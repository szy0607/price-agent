"""RAG 索引任务链路测试。设计依据 docs/RAG索引任务-设计.md。

门槛与 test_group.py 相同：RUN_MYSQL_KEY_TESTS=1 + 已 `alembic upgrade head`
的库。**绝不能真调embedding 模型**——走用户自己的 API Key，真调一次花一次钱，
所以 embed_texts 一律monkeypatch。

## 本文件锁的四条「漏了不报错」

1. **向量库不可用不能把已成功的操作报成失败**（2026-10-17 实测踩到：
   PG 引擎没起 → delete_by_source 抛 BizError 穿透到 router →
   `DELETE /cart/items/{id}/delete` 返回 400，3 个测试因此变红）
2. **不可重试的embedding 错误不烧 arq 额度**（key 已死 / 维度配置错，
   重试 3 次得到的还是同一个错）
3. **可重试的才退避**（抛 Retry，defer 递增）
4. **响应体解析失败被归一化**（厂商返 HTML 错误页时抛的是裸 JSONDecodeError，
   会被 except EmbeddingError 漏掉 → arq 既不重试也不改状态）

## 为什么大量用「直接驱动 sync_one」而不是打 HTTP

异步任务的行为在 HTTP 层看不清（httpx.ASGITransport 会把响应缓冲成一坨，
测不了「边收边断」）。sync_one 是个 async 函数，直接调它能精确断言：
arq 重试了几次、状态最终是什么。
"""
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
from app.core.security import hash_password
from app.database.session import async_engine, async_session_local
from app.main import app
from app.models import CartItem, OwnedItem, PurchaseRecord, User, UserSession
from app.services import embedding_client, index_service

pytestmark = pytest.mark.asyncio(loop_scope="module")
PASSWORD = "testPassword123"
WRITE = {"X-Requested-With": "price-agent"}


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def dispose_test_engine():
    yield
    await async_engine.dispose()


def _login_payload(email: str) -> dict:
    salt = secrets.token_hex(8)
    ts = str(int(time.time()))
    answer = "TEST23"
    sig = hmac.new(settings.captcha_key.encode(), f"{salt}.{ts}.{answer}".encode(),
                   hashlib.sha256).hexdigest()
    return {"user_email": email, "password": PASSWORD,
            "captcha_token": f"{salt}.{ts}.{sig}", "captcha_code": answer}


def _require_mysql() -> None:
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")


@pytest_asyncio.fixture(loop_scope="module")
async def shopper():
    _require_mysql()
    async with async_session_local() as db:
        async with db.begin():
            user = User(user_email=f"index-test-{uuid.uuid4().hex}@example.invalid",
                        username="index-test", password_hash=hash_password(PASSWORD))
            db.add(user)
            await db.flush()
            uid = user.id
    try:
        yield uid
    finally:
        async with async_session_local() as db:
            async with db.begin():
                for model in (CartItem, OwnedItem, PurchaseRecord):
                    await db.execute(delete(model).where(model.user_id == uid))
                await db.execute(delete(UserSession).where(UserSession.user_id == uid))
                await db.execute(delete(User).where(User.id == uid))


async def _mk_cart_item(uid: int, name: str = "测试商品") -> int:
    async with async_session_local() as db:
        async with db.begin():
            row = CartItem(user_id=uid, name=name, specs={"品牌": "测试"})
            db.add(row)
            await db.flush()
            return row.id


async def _status_of(model, item_id: int) -> str | None:
    async with async_session_local() as db:
        return await db.scalar(select(model.index_status).where(model.id == item_id))


async def _cleanup_items(uid: int, *pairs: tuple[str, int]) -> None:
    async with async_session_local() as db:
        async with db.begin():
            for stype, iid in pairs:
                model = index_service._MODELS[stype]
                await db.execute(delete(model).where(model.id == iid, model.user_id == uid))


# ---------- 1. 向量库不可用，主流程必须照常成功 ----------

async def test_delete_succeeds_when_pg_unavailable(shopper, monkeypatch):
    """🔴 回归（2026-10-17 实测踩到）：PG 不可用不能把「删商品」报成失败。

    改之前：vector_repo.delete_by_source 内部要开 PG session，PG 引擎没起时
    get_pg_session() 抛 BizError，一路穿透 router → DELETE 返回 400。
    商品其实已经从 MySQL 删了，只是接口告诉用户「失败」。
    """
    item_id = await _mk_cart_item(shopper, "删向量失败的商品")

    async def boom(*args, **kwargs):
        raise RuntimeError("模拟 PG 引擎未启动")


    # 只 mock delete_by_source。enqueue_sync 保持真实实现（Redis 实际可用）——
    # 它自己会吞投递失败，这里再 mock 反而会让 router await 一个裸协程。
    monkeypatch.setattr(index_service.vector_repo, "delete_by_source", boom)

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://testserver") as client:
        assert (await client.post("/auth/login",
                                  json=_login_payload(await _email_of(shopper)))).status_code == 200
        resp = await client.delete(f"/cart/items/{item_id}/delete", headers=WRITE)

    assert resp.status_code == 200, (
        f"PG/Redis 都不可用时删除仍应成功，实际 {resp.status_code} {resp.text[:80]}")
    async with async_session_local() as db:
        assert await db.get(CartItem, item_id) is None, "商品应已从 MySQL 删除"


