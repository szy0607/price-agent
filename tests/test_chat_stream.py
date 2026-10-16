"""流式输出（SSE）测试。设计依据 docs/流式输出-设计.md。

门槛与 test_chat_conversations.py 相同：RUN_MYSQL_KEY_TESTS=1 + 已
`alembic upgrade head` 的库。模型调用一律 monkeypatch——真调一次花一次钱。

## 为什么大多数用例直接驱动生成器而不是打 HTTP（实测结论）

`httpx.ASGITransport` **会把整个响应缓冲成一坨**再交给客户端：5 帧的流
实测只拿到 1 个 145 字节的 chunk（2026-10-16 探针）。所以走 HTTP 只能测
「状态码对不对」，测不出逐帧时序，也**测不出中途断连**——break 只截断
客户端读取，服务端生成器早已跑完。

因此分两层：
- **生成器层**（`chat_stream.chat_stream`）：三态落库、断连、空输出、并发
  都在这里测——直接控制消费节奏，能真正触发 `GeneratorExit`。
- **HTTP 层**（`POST /chat/stream`）：只测状态码、头、事件顺序是否符合协议。

覆盖（对应设计文档 §7 的 7 项）：
1. 正常完成 → completed
2. 模型异常且有输出 → failed（保存半截）
3. 空输出异常 → **不落 assistant**
4. 主动中断 → interrupted（**必须落库**，设计 §5.9 的核心）
5. 客户端断连后不留悬挂数据
6. 并发：多路流式不因连接池报错
7. trim_trailing_users 回归 + A6 画像不被半截污染（设计 §4.4）
"""
import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid

from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.key_crypto import encrypt
from app.core.security import hash_password
from app.core.rate_limit import _windows
from app.database.session import async_engine, async_session_local
from app.main import app
from app.models import ChatMessage, Conversation, User, UserApiKey, UserProfile, UserSession
from app.repository import chat_repo
from app.schemas.chat_sche import ChatSendInSchema
from app.services import chat_stream, model_call, profile_service

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
async def user():
    """一个带可用默认 key 的测试用户。

    key 是假的（sk-test-...）：模型调用全被 monkeypatch，这个值永不出网。
    但仍必须存在——2026-10-16 起 prepare_chat 会先 key_for_call，缺 key 直接 400。
    """
    _require_mysql()
    async with async_session_local() as db:
        async with db.begin():
            row = User(user_email=f"stream-test-{uuid.uuid4().hex}@example.invalid",
                       username="stream-test", password_hash=hash_password(PASSWORD))
            db.add(row)
            await db.flush()
            uid = row.id
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
                    await db.execute(
                        delete(ChatMessage).where(ChatMessage.conversation_id == cid))
                await db.execute(delete(Conversation).where(Conversation.user_id == uid))
                await db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
                await db.execute(delete(UserSession).where(UserSession.user_id == uid))
                await db.execute(delete(UserApiKey).where(UserApiKey.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))


async def _new_conversation(uid: int, title: str) -> int:
    async with async_session_local() as db:
        async with db.begin():
            row = Conversation(user_id=uid, title=title)
            db.add(row)
            await db.flush()
            return row.id


async def _messages(conv_id: int) -> list[tuple[str, str, str]]:
    async with async_session_local() as db:
        rows = (await db.scalars(
            select(ChatMessage).where(ChatMessage.conversation_id == conv_id)
            .order_by(ChatMessage.id))).all()
    return [(r.role, r.status, r.content) for r in rows]


async def _assistant_rows(conv_id: int) -> list[tuple[str, str]]:
    return [(status, content) for role, status, content in await _messages(conv_id)
            if role == "assistant"]


def _parse_frames(frames: list[str]) -> list[tuple[str, dict]]:
    out = []
    for frame in frames:
        head, _, payload = frame.partition("data: ")
        out.append((head.removeprefix("event: ").strip(), json.loads(payload)))
    return out


async def _drain(uid: int, text: str = "测试提问") -> tuple[list[tuple[str, dict]], int]:
    """完整消费一条流，返回 (事件序列, conversation_id)。

    ⚠️ **必须消费到底**。中途 break 等于取消生成器——阶段③（落库）不会跑，
    rows 会是空的。踩过这个坑：一度误判成「落库全失败」。
    """
    from fastapi import BackgroundTasks

    frames = []
    async for chunk in chat_stream.chat_stream(
            uid, ChatSendInSchema(text=text), BackgroundTasks()):
        frames.append(chunk)
    events = _parse_frames(frames)
    cid = events[0][1]["conversation_id"] if events and events[0][0] == "meta" else None
    return events, cid


# ---------- 1. 正常完成 ----------

