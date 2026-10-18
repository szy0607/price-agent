"""卡片（show_item_card）节点测试（2026-10-18 阶段 5）。

锁四件事：
1. **卡片走独立通道** —— 不混进 text（正文）也不混进 agents（过程提示）
2. **0 次主模型** —— 卡片只要 web_search 的结果，这是它比 compare/recommend 轻的地方
3. **不落库** —— 草稿只在当前响应里，用户点确认才走 POST /cart/items
4. **失败不抛** —— 博查挂了要告诉模型「没搜到」，不是崩掉
"""

import json

import pytest

from app.agents import a1_graph as a1
from app.services.model_call import ToolCall
from app.core.errors import BizError, ErrorCode

pytestmark = pytest.mark.asyncio


def _call(args: dict) -> ToolCall:
    return ToolCall(id="c1", name=a1.CARD_TOOL_NAME,
                    arguments=json.dumps(args, ensure_ascii=False))


def _state(calls) -> dict:
    return {
        "messages": [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": c.id, "type": "function",
                             "function": {"name": c.name,
                                          "arguments": c.arguments}} for c in calls]},
        ],
        "user_id": 13,
        "tool_calls": calls,
    }


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, *a, **k): return None


def _search_result(n: int = 5) -> list[dict]:
    return [{"name": f"商品{i}", "url": f"http://x/{i}",
             "snippet": f"概要{i}", "datePublished": "", "summary": None}
            for i in range(n)]


@pytest.fixture(autouse=True)
def mock_search(monkeypatch):
    """🔴 挡住唯一的花钱调用（0.036 元/次）。"""
    calls = {"n": 0}

    async def fake_search(query, count=5):
        calls["n"] += 1
        return _search_result(count)

    monkeypatch.setattr(a1.web_search_service, "web_search", fake_search)
    return calls


# ---------- 1. 走独立通道 ----------

async def test_card_writes_to_card_channel_not_text(mock_search):
    """🔴 卡片必须走 card 通道，**不能进 text**。

    混进 text 的话，卡片 JSON 会出现在模型的回答正文里，
    用户看到的是「{"query":"..."}」这种裸JSON。
    """
    sink = a1.TextSink()
    out = await a1.card(_state([_call({"query": "索尼WH-1000XM5"})]),
                        sink, 13, _FakeSession())

    cards = await sink.flush_cards()
    assert len(cards) == 1, "应该写到 card 通道"
    assert cards[0]["query"] == "索尼WH-1000XM5"
    assert len(cards[0]["items"]) == a1.MAX_CARD_ITEMS

    # 🔴 关键：text 通道必须是空的
    assert await sink.flush() == [], "卡片混进了正文通道"
    assert out["card_rounds"] == 1


async def test_card_respects_max_items(mock_search):
    """web_search 返回 5 条，卡片只弹 MAX_CARD_ITEMS 张（对话里挤不下）。"""
    sink = a1.TextSink()
    await a1.card(_state([_call({"query": "耳机"})]), sink, 13, _FakeSession())
    cards = await sink.flush_cards()
    assert len(cards[0]["items"]) == a1.MAX_CARD_ITEMS == 3


async def test_card_does_not_clean_names(mock_search):
    """🔴 **大宋 23:47 拍板：不做名称清洗，原样返回**。

    理由是「用户可以在购物车修改」。所以网页标题里的
    「_参数_详细参数_太平洋产品报价」这类尾巴**不应该被处理**。
    这条锁的是「别偷偷加清洗逻辑」。
    """
    async def dirty_search(query, count=5):
        return [{"name": "索尼WH-1000XM5参数_详细参数_太平洋产品报价",
                 "url": "u", "snippet": "s", "datePublished": "",
                 "summary": None}]

    a1.web_search_service.web_search = dirty_search
    sink = a1.TextSink()
    await a1.card(_state([_call({"query": "索尼WH-1000XM5"})]), sink, 13, _FakeSession())
    cards = await sink.flush_cards()
    assert cards[0]["items"][0]["name"] == "索尼WH-1000XM5参数_详细参数_太平洋产品报价"


