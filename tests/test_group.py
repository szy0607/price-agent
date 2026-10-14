"""购物分组测试。

纯函数部分任何环境都能跑；HTTP 集成部分需要一台已 `alembic upgrade head` 的一次性 MySQL：

    RUN_MYSQL_KEY_TESTS=1 python -m pytest tests/test_group.py -v

覆盖重点：两区划分与价格统计、标记购买时分组内「未购买 → 已购买」翻转、
删物品清引用、一物多组、归属校验（别人的 id 一律「不存在」）。
"""

import asyncio
import hashlib
import hmac
import os
import secrets
import time
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.security import hash_password
from app.database.session import async_engine, async_session_local
from app.main import app
from app.models import CartItem, ItemGroup, ItemGroupRef, OwnedItem, PurchaseRecord, User, UserSession

pytestmark = pytest.mark.asyncio(loop_scope="module")
PASSWORD = "testPassword123"
WRITE = {"X-Requested-With": "price-agent"}


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def dispose_test_engine():
    yield
    await async_engine.dispose()


def _login_payload(email: str, password: str) -> dict:
    """自己签一个有效验证码 token，口径同 app/core/captcha.py。"""
    salt = secrets.token_hex(8)
    ts = str(int(time.time()))
    answer = "TEST23"
    sig = hmac.new(settings.captcha_key.encode(), f"{salt}.{ts}.{answer}".encode(), hashlib.sha256).hexdigest()
    return {"user_email": email, "password": password, "captcha_token": f"{salt}.{ts}.{sig}", "captcha_code": answer}


@pytest_asyncio.fixture(loop_scope="module")
async def two_users():
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")
    ids = []
    try:
        async with async_session_local() as db:
            async with db.begin():
                for _ in range(2):
                    user = User(user_email=f"group-test-{uuid.uuid4().hex}@example.invalid",
                                username="group-test", password_hash="unused")
                    db.add(user)
                    await db.flush()
                    ids.append(user.id)
        yield ids
    finally:
        # 逻辑外键（决策 #30）：删用户不会带走记录，必须显式清，且先清子表。
        # User 的主键是 id 不是 user_id，单独处理
        async with async_session_local() as db:
            async with db.begin():
                await db.execute(delete(ItemGroupRef).where(ItemGroupRef.group_id.in_(
                    select(ItemGroup.id).where(ItemGroup.user_id.in_(ids))
                )))
                for model in (ItemGroup, CartItem, OwnedItem, PurchaseRecord, UserSession):
                    await db.execute(delete(model).where(model.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))


async def _set_password_and_login(client: AsyncClient, user_id: int) -> None:
    async with async_session_local() as db:
        async with db.begin():
            user = await db.scalar(select(User).where(User.id == user_id))
            user.password_hash = hash_password(PASSWORD)
            email = user.user_email
    response = await client.post("/auth/login", json=_login_payload(email, PASSWORD))
    assert response.status_code == 200, response.text


async def _add_cart_item(client: AsyncClient, name: str, price) -> int:
    # CartItemInSchema 里 category/image/note 都没给默认值（pydantic v2：Optional 不自动
    # 给 None），全是必填——现有契约如此，前端一直显式传 null，测试照办
    response = await client.post("/cart/items",
                                 json={"name": name, "category": "数码", "specs": {"颜色": "黑"},
                                       "price": price, "image": None, "note": None},
                                 headers=WRITE)
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


async def _add_owned_item(client: AsyncClient, name: str, price) -> int:
    response = await client.post("/items", json={"name": name, "specs": {"颜色": "白"}, "price": price},
                                 headers=WRITE)
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


# ==================== 会话与同源保护 ====================

async def test_groups_require_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        assert (await client.get("/groups")).status_code == 401
        assert (await client.post("/groups", json={"name": "x"}, headers=WRITE)).status_code == 401


async def test_write_requires_same_origin_header(two_users):
    first = two_users[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)
        for call in (
            client.post("/groups", json={"name": "x"}),
            client.patch("/groups/1", json={"name": "y"}),
            client.delete("/groups/1"),
            client.post("/groups/1/items", json={"item_type": "cart", "item_id": 1}),
            client.delete("/groups/1/items/cart/1"),
        ):
            assert (await call).status_code == 400


