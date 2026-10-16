"""会话只读路由 + touch 回归测试（DB 探针）。

门槛与 tests/test_image_service.py 相同：RUN_MYSQL_KEY_TESTS=1 + 已
`alembic upgrade head` 的库。模型调用一律 monkeypatch——走用户自己的
API Key，真调用一次就花一次钱，测试绝不能碰。

覆盖：
- GET /conversations：未登录 401；只返回本人的会话；
- GET /conversations/{id}/messages：越权会话 40001；历史按 id 升序；
- touch 回归（2026-10-14 P1）：发消息必须推进会话 update_time，
  且被 touch 的会话按 update_time 排序跳到列表最前——参数换位时
  WHERE 落空，update_time 会停留在 fixture 写死的 2020 年。
"""
import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime

from contextlib import asynccontextmanager

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
from app.models import ChatMessage, Conversation, User, UserApiKey, UserSession
from app.services import model_call

pytestmark = pytest.mark.asyncio(loop_scope="module")
PASSWORD = "testPassword123"


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def dispose_test_engine():
    yield
    await async_engine.dispose()


def _require_mysql() -> None:
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")


def _login_payload(email: str) -> dict:
    salt = secrets.token_hex(8)
    ts = str(int(time.time()))
    answer = "TEST23"
    sig = hmac.new(settings.captcha_key.encode(), f"{salt}.{ts}.{answer}".encode(),
                   hashlib.sha256).hexdigest()
    return {"user_email": email, "password": PASSWORD,
            "captcha_token": f"{salt}.{ts}.{sig}", "captcha_code": answer}


@pytest_asyncio.fixture(loop_scope="module")
async def pair():
    """两个用户各带会话；mine 有 conv1/conv2（update_time 都钉在 2020，专测 touch），
    stranger 有一个会话用于越权断言。"""
    _require_mysql()
    stale = datetime(2020, 1, 1, 0, 0, 0)
    async with async_session_local() as db:
        async with db.begin():
            mine = User(user_email=f"conv-test-{uuid.uuid4().hex}@example.invalid",
                        username="conv-test", password_hash=hash_password(PASSWORD))
            stranger = User(user_email=f"conv-other-{uuid.uuid4().hex}@example.invalid",
                            username="conv-other", password_hash=hash_password(PASSWORD))
            db.add_all([mine, stranger])
            await db.flush()
            # 2026-10-16 起 prepare_chat 会先 key_for_call（取 key 责任从 call_model
            # 内部上移），没有 active+is_default 的 key 时 /chat/message 直接 400。
            # 模型调用在测试里被 monkeypatch，这个假 key 永不出网。
            db.add_all([
                UserApiKey(user_id=mine.id, provider="test",
                           base_url="https://api.deepseek.com",
                           encrypted_key=encrypt("sk-test-not-a-real-key"),
                           key_suffix="testkey", status="active",
                           model_name="fake-model", is_default=True),
            ])
            conv1 = Conversation(user_id=mine.id, title="想买的键盘", update_time=stale)
            conv2 = Conversation(user_id=mine.id, title="台灯要不要换", update_time=stale)
            foreign = Conversation(user_id=stranger.id, title="别人的会话", update_time=stale)
            db.add_all([conv1, conv2, foreign])
            await db.flush()
            db.add_all([
                ChatMessage(user_id=mine.id, conversation_id=conv1.id, role="user",
                            content="键盘选哪款"),
                ChatMessage(user_id=mine.id, conversation_id=conv1.id, role="assistant",
                            content="看你的预算", model="fake-model"),
                ChatMessage(user_id=mine.id, conversation_id=conv1.id, role="user",
                            content="五百左右"),
                ChatMessage(user_id=mine.id, conversation_id=conv1.id, role="assistant",
                            content="那看机械键盘", model="fake-model"),
                ChatMessage(user_id=stranger.id, conversation_id=foreign.id, role="user",
                            content="私密问题"),
            ])
            await db.flush()
            ids = {"mine": mine.id, "stranger": stranger.id,
                   "conv1": conv1.id, "conv2": conv2.id, "foreign": foreign.id,
                   "email": mine.user_email}
    try:
        yield ids
    finally:
        async with async_session_local() as db:
            async with db.begin():
                for uid in (ids["mine"], ids["stranger"]):
                    conv_rows = list((await db.scalars(
                        select(Conversation.id).where(Conversation.user_id == uid))).all())
                    for cid in conv_rows:
                        await db.execute(delete(ChatMessage).where(ChatMessage.conversation_id == cid))
                    await db.execute(delete(Conversation).where(Conversation.user_id == uid))
                    await db.execute(delete(UserSession).where(UserSession.user_id == uid))
                    await db.execute(delete(UserApiKey).where(UserApiKey.user_id == uid))
                    await db.execute(delete(User).where(User.id == uid))


