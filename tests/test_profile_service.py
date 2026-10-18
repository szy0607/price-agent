"""A6 画像 Agent 测试：纯函数任何环境跑；DB 探针走 RUN_MYSQL_KEY_TESTS=1。

模型调用一律 monkeypatch——走用户自己的 API Key，真调用一次就花一次钱。

fixture 必须 scope="module"（loop_scope 同步）：画像行要跨测试存活，
pytest_asyncio.fixture 不写 scope 默认是 function 级，会在每个测试后把
用户连同画像行删掉（2026-10-14 探针踩过，表现为「上一个测试写的行读不到」）。
"""
import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.key_crypto import encrypt
from app.core.security import hash_password
from app.database.session import async_engine, async_session_local
from app.main import app
from app.models import (ChatMessage, Conversation, PurchaseRecord, User, UserApiKey,
                        UserProfile, UserSession)
from app.services import model_call, profile_service

pytestmark = pytest.mark.asyncio(loop_scope="module")
PASSWORD = "testPassword123"


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def dispose_test_engine():
    yield
    await async_engine.dispose()


def _require_mysql() -> None:
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")


def _purchase(row_id: int, **kwargs) -> PurchaseRecord:
    return PurchaseRecord(user_id=kwargs.pop("user_id", 1),
                          name=kwargs.pop("name", f"商品{row_id}"),
                          specs=kwargs.pop("specs", {}), id=row_id, **kwargs)


def _owned(row_id: int, **kwargs):
    from app.models import OwnedItem
    return OwnedItem(user_id=kwargs.pop("user_id", 1),
                     name=kwargs.pop("name", f"物品{row_id}"),
                     category=kwargs.pop("category", "外设"),
                     specs=kwargs.pop("specs", {}), id=row_id, **kwargs)


# ==================== 纯函数：_parse_verdict ====================

def test_parse_verdict_accepts_plain_and_fenced_json():
    assert profile_service._parse_verdict(
        '{"updated": true, "preferences": {"预算区间": "500"}}') == (True, {"预算区间": "500"})
    assert profile_service._parse_verdict(
        '```json\n{"updated": true, "preferences": {"a": 1}}\n```') == (True, {"a": 1})


@pytest.mark.parametrize("text", [
    "模型不想好好说话",                          # 垃圾文本
    '{"updated": false}',                        # 明确不更新
    '{"updated": true}',                         # 缺 preferences
    '{"updated": true, "preferences": {}}',      # 空画像
    '{"updated": "true", "preferences": {"a": 1}}',  # updated 非布尔 true
    '[]',                                        # 形状不对
])
def test_parse_verdict_rejects(text):
    assert profile_service._parse_verdict(text) == (False, {})


# ==================== 纯函数：证据视图 ====================

def test_format_preferences_empty_and_typed_values():
    assert profile_service.format_preferences({}) == ""
    text = profile_service.format_preferences({"预算区间": "500 元左右", "人数": 2, "已有一套": True})
    assert "预算区间：500 元左右" in text
    assert "人数：2" in text and "已有一套：是" in text


def test_summarize_purchases_aggregates_brands_from_specs_not_name():
    """品牌从 specs 聚合——name 是自由文本，里面出现品牌字样也不算证据。"""
    rows = [
        _purchase(1, name="罗技 MX Master 3S", platform="京东", price=699.0, specs={"品牌": "罗技"}),
        _purchase(2, name="某国产键盘", platform="京东", price=459.0, specs={"品牌": "罗技"}),
        _purchase(3, name="米家台灯 Pro", platform=None, price=None, specs={}),
    ]
    text = profile_service.summarize_purchases(rows)
    assert "共 3 条" in text and "价位 459~699 元" in text
    assert "京东 2 件" in text and "罗技 2 件" in text
    assert "非实时价" in text  # 合规：历史价口径必须写进文案
    assert profile_service.summarize_purchases([]) == ""


def test_summarize_owned_aggregates_categories_brands_and_prices():
    rows = [
        _owned(1, name="机械键盘", category="外设", price=459.0, specs={"品牌": "罗技"}),
        _owned(2, name="鼠标", category="外设", price=299.0, specs={"品牌": "罗技"}),
        _owned(3, name="台灯", category="家电", price=None, specs={}),
    ]
    text = profile_service.summarize_owned(rows)
    assert "共 3 件" in text and "外设 2 件" in text and "罗技 2 件" in text
    assert "299~459 元" in text
    assert profile_service.summarize_owned([]) == ""