async def test_transfer_succeeds_when_pg_unavailable(shopper, monkeypatch):
    """transfer 同理：向量库不可用不能把「标记已购买」报成失败。"""
    item_id = await _mk_cart_item(shopper, "转移商品")

    async def boom(*args, **kwargs):
        raise RuntimeError("模拟 PG 引擎未启动")

    monkeypatch.setattr(index_service.vector_repo, "delete_by_source", boom)

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://testserver") as client:
        assert (await client.post("/auth/login",
                                  json=_login_payload(await _email_of(shopper)))).status_code == 200
        resp = await client.post(f"/cart/items/{item_id}/transform",
                                 json={"price": 99, "platform": "京东"}, headers=WRITE)

    assert resp.status_code == 200, (
        f"实际 {resp.status_code} {resp.text[:80]}")
    async with async_session_local() as db:
        assert await db.get(CartItem, item_id) is None
    await _cleanup_owned_and_purchase(shopper)


async def _email_of(uid: int) -> str:
    async with async_session_local() as db:
        return await db.scalar(select(User.user_email).where(User.id == uid))


async def _cleanup_owned_and_purchase(uid: int) -> None:
    async with async_session_local() as db:
        async with db.begin():
            for model in (OwnedItem, PurchaseRecord):
                await db.execute(delete(model).where(model.user_id == uid))


# ---------- 2/3. 错误分类：不可重试不烧额度，可重试才退避 ----------

async def test_key_rejected_marks_failed_without_retry(shopper, monkeypatch):
    """🔴 key 被厂商拒绝 → **arq 重试 0 次**，直接置 FAILED。

    不可重试的原因：embed_texts 内部已 mark_invalid 把 key 标死，
    重试 3 次得到的还是同一个错，白烧 max_tries 额度。
    """
    item_id = await _mk_cart_item(shopper, "key 被拒的商品")

    async def fake_embed(user_id, texts, session):
        raise embedding_client.EmbeddingKeyRejected("向量模型的 key 已被厂商拒绝，已标记为失效")

    monkeypatch.setattr(embedding_client, "embed_texts", fake_embed)

    # 真的调sync_one：不该抛 Retry（抛了才算错）
    await index_service.sync_one({"job_try": 1}, shopper, "cart", item_id)

    assert await _status_of(CartItem, item_id) == index_service.FAILED, (
        "不可重试的错误应直接置 FAILED，不该停在 RUNNING 等 reaper")
    await _cleanup_items(shopper, ("cart", item_id))


async def test_dim_mismatch_marks_failed_without_retry(shopper, monkeypatch):
    """维度配置错同理——重试到天荒地老也是同一个结果。"""
    item_id = await _mk_cart_item(shopper, "维度错的商品")

    async def fake_embed(user_id, texts, session):
        raise embedding_client.EmbeddingDimMismatch("向量模型返回的向量维度与配置不一致")

    monkeypatch.setattr(embedding_client, "embed_texts", fake_embed)
    await index_service.sync_one({"job_try": 1}, shopper, "cart", item_id)

    assert await _status_of(CartItem, item_id) == index_service.FAILED
    await _cleanup_items(shopper, ("cart", item_id))


async def test_call_failed_raises_retry_with_backoff(shopper, monkeypatch):
    """可重试的错误 → 抛 Retry，且 defer 随 job_try 递增（5/10/15 秒）。

    抛 Retry 后业务表状态**停在 RUNNING** —— 这是有意的：
    arq 重试用尽不会改业务表，等 reaper 判超时（index_stale_seconds）自愈。
    """
    item_id = await _mk_cart_item(shopper, "网络抖动的商品")

    async def fake_embed(user_id, texts, session):
        raise embedding_client.EmbeddingCallFailed("向量模型调用失败")

    monkeypatch.setattr(embedding_client, "embed_texts", fake_embed)

    from arq import Retry

    with pytest.raises(Retry) as first:
        await index_service.sync_one({"job_try": 1}, shopper, "cart", item_id)
    # arq 0.28 的 Retry 把退避记在 defer_score，**单位是毫秒**（旧版属性名是 defer）
    assert first.value.defer_score == 5_000, (
        f"第一次应退避 5000ms=5s，实际 {first.value.defer_score}ms")
    assert await _status_of(CartItem, item_id) == index_service.RUNNING, (
        "可重试错误应停在 RUNNING 等 arq/reaper，不该置 FAILED")

    with pytest.raises(Retry) as third:
        await index_service.sync_one({"job_try": 3}, shopper, "cart", item_id)
    assert third.value.defer_score == 15_000, (
        f"第三次应退避 15000ms=15s，实际 {third.value.defer_score}ms")

    await _cleanup_items(shopper, ("cart", item_id))