@asynccontextmanager
async def _logged_in_client(email: str):
    """登录态的 AsyncClient 上下文：进出各一次 open/close，避免重复 open。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/auth/login", json=_login_payload(email))
        assert response.status_code == 200
        yield client


async def test_list_conversations_requires_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/conversations")

    assert response.status_code == 401


async def test_list_conversations_returns_only_mine(pair):
    async with _logged_in_client(pair["email"]) as client:
        response = await client.get("/conversations")

    body = response.json()
    assert response.status_code == 200 and body["code"] == 0
    ids = [row["id"] for row in body["data"]]
    assert set(ids) == {pair["conv1"], pair["conv2"]}
    assert pair["foreign"] not in ids


async def test_list_messages_rejects_foreign_conversation(pair):
    """越权会话：40001 且不暴露「存在但是别人的」——文案与 send_message 一致。"""
    async with _logged_in_client(pair["email"]) as client:
        response = await client.get(f"/conversations/{pair['foreign']}/messages")

    assert response.status_code == 400
    assert response.json()["code"] == ErrorCode.PARAM_INVALID


async def test_list_messages_returns_history_ascending(pair):
    async with _logged_in_client(pair["email"]) as client:
        response = await client.get(f"/conversations/{pair['conv1']}/messages")

    body = response.json()
    assert response.status_code == 200 and body["code"] == 0
    rows = body["data"]
    assert [row["role"] for row in rows] == ["user", "assistant", "user", "assistant"]
    assert [row["id"] for row in rows] == sorted(row["id"] for row in rows)
    assert rows[1]["model"] == "fake-model"
    assert rows[0]["model"] is None


async def test_send_message_touches_conversation(pair, monkeypatch):
    """touch 回归：fixture 把两个会话的 update_time 钉在 2020。

    给 conv1（id 更小）发一条消息：touch 生效时 conv1 的 update_time 变成
    当前时间并跳到列表最前；参数换位时 WHERE 落空、update_time 停在 2020，
    且列表仍是 id desc 的顺序（conv2 在前）——两个断言专门抓那个 bug。
    """
    async def fake_call(key, messages, **kwargs):
        return "好的，看机械键盘。", "fake-model"

    monkeypatch.setattr(model_call, "call_model", fake_call)
    async with _logged_in_client(pair["email"]) as client:
        response = await client.post("/chat/message", headers={"X-Requested-With": "price-agent"},
                                     json={"conversation_id": pair["conv1"], "text": "再聊聊键盘"})
        assert response.status_code == 200 and response.json()["code"] == 0
        listed = await client.get("/conversations")

    rows = listed.json()["data"]
    assert rows[0]["id"] == pair["conv1"], "被 touch 的会话应按 update_time 跳到最前"
    touched = next(row for row in rows if row["id"] == pair["conv1"])
    assert datetime.fromisoformat(touched["update_time"]).year >= 2026, \
        "update_time 应被推进到当前时间（换位 bug 下会停留在 2020）"