async def test_stream_completed_persists_assistant(user, monkeypatch):
    async def fake_stream(key, messages, **kwargs):
        for piece in ["根据", "你的", "需求，", "推荐"]:
            yield piece

    monkeypatch.setattr(model_call, "stream_model", fake_stream)
    events, cid = await _drain(user)

    assert [name for name, _ in events] == ["meta", "delta", "delta", "delta", "delta", "done"]
    assert "".join(d["text"] for n, d in events if n == "delta") == "根据你的需求，推荐"
    assert events[-1][1]["status"] == chat_repo.STATUS_COMPLETED

    got = await _assistant_rows(cid)
    assert got == [(chat_repo.STATUS_COMPLETED, "根据你的需求，推荐")], got


# ---------- 2. 模型异常且已有部分输出 ----------

async def test_stream_model_error_saves_partial_as_failed(user, monkeypatch):
    async def fake_stream(key, messages, **kwargs):
        yield "已经说了几句"
        raise model_call.ModelCallError("模型服务已欠费，请前往对应平台充值后重试")

    monkeypatch.setattr(model_call, "stream_model", fake_stream)
    events, cid = await _drain(user)

    names = [n for n, _ in events]
    assert "error" in names and names[-1] == "done", names
    err = next(d for n, d in events if n == "error")
    assert "欠费" in err["error"], "错误文案必须是用户可读中文，不是英文异常"
    assert events[-1][1]["status"] == chat_repo.STATUS_FAILED

    got = await _assistant_rows(cid)
    assert got == [(chat_repo.STATUS_FAILED, "已经说了几句")], (
        "半截输出必须保留并标 failed，不能整条丢掉")


# ---------- 3. 空输出异常：不落 assistant ----------

async def test_stream_empty_output_persists_no_assistant(user, monkeypatch):
    async def fake_stream(key, messages, **kwargs):
        raise model_call.ModelCallError("模型调用失败")
        yield  # pragma: no cover

    monkeypatch.setattr(model_call, "stream_model", fake_stream)
    events, cid = await _drain(user)

    assert events[-1][1]["status"] == chat_repo.STATUS_FAILED
    assert await _assistant_rows(cid) == [], (
        "一个 token 都没收到就不该建 assistant 行：content 是 NOT NULL，"
        "空串进上下文会让模型看到空回复")


# ---------- 4. 主动中断：🔴 必须落库（设计 §5.9 核心）----------

async def test_stream_interrupt_persists_interrupted(user, monkeypatch):
    """用户 abort → 服务端落 interrupted。

    这条最容易漏：漏了就表现为「前端显示已停止，刷新后消息消失」。

    ⚠️ **两个实测结论，别照着直觉写**：
    1. `async for ... : break` 不会同步抛 GeneratorExit——异步生成器的收尾要等
       `aclose()` 或 GC finalizer，晚一拍。break 后立刻断言会「DID NOT RAISE」。
    2. `await gen.aclose()` **也不会**把 GeneratorExit 抛回调用方：它把异常投进
       生成器内部，生成器处理完（重新 raise）后 aclose() 正常返回 None。
       所以这里**只断言落库结果，不断言抛什么**。
    """
    async def fake_stream(key, messages, **kwargs):
        for piece in ["说了", "几句", "不该说完"]:
            yield piece

    monkeypatch.setattr(model_call, "stream_model", fake_stream)
    from fastapi import BackgroundTasks

    gen = chat_stream.chat_stream(user, ChatSendInSchema(text="测中断"), BackgroundTasks())
    async for frame in gen:
        # 从 meta 帧拿本次的真实 conversation_id（懒创建会新建会话）
        if frame.startswith("event: meta"):
            cid = json.loads(frame.partition("data: ")[2])["conversation_id"]
            continue
        break               # 只收第一帧 delta 就断开
    await gen.aclose()      # 显式收尾，确保 GeneratorExit 分支真的跑完

    rows = []
    for _ in range(40):
        # 必须按 cid 过滤：查全库最新一条会拿到上一个用例的 completed 行
        rows = await _assistant_rows(cid)
        if rows:
            break
        await asyncio.sleep(0.05)
    assert rows, "中断后必须落库（设计文档 §5.9）"
    assert rows == [(chat_repo.STATUS_INTERRUPTED, "说了")], (
        f"应落 interrupted + 中断前已生成的文本，实际 {rows}")


# ---------- 5. 客户端断连：生成器异常退出后不留悬挂数据 ----------

