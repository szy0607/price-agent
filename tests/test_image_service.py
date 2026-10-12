"""图片上传服务测试。

纯函数部分（格式/尺寸/字段校验）任何环境都能跑；HTTP 集成部分与
tests/test_purchase_record.py 同门槛：RUN_MYSQL_KEY_TESTS=1 + 已 upgrade head 的库。

姿势沿用既有测试：没有 conftest，模块自带 loop_scope="module" 标记、
自签验证码 token 走真登录链路。
"""

import hashlib
import hmac
import io
import os
import secrets
import time
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.errors import BizError, ErrorCode
from app.core.security import hash_password
from app.core.time import get_current_time
from app.database.session import async_engine, async_session_local
from app.main import app
from app.models import CartItem, OwnedItem, User, UserSession
from app.models import Image as ImageRow  # ORM 模型；PIL 的 Image 在本文件里指图像库
from app.schemas.cart_sche import CartItemInSchema
from app.schemas.owned_sche import OwnedItemInSchema, OwnedItemUpdateSchema
from app.services import image_service, image_store

pytestmark = pytest.mark.asyncio(loop_scope="module")
PASSWORD = "testPassword123"
WRITE = {"X-Requested-With": "price-agent"}


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def dispose_test_engine():
    yield
    await async_engine.dispose()


@pytest.fixture(autouse=True)
def isolated_upload_dir(tmp_path, monkeypatch):
    """上传产物落临时目录，跑完 pytest 自清——测试不往真实 uploads/ 留垃圾。"""
    monkeypatch.setattr(image_store, "UPLOAD_DIR", tmp_path)
    yield tmp_path