# ==================== 分组 CRUD 与归属 ====================

async def test_group_crud_roundtrip_and_ownership(two_users):
    first, second = two_users
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as own, \
            AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as other:
        await _set_password_and_login(own, first)
        await _set_password_and_login(other, second)

        created = await own.post("/groups", json={"name": "  双11装机清单  ", "note": "  等显卡降价  "},
                                 headers=WRITE)
        assert created.status_code == 200, created.text
        group = created.json()["data"]
        group_id = group["id"]
        assert group["name"] == "双11装机清单"      # 首尾空白被剥掉，不是存进去
        assert group["note"] == "等显卡降价"

        listing = (await own.get("/groups")).json()["data"]
        assert [g["id"] for g in listing] == [group_id]
        assert (await other.get("/groups")).json()["data"] == []

        patched = await own.patch(f"/groups/{group_id}", json={"name": "双12装机清单"}, headers=WRITE)
        assert patched.json()["data"]["name"] == "双12装机清单"
        assert patched.json()["data"]["note"] == "等显卡降价"    # PATCH 只动提交了的字段

        # 别人的 id 一律「分组不存在」，不给可枚举的差别
        for method in ("GET", "PATCH", "DELETE"):
            response = await other.request(method, f"/groups/{group_id}",
                                           json={"name": "越权改"} if method == "PATCH" else None,
                                           headers=WRITE)
            assert response.status_code == 400, response.text
            assert response.json()["msg"] == "分组不存在"

        assert (await own.delete(f"/groups/{group_id}", headers=WRITE)).status_code == 200
        assert (await own.get("/groups")).json()["data"] == []
        assert (await own.delete(f"/groups/{group_id}", headers=WRITE)).status_code == 400


async def test_group_name_validation(two_users):
    first = two_users[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)
        for bad in ({"name": "   "}, {"name": ""}, {"name": "x" * 101}, {"name": "x", "unknown": 1}):
            response = await client.post("/groups", json=bad, headers=WRITE)
            assert response.status_code == 400, f"{bad} -> {response.text}"
            assert response.json()["code"] == ErrorCode.PARAM_INVALID


# ==================== 两区、统计、加组/移出 ====================

async def test_group_detail_zones_and_stats(two_users):
    first = two_users[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)

        group_id = (await client.post("/groups", json={"name": "装机清单"}, headers=WRITE)).json()["data"]["id"]
        cheap = await _add_cart_item(client, "散热器", 100)          # 未购买 · 有价
        free = await _add_cart_item(client, "机箱", None)            # 未购买 · 未填价
        owned = await _add_owned_item(client, "电源", 50)            # 已购买 · 有价

        for item_type, item_id in (("cart", cheap), ("cart", free), ("owned", owned)):
            response = await client.post(f"/groups/{group_id}/items",
                                         json={"item_type": item_type, "item_id": item_id}, headers=WRITE)
            assert response.status_code == 200, response.text

        detail = (await client.get(f"/groups/{group_id}")).json()["data"]
        assert {i["id"] for i in detail["unpurchased"]} == {cheap, free}
        assert [i["id"] for i in detail["purchased"]] == [owned]
        assert detail["stats"] == {
            "unpurchased_count": 2, "purchased_count": 1, "unpriced_count": 1,
            "unpurchased_total": 100, "purchased_total": 50, "total": 150,
        }

        # 列表页同样带统计，不用逐个点开
        row = (await client.get("/groups")).json()["data"][0]
        assert row["total"] == 150 and row["unpriced_count"] == 1

        # 重复加入同组：人话报错，不是 500
        again = await client.post(f"/groups/{group_id}/items",
                                  json={"item_type": "cart", "item_id": cheap}, headers=WRITE)
        assert again.status_code == 400
        assert again.json()["msg"] == "该物品已在分组中"

        # 不存在的物品 / 类型指错表
        for body in ({"item_type": "cart", "item_id": 999999}, {"item_type": "owned", "item_id": cheap}):
            assert (await client.post(f"/groups/{group_id}/items", json=body, headers=WRITE)).status_code == 400

        # 移出
        removed = await client.delete(f"/groups/{group_id}/items/cart/{free}", headers=WRITE)
        assert removed.status_code == 200
        assert (await client.delete(f"/groups/{group_id}/items/cart/{free}", headers=WRITE)).status_code == 400
        detail = (await client.get(f"/groups/{group_id}")).json()["data"]
        assert detail["stats"]["unpurchased_count"] == 1
        assert detail["stats"]["unpriced_count"] == 0

        # 删分组不动物品
        assert (await client.delete(f"/groups/{group_id}", headers=WRITE)).status_code == 200
        assert len((await client.get("/cart/items")).json()["data"]) == 2
        assert len((await client.get("/items")).json()["data"]) == 1