async def test_stream_client_disconnect_leaves_no_orphan(user, monkeypatch):
    """断连后：那一轮的 user 消息仍在（请求开始就入库），但不能有 completed 的 assistant。

    「不能有」比「必须有」更重要——如果断连被误判成正常完成，会留下一个
    看起来完整、实际只说了半句的回答。
    """
    async def fake_stream(key, messages, **kwargs):
        yield "半句"
        raise model_call.ModelCallError("模型调用失败")

    monkeypatch.setattr(model_call, "stream_model", fake_stream)
    events, cid = await _drain(user)

    assert events[-1][1]["status"] == chat_repo.STATUS_FAILED
    got = await _assistant_rows(cid)
    assert len(got) == 1 and got[0][0] == chat_repo.STATUS_FAILED


# ---------- 6. 并发：多路流式不因连接池/串行化失败 ----------

async def test_stream_concurrent_requests_do_not_conflict(user, monkeypatch):
    """5 路并发，各自的会话与消息互不串。

    这是三段式 session 的回归：若生成阶段仍持有 session，池子（size=10）
    会被慢生成占住，并发一高就 pool_timeout。
    阶段②各路用不同内容的假流，让「串了内容」也能被抓出来。
    """
    async def fake_stream(key, messages, **kwargs):
        # 每路的标识取自本轮用户输入尾部；yield 3 次同一标识，落库文本应为 3 份
        marker = messages[-1]["content"][-6:]
        for _ in range(3):
            yield marker
            await asyncio.sleep(0)

    monkeypatch.setattr(model_call, "stream_model", fake_stream)
    # 限流是 6 次/60 秒，5 路并发正好卡在边缘——清掉窗口避免误伤
    _windows.clear()

    conv_ids = [await _new_conversation(user, f"并发空会话-{i}") for i in range(5)]
    from fastapi import BackgroundTasks

    async def one(text: str) -> tuple[str, list[tuple[str, str]]]:
        frames = []
        async for chunk in chat_stream.chat_stream(
                user, ChatSendInSchema(text=text), BackgroundTasks()):
            frames.append(chunk)
        cid = _parse_frames(frames)[0][1]["conversation_id"]
        return cid, await _assistant_rows(cid)

    results = await asyncio.gather(*[one(f"问题{i}号标记") for i in range(5)])

    assert len(results) == 5
    cids = [cid for cid, _ in results]
    assert len(set(cids)) == 5, f"5 路并发应建5 个独立会话，实际 {cids}"

    for i, (cid, rows) in enumerate(results):
        assert len(rows) == 1, f"第 {i} 路应恰好一条 assistant，实际 {rows}"
        assert rows[0][0] == chat_repo.STATUS_COMPLETED
        expected = f"问题{i}号标记" * 3
        assert rows[0][1] == expected, (
            f"第 {i} 路内容不符：期望 {expected!r}，实际 {rows[0][1]!r}"
            "——串了就说明阶段②共用了状态")

    # 预建的空会话不应被写入（懒创建走的是新 id）
    for i, cid in enumerate(conv_ids):
        rows = await _messages(cid)
        assert len(rows) == 0, f"预建会话 {cid} 不该收到消息，实际 {rows}"


# ---------- 7. trim_trailing_users 回归 + A6 画像不被污染（设计 §4.4）----------

async def test_context_excludes_failed_and_interrupted(user):
    """🔴 三套过滤规则的核心断言（设计 §0/§4）。

    构造 user → failed(半截) → interrupted(半截) → user 的序列，
    断言：
      - messages_for_context：只剩 completed，**半截内容一个都不许出现**
      - trim_trailing_users：末尾连续 user 被砍掉（序列必须合法）
      - messages_for_profile：failed 整条排除、interrupted 只剩事件占位
    这几条坏了不报错——画像只是慢慢变怪，所以必须锁死。
    """
    cid = await _new_conversation(user, "过滤规则")
    async with async_session_local() as db:
        async with db.begin():
            db.add_all([
                ChatMessage(user_id=user, conversation_id=cid, role="user",
                            content="第一个问题"),
                ChatMessage(user_id=user, conversation_id=cid, role="assistant",
                            content="正常回答", model="m", status="completed"),
                # 下面两条的半截内容都带独特标记，断言里搜这个标记
                ChatMessage(user_id=user, conversation_id=cid, role="assistant",
                            content="失败半截XYZ", model="m", status="failed"),
                ChatMessage(user_id=user, conversation_id=cid, role="assistant",
                            content="中断半截ABC", model="m", status="interrupted"),
                ChatMessage(user_id=user, conversation_id=cid, role="user",
                            content="最后的问题"),
            ])

    async with async_session_local() as db:
        ctx = await chat_repo.messages_for_context(user, cid, 12, db)
        prof = await chat_repo.messages_for_profile(user, cid, 12, db)
        shown = await chat_repo.list_messages(user, cid, 12, db)

    ctx_text = " ".join(m["content"] for m in ctx)
    assert "XYZ" not in ctx_text and "ABC" not in ctx_text, (
        f"failed/interrupted 的半截内容绝不能进模型上下文：{ctx_text!r}")
    assert [m["content"] for m in ctx] == ["第一个问题", "正常回答", "最后的问题"]

    # trim：末尾连续 user 被砍掉 → 剩 user/assistant，最后那条 user 不进模型
    trimmed = chat_repo.trim_trailing_users(ctx)
    assert [m["content"] for m in trimmed] == ["第一个问题", "正常回答"], trimmed
    assert not (trimmed and trimmed[-1]["role"] == "user"), (
        "部分模型不接受连续两条 user")

    prof_text = " ".join(m["content"] for m in prof)
    assert "XYZ" not in prof_text, "failed 的半截自述不能进 A6 画像"
    assert "ABC" not in prof_text, "interrupted 的半截文本不能进 A6 画像"
    assert "用户中断了上一轮回答" in prof_text, (
        "但「用户主动打断」这个事件本身要保留——它是高价值信号（设计 §0）")

    # list_messages：忠实记录，三态全留，前端刷新后角标还在
    assert [row.status for row in shown] == [
        "completed", "completed", "failed", "interrupted", "completed"], shown


