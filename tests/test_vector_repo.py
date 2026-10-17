"""vector_repo.search_similar 的相似度阈值测试。

设计依据：2026-10-17 实测——库里只有 1 条向量时 `top_k` 形同虚设，任何 query
都会「有命中」：实测 '今天天气怎么样' 对一台 iPhone 的相似度是 0.3042，
'送人送什么礼物好' 是 0.1909。阈值不加，RAG 拼给模型的「检索证据」就是噪声。

## 本文件锁的三条

1. **min_score=0.0 与加阈值之前完全一致**（回归：默认不过滤，worker 侧零影响）
2. **min_score 真的进了 SQL 参数**（回归 2026-10-17 踩到的 P0：SQL 里有
   :min_score 而参数字典漏了这个键 → InvalidRequestError，一调就炸）
3. **min_score 越界直接 ValueError**（拦手滑的 -1 / 1.5）

## 为什么全程不连 PG

不连 PG 的原因和 test_index_service.py 不同：那边是不能真调 embedding（花钱），
这边是 **CI/协作者机器上可能压根没起 PG**。阈值逻辑属于「纯参数 + 纯校验」，
用假 session 捕获参数就能锁死，真连 PG 反而让测试变成环境探测器。

真连 PG 的验证留在探针里做（结论：min_score=0.0 → 1 条 0.467；
0.4 → 1 条 0.467；0.99 → 0 条）。
"""
import pytest

from app.repository import vector_repo

pytestmark = pytest.mark.asyncio

# 一条 4 维假向量：值本身无意义，只用来确认它被原样转成 pgvector 字面量
_FAKE_VEC = [0.1, 0.2, 0.3, 0.4]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """只实现 search_similar 用到的两个方法：execute / commit / rollback / close。"""

    def __init__(self, sink: dict, rows):
        self._sink = sink
        self._rows = rows

    async def execute(self, statement, params):
        self._sink["sql"] = str(statement)
        self._sink["params"] = params
        return _FakeResult(self._rows)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass


@pytest.fixture
def captured(monkeypatch):
    """把 _pg_tx 换成假 session，把执行到的 SQL 与参数记进 captured。"""
    sink: dict = {}

    def _install(rows):
        async def _fake_tx(fn):
            session = _FakeSession(sink, rows)
            return await fn(session)

        monkeypatch.setattr(vector_repo, "_pg_tx", _fake_tx)
        return sink

    return _install


# ---------- 1. 回归：min_score=0.0 时行为与加阈值之前完全一致 ----------

async def test_min_score_zero_does_not_filter(captured):
    """min_score=0.0 时卫SQL 不该挡住任何行，且参数原样传下去。"""
    rows = [("owned", 1, 0.1909), ("cart", 7, 0.3042)]
    sink = captured(rows)

    hits = await vector_repo.search_similar(13, _FAKE_VEC, top_k=5, min_score=0.0)

    assert [h.source_id for h in hits] == [1, 7], "0.1909 这种低分也该返回——默认不过滤"
    assert sink["params"]["min_score"] == 0.0, "min_score 必须显式传进参数"


async def test_default_min_score_is_zero(captured):
    """不传 min_score 时默认 0.0：worker 侧将来若调这个函数，行为不会突变。"""
    sink = captured([("owned", 1, 0.19)])

    await vector_repo.search_similar(13, _FAKE_VEC)

    assert sink["params"]["min_score"] == 0.0


# ---------- 2. 回归：min_score 必须真的进了 SQL 参数（2026-10-17 的 P0） ----------

async def test_min_score_is_passed_as_bind_param(captured):
    """🔴 本文件最重要的一条。

    2026-10-17 实测踩到：SQL 写成 WHERE ... >= :min_score，函数签名加了
    min_score 并做了校验，但 `session.execute(_SEARCH_SQL, {...})` 的参数字典里
    **漏了这个键**。真机跑出来三个值全炸：

        min_score=0.0   -> StatementError: A value is required for bind
                           parameter 'min_score'
        min_score=0.4   -> 同上
        min_score=0.99  -> 同上

    校验、签名、docstring 全对，唯独「值没送进去」——这类 bug 单测最容易漏，
    所以这里直接断言参数字典里有这个键，且值是调用方传进来的原值。
    """
    sink = captured([("owned", 1, 0.75)])

    await vector_repo.search_similar(13, _FAKE_VEC, top_k=3, min_score=0.42)

    assert "min_score" in sink["params"], "参数字典漏了 min_score——SQL 会报 bind 错误"
    assert sink["params"]["min_score"] == 0.42, "必须是调用方传的值，不是硬编码"
    assert ":min_score" in sink["sql"], "SQL 里也得有占位符，否则阈值没生效"


async def test_sql_filters_by_min_score(captured):
    """锁住SQL 文本本身：阈值条件不能被后来人「优化」掉。"""
    sink = captured([])

    await vector_repo.search_similar(13, _FAKE_VEC, min_score=0.4)

    assert ":min_score" in sink["sql"]
    # user_id 必在 WHERE 里（铁律），别把范围条件改没了
    assert "user_id = :uid" in sink["sql"]


# ---------- 3. 越界拦截 ----------

@pytest.mark.parametrize("bad", [-0.1, 1.1, -1.0, 2.0])
async def test_min_score_out_of_range_rejected(captured, bad):
    """分数是 1 - 余弦距离，范围 [-1, 1]。手滑的值必须当场炸，不静默放行。"""
    captured([])

    with pytest.raises(ValueError, match="min_score"):
        await vector_repo.search_similar(13, _FAKE_VEC, min_score=bad)


async def test_top_k_zero_rejected(captured):
    """顺带锁住原有校验，别让改 min_score 时把它碰掉。"""
    captured([])

    with pytest.raises(ValueError, match="top_k"):
        await vector_repo.search_similar(13, _FAKE_VEC, top_k=0)


# ---------- 4. 行压成 ItemHit 的形态 ----------

async def test_hits_are_item_hit_dataclass(captured):
    """text() 没声明列名，只能按下标取。测 PG 返回的字符串 id 被转成 int。"""
    captured([("owned", "42", 0.63)])   # 模拟 PG 驱动把 int8 返成 str 的情况

    hits = await vector_repo.search_similar(13, _FAKE_VEC)

    assert len(hits) == 1
    assert hits[0].source_type == "owned"
    assert hits[0].source_id == 42 and isinstance(hits[0].source_id, int)
    assert hits[0].score == pytest.approx(0.63)
    assert isinstance(hits[0], vector_repo.ItemHit)


async def test_vector_is_literalised(captured):
    """查询向量要转成 pgvector 文本字面量 '[0.1,0.2,...]' 再 CAST。

    这是 10-15 实测踩过的坑：直接绑 Python list 会报类型错。
    """
    sink = captured([])

    await vector_repo.search_similar(13, _FAKE_VEC)

    vec_param = sink["params"]["vec"]
    assert isinstance(vec_param, str), "vec 必须是字符串，不是 list"
    assert vec_param.startswith("[") and vec_param.endswith("]")
    assert "CAST(:vec AS vector)" in sink["sql"]