async def test_one_item_in_multiple_groups(two_users):
    """一物多组（大宋 10-14 拍板）：同一物品可以同时在两个分组里。"""
    first = two_users[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)
        g1 = (await client.post("/groups", json={"name": "双11装机"}, headers=WRITE)).json()["data"]["id"]
        g2 = (await client.post("/groups", json={"name": "明年升级"}, headers=WRITE)).json()["data"]["id"]
        disk = await _add_cart_item(client, "硬盘", 400)

        for gid in (g1, g2):
            response = await client.post(f"/groups/{gid}/items",
                                         json={"item_type": "cart", "item_id": disk}, headers=WRITE)
            assert response.status_code == 200, response.text

        for gid in (g1, g2):
            detail = (await client.get(f"/groups/{gid}")).json()["data"]
            assert [i["id"] for i in detail["unpurchased"]] == [disk]
            assert detail["stats"]["total"] == 400


# ==================== 分组跟随：标记购买 / 删除 ====================

async def test_transfer_flips_item_to_purchased_zone(two_users):
    """标记购买后，分组里该物品从未购买区翻到已购买区，价格用转移时填的实价。"""
    first = two_users[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)
        group_id = (await client.post("/groups", json={"name": "装机清单"}, headers=WRITE)).json()["data"]["id"]
        fan = await _add_cart_item(client, "风扇", 80)
        await client.post(f"/groups/{group_id}/items", json={"item_type": "cart", "item_id": fan},
                          headers=WRITE)

        before = (await client.get(f"/groups/{group_id}")).json()["data"]
        assert before["stats"]["unpurchased_total"] == 80

        transferred = await client.post(f"/cart/items/{fan}/transform",
                                        json={"price": 75, "platform": "京东"}, headers=WRITE)
        assert transferred.status_code == 200, transferred.text

        after = (await client.get(f"/groups/{group_id}")).json()["data"]
        assert after["unpurchased"] == []
        assert [i["id"] for i in after["purchased"]] == [transferred.json()["data"]["owned"]["id"]]
        assert after["stats"]["purchased_total"] == 75      # 实价，不是购物车参考价 80
        assert after["stats"]["total"] == 75

        # 购物车里已经没有它了，分组里也不该再有未购买区的残影
        assert fan not in [i["id"] for i in (await client.get("/cart/items")).json()["data"]]


async def test_delete_item_removes_group_ref(two_users):
    """删物品 = 分组关系一起走（购物车、物品库两张表都验）。"""
    first = two_users[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)
        group_id = (await client.post("/groups", json={"name": "清单"}, headers=WRITE)).json()["data"]["id"]
        cart_item = await _add_cart_item(client, "待删的购物车物品", 10)
        owned_item = await _add_owned_item(client, "待删的物品库物品", 20)
        for item_type, item_id in (("cart", cart_item), ("owned", owned_item)):
            await client.post(f"/groups/{group_id}/items",
                              json={"item_type": item_type, "item_id": item_id}, headers=WRITE)
        assert (await client.get(f"/groups/{group_id}")).json()["data"]["stats"]["total"] == 30

        assert (await client.delete(f"/cart/items/{cart_item}/delete", headers=WRITE)).status_code == 200
        assert (await client.delete(f"/items/{owned_item}", headers=WRITE)).status_code == 200

        detail = (await client.get(f"/groups/{group_id}")).json()["data"]
        assert detail["unpurchased"] == [] and detail["purchased"] == []
        assert detail["stats"]["total"] == 0