async def test_json_parse_error_normalized_to_call_failed(shopper, monkeypatch):
    """🔴 厂商返回 HTML 错误页时，异常必须是 EmbeddingCallFailed。

    改之前抛的是裸 JSONDecodeError —— 不是 EmbeddingError 的子类，
    会被 sync_one 的 except 漏掉，变成「未知错误」：arq 既不重试也不改状态，
    只能等 reaper 超时 10 分钟。
    """
    import httpx

    class FakeResp:
        status_code = 200

        @staticmethod
        def json():
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    class FakeClient:
        async def post(self, *args, **kwargs):
            return FakeResp()

    monkeypatch.setattr(embedding_client, "get_http_client", lambda: FakeClient())
    # key 要能查到才会走到解析这步——monkeypatch 掉key 服务
    from app.services import embedding_key_service
    from app.services.api_key_service import KeyRecord

    async def fake_key(user_id, session):
        return KeyRecord(key_id=1, provider="t", base_url="https://api.deepseek.com",
                         api_key="sk-x", model_name="m")

    monkeypatch.setattr(embedding_key_service, "key_for_embedding", fake_key)

    with pytest.raises(embedding_client.EmbeddingCallFailed):
        await embedding_client.embed_texts(1, ["随便什么"], None)


# ---------- 4. 顺序约束：PG 写失败绝不能置 SYNCED ----------

async def test_pg_write_failure_never_marks_synced(shopper, monkeypatch):
    """🔴 这条锁死设计的地基：**只有 PG 写入成功才能置 SYNCED**。

    顺序反过来的后果：PG 写失败但状态已标 SYNCED → RAG 认为可检索 →
    检索命中一条不存在的向量 → 模型拿空数据回答，**且不报错**。
    """
    item_id = await _mk_cart_item(shopper, "PG 写失败的商品")

    async def fake_embed(user_id, texts, session):
        return [[0.0] * 1024]

    async def boom(*args, **kwargs):
        raise RuntimeError("模拟 PG 写失败")

    monkeypatch.setattr(embedding_client, "embed_texts", fake_embed)
    monkeypatch.setattr(index_service.vector_repo, "upsert_embedding", boom)

    with pytest.raises(RuntimeError):
        await index_service.sync_one({"job_try": 1}, shopper, "cart", item_id)

    status = await _status_of(CartItem, item_id)
    assert status != index_service.SYNCED, (
        f"PG 写失败却标了 SYNCED —— 这是地基约束被破坏，实际 status={status}")
    await _cleanup_items(shopper, ("cart", item_id))


async def test_pg_write_success_marks_synced(shopper, monkeypatch):
    """正向：PG 写成功 → SYNCED + index_time 有值。"""
    item_id = await _mk_cart_item(shopper, "正常索引的商品")

    async def fake_embed(user_id, texts, session):
        return [[0.0] * 1024]

    async def fake_upsert(*args, **kwargs):
        return None

    monkeypatch.setattr(embedding_client, "embed_texts", fake_embed)
    monkeypatch.setattr(index_service.vector_repo, "upsert_embedding", fake_upsert)

    await index_service.sync_one({"job_try": 1}, shopper, "cart", item_id)

    assert await _status_of(CartItem, item_id) == index_service.SYNCED
    async with async_session_local() as db:
        row = await db.get(CartItem, item_id)
        assert row.index_time is not None, "置 SYNCED 时必须写 index_time"
    await _cleanup_items(shopper, ("cart", item_id))


# ---------- 5. 空文本与目标消失 ----------

