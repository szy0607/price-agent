"""消费记录测试。

纯函数部分任何环境都能跑；HTTP 与聊天注入部分需要一台已 `alembic upgrade head` 的一次性 MySQL：

    RUN_MYSQL_KEY_TESTS=1 python -m pytest tests/test_purchase_record.py -v

姿势沿用 `tests/test_api_key_service.py`：没有 conftest，模块自带 `loop_scope="module"` 标记、
自签验证码 token 走真登录链路、出网用 `httpx.MockTransport` 顶掉。
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.core.api_key_crypto import KeyRing
from app.core.config import settings
from app.core.errors import BizError, ErrorCode
from app.core.security import hash_password
from app.database.session import async_engine, async_session_local
from app.main import app
from app.models import PurchaseRecord, User, UserSession
from app.router.purchase_record import _validate_purchased_at, _validate_specs, _validate_url
from app.services import chat_service, product_page
from app.services.api_key_service import ApiKeyService
from app.services.chat_service import SYSTEM_PROMPT, _system_prompt_with
from app.services.product_page import clean_title, parse_product_url
from app.services.user_profile import compose_context, summarize_focus, summarize_profile


pytestmark = pytest.mark.asyncio(loop_scope="module")
ACTOR = "service:test"
PASSWORD = "testPassword123"
WRITE = {"X-Requested-With": "price-agent"}


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def dispose_test_engine():
    yield
    await async_engine.dispose()


def _login_payload(email: str, password: str) -> dict:
    """自己签一个有效验证码 token。

    口径见 `app/core/captcha.py`：`sig = hmac_sha256(CAPTCHA_KEY, f"{salt}.{ts}.{答案}")`。
    比 mock 掉 `verify_captcha` 好 —— 走真登录链路，签名口径一改这里就红。
    """
    salt = secrets.token_hex(8)
    ts = str(int(time.time()))
    answer = "TEST23"
    sig = hmac.new(settings.captcha_key.encode(), f"{salt}.{ts}.{answer}".encode(), hashlib.sha256).hexdigest()
    return {"user_email": email, "password": password, "captcha_token": f"{salt}.{ts}.{sig}", "captcha_code": answer}


class _Row:
    """给纯函数用的假行：summarize_* 只读属性，不碰 ORM。"""

    def __init__(self, name, platform=None, price=None, purchased_at=None, specs=None, note=None):
        self.name = name
        self.platform = platform
        self.price = price
        self.purchased_at = purchased_at
        self.specs = specs or {}
        self.note = note


# ==================== 链接解析：白名单是唯一的 SSRF 防线 ====================

@pytest.mark.parametrize("url,platform,goods_id", [
    ("https://item.jd.com/100012043912.html", "京东", "100012043912"),
    ("https://item.m.jd.com/product/123.html", "京东", "123"),
    ("https://item.taobao.com/item.htm?id=654321&spm=a21n57", "淘宝", "654321"),
    ("https://detail.tmall.com/item.htm?id=777", "天猫", "777"),
    ("https://mobile.yangkeduo.com/goods.html?goods_id=8888", "拼多多", "8888"),
    ("https://product.suning.com/0070074/1234567890.html", "苏宁易购", "1234567890"),
])
def test_parse_accepts_allowlisted_links(url, platform, goods_id):
    assert parse_product_url(url) == (platform, goods_id)


@pytest.mark.parametrize("url", [
    "",
    "   ",
    "http://item.jd.com/1.html",                    # 只放 https
    "https://evil.com/x",                           # 白名单外
    "https://item.jd.com.evil.com/1.html",          # 后缀伪装：不是 endswith 匹配
    "https://sub.item.jd.com/1.html",               # 子域
    "https://item.jd.com:8443/1.html",              # 带端口
    "https://user:pass@item.jd.com/1.html",         # 带凭据
    "https://item.jd.com/1.html?" + "a" * 600,      # 超过列宽
    "/item.jd.com/1.html",                          # 相对地址
    "item.jd.com/1.html",                           # 无 scheme
])
def test_parse_rejects_everything_else(url):
    with pytest.raises(BizError) as caught:
        parse_product_url(url)
    assert caught.value.code == ErrorCode.PARAM_INVALID
    assert caught.value.http_status == 400


@pytest.mark.parametrize("bad", [None, 1, ["https://item.jd.com/1.html"], {"url": "https://item.jd.com/1.html"}])
def test_parse_rejects_non_string_without_crashing(bad):
    with pytest.raises(BizError):
        parse_product_url(bad)


def test_two_rejection_messages_are_distinct():
    """「格式不对」和「这家不支持」是两句不同的话，但都不透出内网判定细节。"""
    with pytest.raises(BizError) as bad_format:
        parse_product_url("https://item.jd.com:8443/1.html")
    with pytest.raises(BizError) as unsupported:
        parse_product_url("https://www.dewu.com/sku/1")
    assert bad_format.value.msg == product_page._INVALID_MSG
    assert unsupported.value.msg == product_page._UNSUPPORTED_MSG


# ==================== 标题清洗：外部内容进库/进对话前必过 ====================

def test_clean_title_strips_platform_decoration():
    assert clean_title("<title>Sony WH-1000XM5 耳机【图片 价格 参数 评价】-京东</title>") == "Sony WH-1000XM5 耳机"


def test_clean_title_collapses_whitespace_and_zero_width():
    assert clean_title("<title>\n  戴森 V12​\tDetect\n  吸尘器 </title>") == "戴森 V12 Detect 吸尘器"


def test_clean_title_strips_real_tags_before_unescaping():
    assert clean_title("<title><b>好物</b></title>") == "好物"
    # 反转义后才出现的 < 是纯文本，Vue 的 {{ }} 会再转义一次，不会变成标签
    assert clean_title("<title>&lt;b&gt;好物&lt;/b&gt;</title>") == "<b>好物</b>"


def test_clean_title_falls_back_to_og_title():
    assert clean_title('<html><head><meta property="og:title" content="象印 保温杯"></head></html>') == "象印 保温杯"


def test_clean_title_caps_length():
    assert len(clean_title(f"<title>{'长' * 500}</title>")) == product_page._TITLE_CAP


@pytest.mark.parametrize("markup", ["", "<html><body>no title</body></html>", "<title></title>", "<title>   </title>"])
def test_clean_title_returns_empty_when_nothing_usable(markup):
    assert clean_title(markup) == ""


# ==================== 记录字段：入库前各条边界 ====================

def test_record_url_is_not_bound_by_the_fetch_allowlist():
    """白名单管「我们主动去抓谁」，不管「用户能记什么链接」。"""
    assert _validate_url("https://www.dewu.com/sku/123") == "https://www.dewu.com/sku/123"
    assert _validate_url("  https://item.jd.com/1.html  ") == "https://item.jd.com/1.html"
    assert _validate_url(None) is None
    assert _validate_url("   ") is None


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)",                                  # 存储型 XSS
    "data:text/html,<script>alert(1)</script>",
    "ftp://item.jd.com/1.html",
    "https://item.jd.com/1.html\nx",                        # 控制字符
    "https://item.jd.com/" + "a" * 600,                     # 超列宽
])
def test_record_url_rejects_non_http_and_control_chars(bad):
    with pytest.raises(BizError):
        _validate_url(bad)


def test_specs_keep_only_scalar_pairs():
    cleaned = _validate_specs({"颜色": "黑色", "嵌套": {"a": 1}, "列表": [1, 2], None: "x", "空值": "  ", "布尔": True, "数量": 3})
    assert cleaned == {"颜色": "黑色", "布尔": "是", "数量": "3"}


def test_specs_are_capped_in_count_and_length():
    cleaned = _validate_specs({f"键{i}": "值" * 300 for i in range(60)})
    assert len(cleaned) == 30
    assert all(len(key) <= 64 and len(value) <= 128 for key, value in cleaned.items())


def test_purchased_at_normalizes_to_naive_utc():
    """库里存 naive UTC（应用连接固定 +00:00），带时区的入参先归一。"""
    cst = datetime(2026, 3, 1, 10, 30, tzinfo=timezone(timedelta(hours=8)))
    assert _validate_purchased_at(cst) == datetime(2026, 3, 1, 2, 30)
    assert _validate_purchased_at(datetime(2026, 3, 1, 10, 30)) == datetime(2026, 3, 1, 10, 30)
    assert _validate_purchased_at(None) is None


# ==================== 画像与上下文拼装 ====================

def test_profile_is_empty_without_records():
    assert summarize_profile([]) == ""
    assert compose_context("", "") == ""


def test_profile_counts_prices_and_platforms():
    rows = [
        _Row("iPhone 15", "京东", 4999, datetime(2026, 3, 1)),
        _Row("保温杯", "淘宝", 99, datetime(2026, 2, 1)),
        _Row("旧鼠标", "京东"),
    ]
    text = summarize_profile(rows)
    assert "共 3 条消费记录" in text
    assert "2 条填了价格" in text
    assert "均价 2549" in text
    assert "最高 4999" in text and "最低 99" in text
    assert "京东 2 件" in text
    assert "非实时价" in text          # 提醒模型这不是当前报价
    assert "iPhone 15" in text and "2026-03-01" in text


def test_profile_survives_rows_without_anything():
    assert summarize_profile([_Row("")]) != ""      # 只有条数还是有意义
    assert "常记的购买平台" not in summarize_profile([_Row("仅名称")])


def test_profile_is_capped():
    rows = [_Row("很长的商品名" * 30, "京东", 1) for _ in range(200)]
    assert len(summarize_profile(rows)) <= 1200


def test_focus_expands_specs_and_note():
    text = summarize_focus([_Row("戴森 V12", "苏宁", 2999, datetime(2026, 5, 6), {"颜色": "金色"}, "国补后买的")])
    assert text.startswith("- ")
    for fragment in ("戴森 V12", "苏宁", "2999 元", "2026-05-06", "颜色:金色", "备注 国补后买的"):
        assert fragment in text


def test_focus_flattens_newlines_in_names():
    """名称里的换行会顶破「一行一条」的排版；恶意页面标题正是靠这个塞假条目。"""
    assert len(summarize_focus([_Row("商品\n- 假条目\n- 第二条")]).splitlines()) == 1


def test_compose_labels_both_blocks():
    merged = compose_context("概况文本", "- 焦点文本")
    assert "用户消费概况" in merged and "用户本次勾选的商品" in merged
    assert merged.index("用户本次勾选的商品") < merged.index("用户消费概况")


# ==================== system 提示合成：红线一个字不能动 ====================

def test_system_prompt_is_untouched_without_context():
    assert _system_prompt_with("") == SYSTEM_PROMPT
    assert _system_prompt_with("   \n  ") == SYSTEM_PROMPT


def test_system_prompt_keeps_the_no_realtime_price_red_line():
    merged = _system_prompt_with("用户消费概况：共 3 条消费记录。")
    assert merged.startswith(SYSTEM_PROMPT)
    assert "你没有实时商品、库存、价格或优惠券数据" in merged
    assert "【用户消费记录】" in merged
    assert "用户消费概况" in merged


def test_system_prompt_truncates_oversized_context():
    # 引导语本身含一个「记」字（【用户消费记录】），所以断言总长为 1 + 上限
    merged = _system_prompt_with("记" * 9000)
    assert merged.count("记") == 1 + 4000
    assert merged.endswith("记")
    assert len(_system_prompt_with("x" * 9000)) == len(SYSTEM_PROMPT) + len(chat_service._CONTEXT_LEAD) + 4000


# ==================== HTTP 集成 ====================

@pytest_asyncio.fixture(loop_scope="module")
async def two_users():
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")
    ids = []
    try:
        async with async_session_local() as db:
            async with db.begin():
                for _ in range(2):
                    user = User(user_email=f"purchase-test-{uuid.uuid4().hex}@example.invalid", username="purchase-test", password_hash="unused")
                    db.add(user)
                    await db.flush()
                    ids.append(user.id)
        yield ids
    finally:
        # user_id 是逻辑外键（决策 #30），删用户不会带走记录，必须显式清
        async with async_session_local() as db:
            async with db.begin():
                await db.execute(delete(PurchaseRecord).where(PurchaseRecord.user_id.in_(ids)))
                await db.execute(delete(UserSession).where(UserSession.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))


async def _set_password_and_login(client: AsyncClient, user_id: int) -> None:
    async with async_session_local() as db:
        async with db.begin():
            user = await db.scalar(select(User).where(User.id == user_id))
            user.password_hash = hash_password(PASSWORD)
            email = user.user_email
    response = await client.post("/auth/login", json=_login_payload(email, PASSWORD))
    assert response.status_code == 200, response.text


async def _count(user_id: int) -> int:
    async with async_session_local() as db:
        return await db.scalar(select(PurchaseRecord.id).where(PurchaseRecord.user_id == user_id).limit(1)) is not None


def _use_keks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_key_keks", SecretStr('{"v1":"' + base64.b64encode(b"1" * 32).decode() + '"}'))
    monkeypatch.setattr(settings, "api_key_active_kek_version", "v1")


def _stub_outbound(monkeypatch, target_module, payload: dict) -> list[dict]:
    """顶掉某个模块的 httpx.AsyncClient，记录它真正发出去的请求体。"""
    bodies: list[dict] = []
    original = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(target_module.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return bodies


async def test_records_require_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        assert (await client.get("/purchase-records")).status_code == 401
        assert (await client.post("/purchase-records", json={"name": "x"}, headers=WRITE)).status_code == 401


async def test_record_crud_roundtrip_and_ownership(two_users):
    first, second = two_users
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as own, \
            AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as other:
        await _set_password_and_login(own, first)
        await _set_password_and_login(other, second)

        # 写操作必须带同源保护头
        assert (await own.post("/purchase-records", json={"name": "保温杯"})).status_code == 400

        created = await own.post("/purchase-records", json={
            "name": "Sony WH-1000XM5",
            "product_url": "https://item.jd.com/100012043912.html",
            "platform": "京东",
            "price": 1699,
            "specs": {"颜色": "黑色", "嵌套": {"x": 1}},
            "purchased_at": "2026-03-01T10:30:00+08:00",
            "note": "  ",
        }, headers=WRITE)
        assert created.status_code == 200, created.text
        row = created.json()["data"]
        assert row["name"] == "Sony WH-1000XM5"
        assert row["specs"] == {"颜色": "黑色"}
        assert row["note"] is None
        assert row["purchased_at"] == "2026-03-01T02:30:00Z"    # +08:00 → naive UTC → 回给前端补 Z
        record_id = row["id"]

        listing = (await own.get("/purchase-records")).json()["data"]
        assert [item["id"] for item in listing] == [record_id]
        assert (await other.get("/purchase-records")).json()["data"] == []

        # 别人的 id 一律「不存在」，不给「存在但不属于你」这种可枚举的差别
        for method in ("PUT", "DELETE"):
            response = await other.request(
                method,
                f"/purchase-records/{record_id}",
                json={"name": "越权改"} if method == "PUT" else None,
                headers=WRITE,
            )
            assert response.status_code == 400, response.text
            assert response.json()["code"] == ErrorCode.PARAM_INVALID
            assert response.json()["msg"] == "消费记录不存在"
        assert (await own.get("/purchase-records")).json()["data"][0]["name"] == "Sony WH-1000XM5"

        updated = await own.put(f"/purchase-records/{record_id}", json={"name": "  改成 戴森 V12  ", "specs": {}}, headers=WRITE)
        assert updated.status_code == 200, updated.text
        body = updated.json()["data"]
        assert body["name"] == "改成 戴森 V12"
        assert body["product_url"] is None      # PUT 是整条覆盖，没传即清空
        assert body["price"] is None

        assert (await own.delete(f"/purchase-records/{record_id}", headers=WRITE)).status_code == 200
        assert (await own.get("/purchase-records")).json()["data"] == []
        assert (await own.delete(f"/purchase-records/{record_id}", headers=WRITE)).status_code == 400


async def test_record_validation_bounds(two_users):
    first = two_users[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)
        had_one = await _count(first)
        for bad in (
            {"name": "   "},
            {"name": "x" * 300},
            {"name": "x", "price": -1},
            {"name": "x", "price": 10**12},
            {"name": "x", "product_url": "javascript:alert(1)"},
            {"name": "x", "platform": "x" * 100},
            {"name": "x", "unknown_field": 1},
            {"name": "x", "purchased_at": "去年三月"},
        ):
            response = await client.post("/purchase-records", json=bad, headers=WRITE)
            assert response.status_code == 400, f"{bad} -> {response.text}"
            assert response.json()["code"] == ErrorCode.PARAM_INVALID
        # 一条都没落库
        assert await _count(first) == had_one


async def test_link_preview_returns_draft_without_saving(two_users, monkeypatch):
    first = two_users[0]
    calls: list[httpx.Request] = []
    original = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                              content="<title>象印 保温杯 SM-SA48【图片 价格】-京东</title>".encode("utf-8"))

    monkeypatch.setattr(product_page.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)

        refused = await client.post("/purchase-records/link-preview", json={"product_url": "https://www.dewu.com/sku/1"}, headers=WRITE)
        assert refused.status_code == 400
        assert refused.json()["msg"] == product_page._UNSUPPORTED_MSG
        assert calls == []        # 白名单外的链接连一次外呼都不该发生

        ok = await client.post("/purchase-records/link-preview", json={"product_url": "https://item.jd.com/123.html"}, headers=WRITE)
        assert ok.status_code == 200, ok.text
        assert ok.json()["data"] == {"name_suggestion": "象印 保温杯 SM-SA48", "platform": "京东", "goods_id": "123", "source": "网络"}

        # 草稿只是草稿：没有确认这一步就绝不该有记录
        assert (await client.get("/purchase-records")).json()["data"] == []

        sent = calls[0]
        assert str(sent.url) == "https://item.jd.com/123.html"
        header_names = {name.lower() for name in sent.headers.keys()}
        assert "cookie" not in header_names       # 会话 cookie 绝不能带去第三方
        assert "authorization" not in header_names
        assert sent.headers.get("user-agent") == product_page._BROWSER_UA


async def test_link_preview_never_follows_redirects(two_users, monkeypatch):
    """follow_redirects=False：跟一跳等于把白名单作废。"""
    first = two_users[0]
    seen: list[str] = []
    original = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8080/internal"})

    monkeypatch.setattr(product_page.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)
        response = await client.post("/purchase-records/link-preview", json={"product_url": "https://item.jd.com/1.html"}, headers=WRITE)
        assert response.status_code == 400
        assert response.json()["msg"] == "没能读到该商品页面，请直接手动填写"
        assert seen == ["https://item.jd.com/1.html"]   # 只发了一次，没有跟着跳到内网


async def test_link_preview_without_session_is_rejected():
    """它会驱动一次对外请求，匿名绝不能调 —— require_same_origin_write 只查头、不查登录。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/purchase-records/link-preview", json={"product_url": "https://item.jd.com/1.html"}, headers=WRITE)
        assert response.status_code == 401