# ---------- 2. 成本 ----------

async def test_card_costs_zero_model_calls(mock_search, monkeypatch):
    """🔴 卡片**不调主模型** —— 这是它比 compare/recommend 轻的地方（0.036 元 + 0.5 秒）。"""
    boom = {"called": False}

    async def spy_call(key, messages, **kw):
        boom["called"] = True
        return ("{}", "m", [])

    monkeypatch.setattr(a1.model_call, "call_model", spy_call)
    sink = a1.TextSink()
    await a1.card(_state([_call({"query": "耳机"})]), sink, 13, _FakeSession())
    assert boom["called"] is False, "卡片不该调主模型"
    assert mock_search["n"] == 1, "只该调 1 次博查"


# ---------- 3. agent 事件成对 ----------

async def test_card_emits_agent_events(mock_search):
    """前端要显示「正在查商品…」→ start / end 必须成对。"""
    sink = a1.TextSink()
    await a1.card(_state([_call({"query": "耳机"})]), sink, 13, _FakeSession())
    assert [e["phase"] for e in sink._agents] == ["start", "end"]
    assert sink._agents[0]["name"] == "CARD"


# ---------- 4. 失败降级 ----------

async def test_card_tells_model_not_to_fabricate_on_empty(monkeypatch):
    """🔴 搜不到时必须明说「不要编造商品」。

    不说的话模型会自己编一个商品出来——不报错，但推荐是假的。
    """
    async def empty(query, count=5):
        return []

    monkeypatch.setattr(a1.web_search_service, "web_search", empty)
    sink = a1.TextSink()
    out = await a1.card(_state([_call({"query": "不存在的商品"})]),
                         sink, 13, _FakeSession())
    text = out["messages"][-1]["content"]
    assert "不要编造" in text
    assert await sink.flush_cards() == [], "没搜到就不该写卡片"


async def test_card_survives_bocha_error(monkeypatch):
    """博查报错 → 告诉模型「没搜到」，**不抛异常**。"""

    async def boom(query, count=5):
        raise BizError(ErrorCode.PARAM_INVALID, "BOCHA_API_KEY 未配置")

    monkeypatch.setattr(a1.web_search_service, "web_search", boom)
    sink = a1.TextSink()
    out = await a1.card(_state([_call({"query": "耳机"})]), sink, 13, _FakeSession())
    assert "没搜到" in out["messages"][-1]["content"]
    assert [e["phase"] for e in sink._agents] == ["start", "end"], "异常时end 也要发"


async def test_card_rejects_empty_query(mock_search):
    """没有 query → 明确告诉模型，不要去搜空串。"""
    sink = a1.TextSink()
    out = await a1.card(_state([_call({"query": "  "})]), sink, 13, _FakeSession())
    assert "没有提供商品名" in out["messages"][-1]["content"]
    assert mock_search["n"] == 0, "空 query 不该调博查（省钱）"


# ---------- 5. 图与计数 ----------

def test_route_dispatches_card():
    """🔴 route 必须认识第四个工具。"""
    assert a1.route({"tool_calls": [_call({"query": "x"})]}) == "card"


def test_recursion_limit_covers_four_tools():
    """🔴 四种工具的最坏路径：检索2+对比1+推荐1+卡片1 = 11 次节点执行 + END = 12。"""
    steps = 2 * (a1.MAX_SEARCH_ROUNDS + a1.MAX_COMPARE_ROUNDS
                 + a1.MAX_RECOMMEND_ROUNDS + a1.MAX_CARD_ROUNDS) + 1
    assert steps == 11
    assert a1.RECURSION_LIMIT >= steps + 1, (
        "RECURSION_LIMIT=%d 不够（需要 %d）" % (a1.RECURSION_LIMIT, steps + 1))