async def test_target_gone_deletes_vector_copy(shopper, monkeypatch):
    """目标已被删（worker 慢半拍）→ 删副本收工，不报错。"""
    item_id = await _mk_cart_item(shopper, "会被删掉的商品")
    async with async_session_local() as db:
        async with db.begin():
            row = await db.get(CartItem, item_id)
            await db.delete(row)

    called = {}

    async def fake_delete(user_id, stype, iid):
        called["args"] = (user_id, stype, iid)

    monkeypatch.setattr(index_service.vector_repo, "delete_by_source", fake_delete)
    # 不该调 embedding（目标都没了）
    async def must_not_call(*args, **kwargs):
        raise AssertionError("目标已消失，不该调 embedding")

    monkeypatch.setattr(embedding_client, "embed_texts", must_not_call)

    await index_service.sync_one({"job_try": 1}, shopper, "cart", item_id)
    assert called.get("args") == (shopper, "cart", item_id), called


async def test_blank_text_marks_synced_not_pending(shopper, monkeypatch):
    """全空物品（name/specs/note 都空）→ 标 SYNCED，不是 PENDING。

    留 PENDING 会被 reaper 永远捞起来反复投递。
    """
    item_id = await _mk_cart_item(shopper, "")
    async with async_session_local() as db:
        async with db.begin():
            row = await db.get(CartItem, item_id)
            row.specs = {}
            row.note = None

    async def must_not_call(*args, **kwargs):
        raise AssertionError("空文本不该调 embedding")

    monkeypatch.setattr(embedding_client, "embed_texts", must_not_call)
    await index_service.sync_one({"job_try": 1}, shopper, "cart", item_id)

    assert await _status_of(CartItem, item_id) == index_service.SYNCED
    await _cleanup_items(shopper, ("cart", item_id))


# ---------- 6. 兼容性：子类仍能被 except EmbeddingError 捕到 ----------

def test_error_subclasses_inherit_base():
    """B 批（embedding_client 原有代码）若写 except EmbeddingError 仍能工作。"""
    for sub in (embedding_client.EmbeddingKeyRejected,
                embedding_client.EmbeddingCallFailed,
                embedding_client.EmbeddingDimMismatch):
        assert issubclass(sub, embedding_client.EmbeddingError), sub
        try:
            raise sub("x")
        except embedding_client.EmbeddingError:
            pass  # 能捕到即达标


# ---------- 7. enqueue_sync 永不抛 ----------

async def test_enqueue_never_raises(shopper, monkeypatch):
    """Redis 不可用时 enqueue_sync 返回 False 而不抛——投递在事务外，
    抛出去会让上层 500，用户以为保存失败但数据其实已经存上了。"""
    async def boom():
        raise RuntimeError("模拟 Redis 不可用")

    monkeypatch.setattr(index_service, "get_pool", boom)
    assert await index_service.enqueue_sync(shopper, "cart", 999999) is False


async def test_enqueue_uses_idempotent_job_id(shopper, monkeypatch):
    """_job_id 必须是 idx:{类型}:{id}——arq 同 ID 已在队列时返回 None，
    这是「同一商品连改 5 次只排一次」的天然去重依据。"""
    seen = {}

    class FakePool:
        async def enqueue_job(self, fn, *args, **kwargs):
            seen["fn"] = fn
            seen["args"] = args
            seen["kwargs"] = kwargs
            return object()

    async def fake_pool():
        return FakePool()

    monkeypatch.setattr(index_service, "get_pool", fake_pool)
    assert await index_service.enqueue_sync(shopper, "owned", 42) is True
    assert seen["fn"] == "sync_one"
    assert seen["args"] == (shopper, "owned", 42)
    assert seen["kwargs"]["_job_id"] == "idx:owned:42"


# ---------- 8. reaper 捞取范围 ----------

async def test_reap_picks_pending_and_failed_only(shopper, monkeypatch):
    """reaper 必须捞 PENDING + FAILED，但**不能捞正常的 SYNCED**。"""
    pending = await _mk_cart_item(shopper, "待索引")
    failed = await _mk_cart_item(shopper, "失败过")
    synced = await _mk_cart_item(shopper, "已索引")
    async with async_session_local() as db:
        async with db.begin():
            row = await db.get(CartItem, failed)
            row.index_status = index_service.FAILED
            row = await db.get(CartItem, synced)
            row.index_status = index_service.SYNCED

    picked: list[tuple] = []

    async def fake_enqueue(uid, stype, iid):
        picked.append((uid, stype, iid))
        return True

    monkeypatch.setattr(index_service, "enqueue_sync", fake_enqueue)
    await index_service.reap_once()

    # 只看自己这个 user 的行：库里还有大宋自己的 67 条 PENDING 存量
    ids = {i for u, _, i in picked if u == shopper}
    assert pending in ids, "PENDING 应被捞起"
    assert failed in ids, "FAILED 应被捞起（key 修好后要有入口重试）"
    assert synced not in ids, "SYNCED 是完成态，不该被反复重投"
    await _cleanup_items(shopper, ("cart", pending), ("cart", failed), ("cart", synced))