def test_build_profile_context_skips_empty_blocks():
    assert profile_service.build_profile_context({}, [], []) == ""
    text = profile_service.build_profile_context({"用途": "静音办公"}, [], [])
    assert text.startswith("【用户偏好】") and "【消费行为】" not in text


# ==================== DB 探针 ====================

def _login_payload(email: str) -> dict:
    salt = secrets.token_hex(8)
    ts = str(int(time.time()))
    answer = "TEST23"
    sig = hmac.new(settings.captcha_key.encode(), f"{salt}.{ts}.{answer}".encode(),
                   hashlib.sha256).hexdigest()
    return {"user_email": email, "password": PASSWORD,
            "captcha_token": f"{salt}.{ts}.{sig}", "captcha_code": answer}


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def shopper():
    """一个测试用户；画像/会话/消息由各测试自建自清，finally 收尾全删。

    顺带挂一条可用默认 key：2026-10-16 起 `prepare_chat` 会先 `key_for_call`
    （取 key 的责任从 call_model 内部上移），没有 key 时 /chat/message 直接 400。
    模型调用仍由各测试 monkeypatch，这个假 key 永不出网。
    """
    _require_mysql()
    async with async_session_local() as db:
        async with db.begin():
            user = User(user_email=f"a6-test-{uuid.uuid4().hex}@example.invalid",
                        username="a6-test", password_hash=hash_password(PASSWORD))
            db.add(user)
            await db.flush()
            uid = user.id
            db.add(UserApiKey(
                user_id=uid, provider="test", base_url="https://api.deepseek.com",
                encrypted_key=encrypt("sk-test-not-a-real-key"), key_suffix="testkey",
                status="active", model_name="fake-model", is_default=True))
    try:
        yield uid
    finally:
        async with async_session_local() as db:
            async with db.begin():
                conv_ids = list((await db.scalars(
                    select(Conversation.id).where(Conversation.user_id == uid))).all())
                for cid in conv_ids:
                    await db.execute(delete(ChatMessage).where(ChatMessage.conversation_id == cid))
                await db.execute(delete(Conversation).where(Conversation.user_id == uid))
                await db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
                await db.execute(delete(UserSession).where(UserSession.user_id == uid))
                await db.execute(delete(UserApiKey).where(UserApiKey.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))


async def _email_of(uid: int) -> str:
    async with async_session_local() as db:
        return await db.scalar(select(User.user_email).where(User.id == uid))


def _patch_both(monkeypatch, a6_reply: str) -> dict:
    """按 system prompt 分流：A6 的 prompt 返回画像裁决，chat 的返回普通回复。

    mock 签名跟着 2026-10-16 的 call_model 改造走：收 KeyRecord、不再收
    user_id / session（key 由调用方在自己的 session 里查好传入）。
    """
    seen: dict = {}

    async def fake_call(key, messages, **kwargs):
        if messages and messages[0]["content"] == profile_service.PROFILE_SYSTEM_PROMPT:
            seen["a6_input"] = messages[1]["content"]
            return a6_reply, "fake-model", []
        seen["chat_system"] = messages[0]["content"]
        return "chat 回复", "fake-model", []

    monkeypatch.setattr(model_call, "call_model", fake_call)
    return seen


async def test_refresh_profile_writes_preferences(shopper, monkeypatch):
    """直接调后台入口：输入含本轮对话 → 画像落库。"""
    seen = _patch_both(monkeypatch, '{"updated": true, "preferences": {"预算区间": "500 元左右", "用途": "静音办公"}}')
    async with async_session_local() as db:
        async with db.begin():
            conv = Conversation(user_id=shopper, title="键盘咨询")
            db.add(conv)
            await db.flush()
            db.add(ChatMessage(user_id=shopper, conversation_id=conv.id, role="user",
                               content="我预算五百左右，想要个静音键盘"))
            cid = conv.id
    await profile_service.refresh_profile(shopper, cid)
    async with async_session_local() as db:
        row = await db.get(UserProfile, shopper)
        assert row is not None and row.preferences["预算区间"] == "500 元左右"
    assert "预算五百" in seen["a6_input"]