async def _prepare_chat_user(user_id: int, provider: str, monkeypatch) -> None:
    _use_keks(monkeypatch)
    async with async_session_local() as db:
        async with db.begin():
            user = await db.scalar(select(User).where(User.id == user_id))
            user.model_provider = provider
    await ApiKeyService(async_session_local, KeyRing.from_settings(settings)).save_key(user_id, provider, "sk-test-secret-aaaa", actor=ACTOR)


async def test_chat_injects_profile_and_focus_openai_shape(two_users, monkeypatch):
    first = two_users[0]
    await _prepare_chat_user(first, "openai", monkeypatch)
    bodies = _stub_outbound(monkeypatch, chat_service, {"choices": [{"message": {"content": "好的"}}]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, first)
        saved = await client.post("/purchase-records", json={"name": "戴森 V12 Detect", "platform": "苏宁", "price": 2999}, headers=WRITE)
        record_id = saved.json()["data"]["id"]
        question = "这个牌子的东西我之前买过吗"

        reply = await client.post("/chat/message", json={
            "messages": [{"role": "user", "content": question}],
            # 重复、0、负数都该被 ChatInput 的校验器吃掉，只留 1 个有效 id
            "record_ids": [record_id, record_id, 0, -5],
        }, headers=WRITE)
        assert reply.status_code == 200, reply.text
        assert reply.json()["data"]["model"] == "gpt-4o-mini"

        system = bodies[-1]["messages"][0]
        assert system["role"] == "system"
        assert system["content"].startswith(SYSTEM_PROMPT)
        assert "戴森 V12 Detect" in system["content"]
        assert "用户本次勾选的商品" in system["content"]
        assert "用户消费概况" in system["content"]
        # 注入走 system，用户原话一个字不动
        assert bodies[-1]["messages"][-1] == {"role": "user", "content": question}

        called = len(bodies)
        foreign = await client.post("/chat/message", json={
            "messages": [{"role": "user", "content": "接着聊"}],
            "record_ids": [999999999],
        }, headers=WRITE)
        assert foreign.status_code == 400
        assert "所选消费记录不存在" in foreign.json()["msg"]
        assert len(bodies) == called        # 报错发生在调模型之前，一次外呼都没花出去

        assert (await client.post("/chat/message", json={"messages": [{"role": "user", "content": "随便聊聊"}]}, headers=WRITE)).status_code == 200
        plain = bodies[-1]["messages"][0]["content"]
        assert "用户本次勾选的商品" not in plain
        assert "用户消费概况" in plain      # 没勾选也带画像


async def test_chat_injects_profile_for_anthropic_shape(two_users, monkeypatch):
    """anthropic 的 system 是顶层字段，不是 messages 首条 —— 两个分支都得改到。"""
    second = two_users[1]
    await _prepare_chat_user(second, "anthropic", monkeypatch)
    bodies = _stub_outbound(monkeypatch, chat_service, {"content": [{"type": "text", "text": "好的"}]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, second)
        saved = await client.post("/purchase-records", json={"name": "小米空气净化器 4 Pro"}, headers=WRITE)
        record_id = saved.json()["data"]["id"]

        reply = await client.post("/chat/message", json={
            "messages": [{"role": "user", "content": "滤芯多久换一次"}],
            "record_ids": [record_id],
        }, headers=WRITE)
        assert reply.status_code == 200, reply.text
        assert reply.json()["data"]["model"] == "claude-haiku-4-5"

        body = bodies[-1]
        assert body["system"].startswith(SYSTEM_PROMPT)
        assert "小米空气净化器 4 Pro" in body["system"]
        assert "你没有实时商品、库存、价格或优惠券数据" in body["system"]
        assert [item["role"] for item in body["messages"]] == ["user"]   # 没有伪装的 system 消息


async def test_chat_still_works_with_no_records_at_all(two_users, monkeypatch):
    """没记录的用户，system 提示必须与改动前逐字相同。"""
    second = two_users[1]
    await _prepare_chat_user(second, "openai", monkeypatch)
    async with async_session_local() as db:
        async with db.begin():
            await db.execute(delete(PurchaseRecord).where(PurchaseRecord.user_id == second))
    bodies = _stub_outbound(monkeypatch, chat_service, {"choices": [{"message": {"content": "好的"}}]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await _set_password_and_login(client, second)
        assert (await client.get("/purchase-records")).json()["data"] == []
        assert (await client.post("/chat/message", json={"messages": [{"role": "user", "content": "你好"}]}, headers=WRITE)).status_code == 200
        assert bodies[-1]["messages"][0]["content"] == SYSTEM_PROMPT