def _jpeg_bytes(size=(64, 48), color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


# ==================== image_store：落盘前的四道闸 ====================

def test_accepts_real_jpeg_and_returns_uuid_path():
    rel = image_store.save_upload_image(_jpeg_bytes(), "photo.jpg")
    assert rel.startswith("/uploads/") and rel.endswith(".jpg")
    name = rel.rsplit("/", 1)[1]
    assert len(name) == 36  # 32 hex + .jpg
    # 落盘的是重编码 JPEG，且源文件若带 EXIF 也已剥离
    with Image.open(image_store.UPLOAD_DIR / name) as im:
        assert im.format == "JPEG"
        assert im.getexif() == {}


@pytest.mark.parametrize("filename", ["virus.exe", "script.php", "noext", "photo.jpg.php"])
def test_rejects_disallowed_extensions(filename):
    with pytest.raises(BizError) as caught:
        image_store.save_upload_image(_jpeg_bytes(), filename)
    assert caught.value.code == ErrorCode.PARAM_INVALID


def test_rejects_oversized_payload():
    with pytest.raises(BizError) as caught:
        image_store.save_upload_image(b"x" * (image_store.MAX_BYTES + 1), "big.jpg")
    assert caught.value.code == ErrorCode.PARAM_INVALID


def test_rejects_undecodable_content():
    """改了扩展名的假文件：Pillow 打不开，按参数错误拒，不是 500。"""
    with pytest.raises(BizError) as caught:
        image_store.save_upload_image(b"\x00\x01\x02not an image", "fake.jpg")
    assert caught.value.code == ErrorCode.PARAM_INVALID


def test_rejects_decompression_bomb_before_decode():
    """炸弹图必须在 im.load() 之前被 size 检查拦下。

    6000x6000 = 3600 万像素 > MAX_PIXELS(2500 万)。若检查顺序反了
    （先 load 再查 size），这个测试会先在内存上炸。
    """
    with pytest.raises(BizError) as caught:
        image_store.save_upload_image(_jpeg_bytes(size=(6000, 6000)), "bomb.jpg")
    assert caught.value.code == ErrorCode.PARAM_INVALID
    assert caught.value.msg == "图片尺寸超出限制"


def test_normal_large_photo_is_downscaled_not_rejected():
    """4000x3000（1200 万像素）是正常手机图：不拒，缩到 MAX_EDGE 以内。"""
    rel = image_store.save_upload_image(_jpeg_bytes(size=(4000, 3000)), "big.jpg")
    with Image.open(image_store.UPLOAD_DIR / rel.rsplit("/", 1)[1]) as im:
        assert max(im.size) <= image_store.MAX_EDGE


def test_atomic_write_leaves_no_tmp_file():
    rel = image_store.save_upload_image(_jpeg_bytes(), "atomic.jpg")
    name = rel.rsplit("/", 1)[1]
    assert not (image_store.UPLOAD_DIR / f".{name}.tmp").exists()   # 临时文件必须已 rename 走
    assert (image_store.UPLOAD_DIR / name).exists()


# ==================== schema：image 字段的路径白名单 ====================

def _valid_path() -> str:
    return f"/uploads/{uuid.uuid4().hex}.jpg"


@pytest.mark.parametrize("bad", [
    "/uploads/../app/core/config.py",       # 路径穿越
    "/uploads/../../etc/passwd",            # 多层穿越
    "http://evil.com/x.jpg",                # 外域引用（前端 <img> 会直接加载）
    "https://evil.com/x.jpg",
    "/uploads/not-a-uuid.jpg",              # 不是 uuid 形态
    "/uploads/" + "a" * 32 + ".png",        # 后缀不对（落盘统一是 .jpg）
    "/static/logo.png",                     # 别的目录
    "",
])
def test_image_path_rejects_everything_else(bad):
    with pytest.raises(ValueError):
        CartItemInSchema(name="测试", specs={}, image=bad)
    with pytest.raises(ValueError):
        OwnedItemInSchema(name="测试", image=bad)


def test_image_path_accepts_own_upload_shape():
    path = _valid_path()
    item = CartItemInSchema(name="索尼 WH-1000XM6", category="数码", price=None,
                            specs={}, image=path, note=None)
    assert item.image == path
    assert OwnedItemInSchema(name="索尼 WH-1000XM6", image=path).image == path


def test_update_schema_validates_image_too():
    assert OwnedItemUpdateSchema(image=_valid_path()).image is not None
    with pytest.raises(ValueError):
        OwnedItemUpdateSchema(image="/uploads/../x")


# ==================== 限流器 ====================

def test_rate_limit_opens_after_limit():
    from app.core.rate_limit import _windows, check_rate_limit
    key = f"test:{uuid.uuid4().hex}"
    _windows.pop(key, None)
    try:
        for _ in range(3):
            check_rate_limit(key, limit=3, window=60)
        with pytest.raises(BizError) as caught:
            check_rate_limit(key, limit=3, window=60)
        assert caught.value.code == ErrorCode.RATE_LIMITED
    finally:
        _windows.pop(key, None)


# ==================== HTTP 集成 ====================

@pytest_asyncio.fixture(loop_scope="module")
async def uploader():
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")
    async with async_session_local() as db:
        async with db.begin():
            user = User(user_email=f"upload-test-{uuid.uuid4().hex}@example.invalid",
                        username="upload-test", password_hash=hash_password(PASSWORD))
            db.add(user)
            await db.flush()
            user_id = user.id
    try:
        yield user_id
    finally:
        async with async_session_local() as db:
            async with db.begin():
                await db.execute(delete(ImageRow).where(ImageRow.user_id == user_id))
                await db.execute(delete(CartItem).where(CartItem.user_id == user_id))
                await db.execute(delete(OwnedItem).where(OwnedItem.user_id == user_id))
                await db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                await db.execute(delete(User).where(User.id == user_id))


def _login_payload(email: str) -> dict:
    salt = secrets.token_hex(8)
    ts = str(int(time.time()))
    answer = "TEST23"
    sig = hmac.new(settings.captcha_key.encode(), f"{salt}.{ts}.{answer}".encode(),
                   hashlib.sha256).hexdigest()
    return {"user_email": email, "password": PASSWORD,
            "captcha_token": f"{salt}.{ts}.{sig}", "captcha_code": answer}


async def _email_of(user_id: int) -> str:
    async with async_session_local() as db:
        return (await db.scalar(select(User.user_email).where(User.id == user_id)))


async def test_upload_requires_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/upload/image", headers=WRITE,
                                     files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")})
        assert response.status_code == 401


async def test_upload_rejects_missing_origin_header(uploader):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/auth/login", json=_login_payload(await _email_of(uploader)))
        assert response.status_code == 200
        refused = await client.post("/upload/image",
                                    files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")})
        assert refused.status_code == 400
        assert refused.json()["code"] == ErrorCode.PARAM_INVALID


async def test_upload_roundtrip_and_rate_limit(uploader):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/auth/login", json=_login_payload(await _email_of(uploader)))
        assert response.status_code == 200

        ok = await client.post("/upload/image", headers=WRITE,
                               files={"image": ("photo.jpg", _jpeg_bytes(), "image/jpeg")})
        assert ok.status_code == 200, ok.text
        rel = ok.json()["data"]["image"]
        assert rel.startswith("/uploads/")
        assert (image_store.UPLOAD_DIR / rel.rsplit("/", 1)[1]).exists()

        # 限流：第 11 次（60s 窗口 10 次）必须 42901
        for _ in range(9):
            assert (await client.post("/upload/image", headers=WRITE,
                                      files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")})
                    ).status_code == 200
        limited = await client.post("/upload/image", headers=WRITE,
                                    files={"image": ("x.jpg", _jpeg_bytes(), "image/jpeg")})
        assert limited.status_code == 429, limited.text
        assert limited.json()["code"] == ErrorCode.RATE_LIMITED


# ==================== 第二阶段：生命周期与访问收口 ====================

async def _upload(client: AsyncClient) -> str:
    response = await client.post("/upload/image", headers=WRITE,
                                 files={"image": ("photo.jpg", _jpeg_bytes(), "image/jpeg")})
    assert response.status_code == 200, response.text
    return response.json()["data"]["image"]


async def _image_row(path: str) -> ImageRow | None:
    async with async_session_local() as db:
        return (await db.scalars(select(ImageRow).where(ImageRow.path == path))).first()


async def test_upload_registers_pending_row(uploader):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await client.post("/auth/login", json=_login_payload(await _email_of(uploader)))
        rel = await _upload(client)
        row = await _image_row(rel)
        assert row is not None
        assert row.user_id == uploader and row.status == "pending"


async def test_saving_item_references_and_deleting_releases(uploader):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await client.post("/auth/login", json=_login_payload(await _email_of(uploader)))
        rel = await _upload(client)

        # 保存商品 -> referenced
        created = await client.post("/cart/items", headers=WRITE, json={
            "name": "索尼 WH-1000XM6", "category": "数码", "price": None,
            "specs": {}, "image": rel, "note": None})
        assert created.status_code == 200, created.text
        assert (await _image_row(rel)).status == "referenced"

        # 访问收口：主人带 cookie 能下图
        got = await client.get(rel)
        assert got.status_code == 200
        assert got.headers["content-type"].startswith("image/")

        # 删商品 -> released（图还能访问，行还在，等定时清理）
        item_id = created.json()["data"]["id"]
        assert (await client.delete(f"/cart/items/{item_id}/delete", headers=WRITE)).status_code == 200
        assert (await _image_row(rel)).status == "released"


async def test_cross_user_image_access_is_refused(uploader):
    """上传后不保存商品（pending 也有主），别人的 cookie 下图必须 400「不存在」。"""
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")
    async with async_session_local() as db:
        async with db.begin():
            other = User(user_email=f"upload-other-{uuid.uuid4().hex}@example.invalid",
                         username="other", password_hash=hash_password(PASSWORD))
            db.add(other)
            await db.flush()
            other_id = other.id
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as owner, \
                AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as stranger:
            await owner.post("/auth/login", json=_login_payload(await _email_of(uploader)))
            await stranger.post("/auth/login", json=_login_payload(await _email_of(other_id)))
            rel = await _upload(owner)

            # 未登录：40101
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as anon:
                anon_resp = await anon.get(rel)
                assert anon_resp.status_code == 401
                assert anon_resp.json()["code"] == ErrorCode.SESSION_INVALID

            # 登录但图不是你的：40001，且文案与「不存在」一致（不可枚举）
            stranger_resp = await stranger.get(rel)
            assert stranger_resp.status_code == 400
            assert stranger_resp.json()["code"] == ErrorCode.PARAM_INVALID
            assert stranger_resp.json()["msg"] == "图片不存在"
    finally:
        async with async_session_local() as db:
            async with db.begin():
                await db.execute(delete(ImageRow).where(ImageRow.user_id == other_id))
                await db.execute(delete(UserSession).where(UserSession.user_id == other_id))
                await db.execute(delete(User).where(User.id == other_id))


async def test_shared_image_survives_until_last_reference_gone(uploader):
    """购物车和物品库挂同一张图：一边删光，图仍 referenced；全删才 released。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await client.post("/auth/login", json=_login_payload(await _email_of(uploader)))
        rel = await _upload(client)

        cart = await client.post("/cart/items", headers=WRITE, json={
            "name": "共享图测试-车", "category": "数码", "price": None,
            "specs": {}, "image": rel, "note": None})
        owned = await client.post("/items", headers=WRITE, json={
            "name": "共享图测试-库", "category": "数码", "price": None,
            "specs": {}, "image": rel, "note": None})
        cart_id, owned_id = cart.json()["data"]["id"], owned.json()["data"]["id"]
        assert (await _image_row(rel)).status == "referenced"

        # 只删购物车：物品库还引用着，不能释放
        await client.delete(f"/cart/items/{cart_id}/delete", headers=WRITE)
        assert (await _image_row(rel)).status == "referenced"

        # 物品库也删：两表都无人引用 -> released
        await client.delete(f"/items/{owned_id}", headers=WRITE)
        assert (await _image_row(rel)).status == "released"


async def test_cleanup_removes_stale_pending_and_released(uploader):
    """定时清理：stale pending 与 released 的行和文件都删；referenced 不动。"""
    async with async_session_local() as db:
        async with db.begin():
            stale = ImageRow(user_id=uploader, path=f"/uploads/{uuid.uuid4().hex}.jpg",
                          status="pending")
            stale.create_time = get_current_time() - timedelta(hours=25)
            fresh = ImageRow(user_id=uploader, path=f"/uploads/{uuid.uuid4().hex}.jpg",
                          status="pending")
            released = ImageRow(user_id=uploader, path=f"/uploads/{uuid.uuid4().hex}.jpg",
                             status="released")
            db.add_all([stale, fresh, released])
        async with async_session_local() as db:
            result = await image_service.cleanup_once(db)
        assert result["removed_rows"] == 2
        assert (await _image_row(stale.path)) is None
        assert (await _image_row(fresh.path)) is not None       # 24h 内的 pending 不动
        assert (await _image_row(released.path)) is None


async def test_cleanup_is_idempotent(uploader):
    """文件已不在（外部删的）也不能炸——多 worker 重复跑的底气。"""
    async with async_session_local() as db:
        async with db.begin():
            ghost = ImageRow(user_id=uploader, path=f"/uploads/{uuid.uuid4().hex}.jpg",
                          status="released")
            db.add(ghost)
        async with async_session_local() as db:
            result = await image_service.cleanup_once(db)
        assert result["removed_rows"] == 1
        async with async_session_local() as db:
            again = await image_service.cleanup_once(db)
        assert again["removed_rows"] == 0