async def test_a6_input_text_excludes_partial_content(user, monkeypatch):
    """A6 真正喂给模型的那段文本里，不含半截内容。

    比上一条更进一步：上一条测 repo 返回值，这条测**拼进 prompt 的最终文本**——
    拼接逻辑（截断、角色标签）出错时只有这里能抓到。
    """
    cid = await _new_conversation(user, "A6 污染")
    async with async_session_local() as db:
        async with db.begin():
            db.add_all([
                ChatMessage(user_id=user, conversation_id=cid, role="user",
                            content="我一直只用静音的"),
                ChatMessage(user_id=user, conversation_id=cid, role="assistant",
                            content="半截内容MARKER77", model="m", status="failed"),
                ChatMessage(user_id=user, conversation_id=cid, role="user",
                            content="所以推荐静音的吧"),
            ])

    captured: dict = {}

    async def fake_call(key, messages, **kwargs):
        captured["prompt"] = messages[-1]["content"]
        return '{"updated": false}', "fake-model"

    monkeypatch.setattr(model_call, "call_model", fake_call)
    await profile_service.refresh_profile(user, cid)

    prompt = captured.get("prompt", "")
    assert prompt, "A6 应被调用并拿到输入"
    assert "MARKER77" not in prompt, (
        f"A6 输入里混进了 failed 的半截内容，画像会被污染：{prompt!r}")
    assert "我一直只用静音的" in prompt, "用户真实表达必须保留"


# ---------- HTTP 层：协议头与事件顺序 ----------

@asynccontextmanager
async def _logged_in_client(uid: int):
    async with async_session_local() as db:
        email = await db.scalar(select(User.user_email).where(User.id == uid))
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://testserver") as client:
        response = await client.post("/auth/login", json=_login_payload(email))
        assert response.status_code == 200
        yield client


async def test_stream_endpoint_headers_and_order(user, monkeypatch):
    """HTTP 层：Content-Type 是 text/event-stream，防缓冲头在，meta 先于任何 delta。"""
    async def fake_stream(key, messages, **kwargs):
        yield "你好"

    monkeypatch.setattr(model_call, "stream_model", fake_stream)
    _windows.clear()

    async with _logged_in_client(user) as client:
        response = await client.post(
            "/chat/stream",
            headers={"X-Requested-With": "price-agent"},
            json={"conversation_id": None, "text": "端到端"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    # 这三个头缺一个，流就可能被代理攒成一坨再一次性吐出
    assert response.headers.get("x-accel-buffering") == "no"
    assert "no-cache" in response.headers.get("cache-control", "")

    events = _parse_frames([f for f in response.text.split("\n\n") if f.strip()])
    assert events[0][0] == "meta", "meta 必须先发，前端据此把草稿标题转正"
    assert events[-1][0] == "done"
    names = [n for n, _ in events]
    assert names.index("meta") < names.index("delta") < names.index("done")


async def test_stream_endpoint_requires_origin_header(user, monkeypatch):
    """无 X-Requested-With 必须 40001——require_same_origin_write 挂在流式端点上。

    这条决定了客户端**必须用 fetch 带自定义头**，也就顺带解释了「禁止
    EventSource」（它不支持自定义头，设计文档 §5.8）。
    """
    _windows.clear()
    async with _logged_in_client(user) as client:
        response = await client.post("/chat/stream",
                                     json={"conversation_id": None, "text": "缺头"})

    assert response.status_code == 400
    assert response.json()["code"] == 40001