async def test_chat_message_triggers_profile_write(shopper, monkeypatch):
    """接线：POST /chat/message 后 BackgroundTasks 应把画像写进库。"""
    _patch_both(monkeypatch, '{"updated": true, "preferences": {"来源": "接线测试"}}')
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await client.post("/auth/login", json=_login_payload(await _email_of(shopper)))
        r = await client.post("/chat/message", headers={"X-Requested-With": "price-agent"},
                              json={"conversation_id": None, "text": "随便聊聊"})
        assert r.status_code == 200 and r.json()["code"] == 0
    async with async_session_local() as db:
        row = await db.get(UserProfile, shopper)
        assert row is not None and row.preferences.get("来源") == "接线测试"


async def test_chat_system_prompt_includes_profile(shopper, monkeypatch):
    """读取侧：画像存在时，chat 的 system 必须带上【用户偏好】块。"""
    seen = _patch_both(monkeypatch, '{"updated": false}')
    async with async_session_local() as db:
        await profile_service.upsert_preferences(shopper, {"用途": "静音办公"}, db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        await client.post("/auth/login", json=_login_payload(await _email_of(shopper)))
        r = await client.post("/chat/message", headers={"X-Requested-With": "price-agent"},
                              json={"conversation_id": None, "text": "在吗"})
        assert r.status_code == 200
    assert "【用户偏好】" in seen["chat_system"] and "静音办公" in seen["chat_system"]


async def test_refresh_profile_no_update_keeps_update_time(shopper, monkeypatch):
    """防抖动：updated:false 完全不写库，update_time 不动。"""
    _patch_both(monkeypatch, '{"updated": false}')
    async with async_session_local() as db:
        before = (await db.get(UserProfile, shopper)).update_time
    await profile_service.refresh_profile(shopper, _any_conversation_id(shopper))
    async with async_session_local() as db:
        after = (await db.get(UserProfile, shopper)).update_time
    assert after == before


async def test_refresh_profile_swallows_model_error(shopper, monkeypatch):
    """A6 模型失败只记日志：不 raise，画像保持上一版。"""
    async def boom(key, messages, **kwargs):
        raise model_call.ModelCallError("模型服务已欠费，请前往对应平台充值后重试")

    monkeypatch.setattr(model_call, "call_model", boom)
    await profile_service.refresh_profile(shopper, _any_conversation_id(shopper))


async def _any_conversation_id(user_id: int) -> int:
    async with async_session_local() as db:
        return await db.scalar(select(Conversation.id).where(Conversation.user_id == user_id)
                               .order_by(Conversation.id.desc()).limit(1))


async def test_a6_input_keeps_newest_turns(shopper, monkeypatch):
    """P1 回归（2026-10-14）：长会话下 A6 输入必须含最新轮次。

    左截断（整体 [:cap]）会留下最旧的几轮、把最新提问整段扔掉——
    而「这轮有没有新偏好」正是 A6 的核心职责。
    """
    async with async_session_local() as db:
        async with db.begin():
            conv = Conversation(user_id=shopper, title="长会话")
            db.add(conv)
            await db.flush()
            for i in range(12):
                db.add(ChatMessage(user_id=shopper, conversation_id=conv.id,
                                   role="user" if i % 2 == 0 else "assistant",
                                   content=f"第{i:02d}轮" + "x" * 800))
            cid = conv.id
            db.add(ChatMessage(user_id=shopper, conversation_id=cid, role="user",
                               content="最新一轮的问题：还要不要再买个月饼"))
    seen = _patch_both(monkeypatch, '{"updated": false}')
    await profile_service.refresh_profile(shopper, cid)
    assert "最新一轮的问题" in seen["a6_input"], "A6 输入丢了最新一轮（左截断回归）"
    # 窗口是最近 12 条（第01~11轮 + 新问题），预算 6000 只装得下约 7 条旧轮次：
    # 最新的第11轮必须在，最旧的第01轮必须被挤出——证明淘汰方向是从旧往新留
    assert "第11轮" in seen["a6_input"], "较新的轮次不应被挤掉"
    assert "第01轮" not in seen["a6_input"], "最旧轮次应被预算挤出去"
