"""向量模型 key 与切片纯函数测试。

纯函数部分任何环境都能跑；DB 探针需要一台已 `alembic upgrade head` 的一次性 MySQL：

    RUN_MYSQL_KEY_TESTS=1 python -m pytest tests/test_embedding_key.py -v

覆盖重点：切片口径（name+specs+note、换行折叠、空值键丢弃）、
向量 key 的默认互斥 / 归属校验 / 删除不转移 / key_for_embedding 三种报错口径。
每个 DB 探针自包含（自己建自己的 key），不依赖跨测试状态。
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.core.errors import BizError
from app.database.session import async_engine, async_session_local
from app.models import User, UserEmbeddingKey
from app.services import embedding_key_service
from app.services.embed_slice import build_item_text
from app.schemas.setting_sche import EmbeddingKeyInSchema


# ---------- 纯函数：切片（不需要数据库） ----------

def test_slice_full():
    out = build_item_text("iPhone 16 Pro Max",
                          {"品牌": "Apple", "存储": "512GB"},
                          "主力机备用")
    assert out == "iPhone 16 Pro Max 品牌: Apple；存储: 512GB 主力机备用"


def test_slice_name_only():
    assert build_item_text("索尼 WH-1000XM5", None, None) == "索尼 WH-1000XM5"


def test_slice_flattens_newlines_in_values():
    out = build_item_text("A\nB", {"备注": "第一行\n第二行"}, None)
    assert "\n" not in out
    assert out == "A B 备注: 第一行 第二行"


def test_slice_drops_blank_valued_keys():
    out = build_item_text("X", {"有值": "v", "空值": "", "None值": None}, None)
    assert out == "X 有值: v"


def test_slice_all_empty():
    assert build_item_text("", {}, "") == ""
    assert build_item_text("", None, None) == ""


def test_slice_nonstring_specs_values():
    out = build_item_text("X", {"重量": 1.5, " tags": ["a", "b"]}, None)
    assert "重量: 1.5" in out and "tags: ['a', 'b']" in out


# ---------- DB 探针：向量 key（门控 RUN_MYSQL_KEY_TESTS=1） ----------

@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def dispose_test_engine():
    yield
    await async_engine.dispose()


def _in_schema(provider="qwen", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
               api_key="sk-embed-test-0001", model_name="qwen3.7-text-embedding-flash"):
    return EmbeddingKeyInSchema(provider=provider, base_url=base_url,
                                api_key=api_key, model_name=model_name)


@pytest_asyncio.fixture(loop_scope="module")
async def two_users():
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")
    ids = []
    try:
        async with async_session_local() as db:
            async with db.begin():
                for _ in range(2):
                    user = User(user_email=f"ek-test-{uuid.uuid4().hex}@example.invalid",
                                username="ek-test", password_hash="unused")
                    db.add(user)
                    await db.flush()
                    ids.append(user.id)
        yield ids
    finally:
        async with async_session_local() as db:
            async with db.begin():
                await db.execute(delete(UserEmbeddingKey).where(UserEmbeddingKey.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))


@pytest.mark.asyncio(loop_scope="module")
async def test_add_sets_default_and_bumps_previous(two_users):
    uid = two_users[0]
    async with async_session_local() as db:
        first = await embedding_key_service.add_embedding_key(_in_schema(), uid, db)
        assert first.is_default is True
        second = await embedding_key_service.add_embedding_key(
            _in_schema(api_key="sk-embed-test-0002"), uid, db)
        assert second.is_default is True
        await db.refresh(first)
        assert first.is_default is False
        record = await embedding_key_service.key_for_embedding(uid, db)
        assert record.key_id == second.id
        assert record.api_key == "sk-embed-test-0002"
        assert record.model_name == "qwen3.7-text-embedding-flash"


@pytest.mark.asyncio(loop_scope="module")
async def test_no_embedding_key_errors(two_users):
    uid = two_users[1]
    async with async_session_local() as db:
        with pytest.raises(BizError) as exc:
            await embedding_key_service.key_for_embedding(uid, db)
        assert "尚未配置向量模型" in str(exc.value)


@pytest.mark.asyncio(loop_scope="module")
async def test_invalid_default_key_errors(two_users):
    uid = two_users[0]
    async with async_session_local() as db:
        await embedding_key_service.add_embedding_key(_in_schema(), uid, db)
        rows = await embedding_key_service.list_embedding_keys(uid, db)
        await embedding_key_service.mark_invalid(rows[-1].id, uid, db)
        with pytest.raises(BizError) as exc:
            await embedding_key_service.key_for_embedding(uid, db)
        assert "已失效" in str(exc.value)


@pytest.mark.asyncio(loop_scope="module")
async def test_ownership_other_users_key_not_found(two_users):
    owner, other = two_users[0], two_users[1]
    async with async_session_local() as db:
        row = await embedding_key_service.add_embedding_key(_in_schema(), owner, db)
        key_id = row.id  # 先捕获标量：后续 service 的 commit/rollback 会令 row 过期
        with pytest.raises(BizError) as exc:
            await embedding_key_service.update_embedding_key(key_id, _in_schema(), other, db)
        assert "不存在" in str(exc.value)
        with pytest.raises(BizError):
            await embedding_key_service.set_default_embedding_key(key_id, other, db)
        with pytest.raises(BizError):
            await embedding_key_service.delete_embedding_key(key_id, other, db)


@pytest.mark.asyncio(loop_scope="module")
async def test_delete_default_not_transferred(two_users):
    uid = two_users[0]
    async with async_session_local() as db:
        await embedding_key_service.add_embedding_key(_in_schema(), uid, db)
        await embedding_key_service.add_embedding_key(
            _in_schema(api_key="sk-embed-test-0002"), uid, db)
        rows = await embedding_key_service.list_embedding_keys(uid, db)
        await embedding_key_service.delete_embedding_key(rows[-1].id, uid, db)
        left = await embedding_key_service.list_embedding_keys(uid, db)
        assert len(left) == 1
        assert all(r.is_default is False for r in left)
        with pytest.raises(BizError):
            await embedding_key_service.key_for_embedding(uid, db)
