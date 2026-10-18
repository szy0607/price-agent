"""A1 图的 compare 节点（2026-10-18 阶段 2）。

锁四类「错了不报错」的行为：
1. **route 必须按工具名分派** —— 否则 compare 的 tool_call 会被扔进 search
2. **三件上限** —— 模型无视 maxItems 给 4 个时要截断（多 1 次博查 = 0.036 元）
3. **question 为空要降级** —— 不能让整个对比失败
4. **RECURSION_LIMIT 要够最坏路径** —— 撞了是抛异常、流断、用户看到「生成失败」
"""

import json

import pytest

from app.agents import a1_graph as a1
from app.services.model_call import ToolCall

pytestmark = pytest.mark.asyncio


def _call(name: str, args: dict) -> ToolCall:
    return ToolCall(id="c_" + name, name=name,
                    arguments=json.dumps(args, ensure_ascii=False))


def _state(tool_calls: list) -> dict:
    return {
        "messages": [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": c.id, "type": "function",
                             "function": {"name": c.name,
                                          "arguments": c.arguments}} for c in tool_calls]},
            *[{"role": "tool", "tool_call_id": c.id, "content": "占位"}
              for c in tool_calls],
        ],
        "user_id": 13,
        "tool_calls": tool_calls,
    }


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, *a, **k): return None


# ---------- 1. route 按工具名分派 ----------

def test_route_dispatches_by_tool_name():
    """🔴 **本文件最重要的一条**：route 必须看工具名。

    原来只有一种工具时写死 `return "search"`。加 compare 后如果不改，
    compare 的 tool_call 会被扔进 search 节点 —— 去检索
    「索尼WH-1000XM5」这个字符串，检索不到，模型拿到「没找到」就开始编答案。
    **不报错，只是答非所问。**
    """
    search_call = _call(a1.TOOL_NAME, {"query": "耳机"})
    compare_call = _call(a1.COMPARE_TOOL_NAME, {"question": "q", "items": ["a", "b"]})

    assert a1.route({"tool_calls": [search_call]}) == "search"
    assert a1.route({"tool_calls": [compare_call]}) == "compare"
    assert a1.route({"tool_calls": []}) == a1.END
    assert a1.route({}) == a1.END


def test_route_falls_back_to_search_for_unknown_tool():
    """模型幻觉出未知工具名时回落到 search，不抛异常。

    理由：让它走一次检索比中断整轮对话好。真要严格校验应该抛，
    但**没验证过所有厂商的模型都严格遵守 tools 定义**，先用宽松口径。
    """
    weird = _call("some_hallucinated_tool", {})
    assert a1.route({"tool_calls": [weird]}) == "search"


def test_route_must_return_end_constant_not_string():
    """🔴 route 要return `END` 常量，不是字符串 "END"。

    实测：返回字符串会抛 `KeyError: 'END'`（我写探针时踩过）。
    """
    assert a1.END == "__end__", "END 常量的值变了？条件边映射表会失效"
    assert a1.route({"tool_calls": []}) is a1.END


# ---------- 2. 三件上限 ----------

async def test_compare_truncates_over_three_items():
    """🔴 模型给 4 件时截断到 3 件（第 4 件要多花 0.036 元博查）。

    ⚠️ 断言不能写 `'d' not in text` —— 占位文案里有「设计」（design.md），
    字母 d 会出现。**必须用逗号分隔的商品名片段来判断**。
    （2026-10-18 第一版就是这么写错的，白跑一轮。）
    """
    sink = a1.TextSink()
    call = _call(a1.COMPARE_TOOL_NAME, {
        "question": "哪个好",
        "items": ["商品甲", "商品乙", "商品丙", "商品丁"],
    })
    out = await a1.compare(_state([call]), sink, _FakeSession())

    text = out["messages"][-1]["content"]
    assert "商品丁" not in text, "第 4 件应该被丢掉：" + text
    for kept in ("商品甲", "商品乙", "商品丙"):
        assert kept in text, kept + " 应该保留"
    assert out["compare_rounds"] == 1


async def test_compare_rejects_fewer_than_two():
    """少于 2 件没法比 —— 要给模型明确指引，不是空结果。"""
    sink = a1.TextSink()
    call = _call(a1.COMPARE_TOOL_NAME, {"question": "q", "items": ["只有一个"]})
    out = await a1.compare(_state([call]), sink, _FakeSession())
    assert "至少需要 2 件" in out["messages"][-1]["content"]


# ---------- 3. question 为空要降级 ----------

async def test_compare_degrades_when_question_missing():
    """🔴 question 为空 → **降级**成按品类对比，不报错。

    「维度按用户问题定」是 A4 的核心，但模型漏填时
    退化到「按品类对比」远好过整个对比失败（三道保险的第三道）。
    """
    sink = a1.TextSink()
    call = _call(a1.COMPARE_TOOL_NAME, {"items": ["索尼", "AirPods"]})
    out = await a1.compare(_state([call]), sink, _FakeSession())
    assert "品类" in out["messages"][-1]["content"]


async def test_compare_emits_agent_events():
    """🔴 前端要显示「正在对比…」→ 必须发 start / end 两个事件。

    ⚠️ 必须都发：节点抛异常时 end 不会自动补（TextSink 里刻意不自动配对），
    只有 try/finally 保证。只有 start 的话前端会永远转圈。
    """
    sink = a1.TextSink()
    call = _call(a1.COMPARE_TOOL_NAME, {"question": "q", "items": ["a", "b"]})
    await a1.compare(_state([call]), sink, _FakeSession())
    phases = [ev["phase"] for ev in sink._agents]
    assert phases == ["start", "end"], "应该成对，实际 " + str(phases)


# ---------- 4. RECURSION_LIMIT ----------

def test_recursion_limit_covers_worst_path():
    """🔴 锁「RECURSION_LIMIT 够最坏路径」。

    最坏路径 = 检索 2 次 + 对比 1 次：
        decide(1) → search(2) → decide(3) → search(4)
                 → decide(5) → compare(6) → decide(7)
    **实测最小可用值 = 7**（2026-10-18 探针跑出来的）。

    撞上限的后果是抛 GraphRecursionError → SSE 流断 → 用户看到「生成失败」。
    业务上靠各工具的次数上限提前收尾，让这个兜底永远撞不到。

    🔴 这个断言的价值是「改公式时会被抓到」——
       2026-10-17 我按轮数×2 算出 5（会撞），
       这次先按边数算出 8（可用但理由不对，START 其实不算 super-step）。
    """
    worst_path_steps = 2 * (a1.MAX_SEARCH_ROUNDS + a1.MAX_COMPARE_ROUNDS) + 1
    assert worst_path_steps == 7
    assert a1.RECURSION_LIMIT >= worst_path_steps, (
        "RECURSION_LIMIT=%d < 最坏路径需要 %d"
        % (a1.RECURSION_LIMIT, worst_path_steps))


def test_limits_are_separate_per_tool():
    """🔴 锁「检索与对比各自计数」。

    检索用用户自己的 embedding key（不花钱），对比要联网（约 0.108 元）。
    **一个数字管全部的话，对比会占检索的额度或反过来。**
    """
    assert a1.MAX_SEARCH_ROUNDS == 2
    assert a1.MAX_COMPARE_ROUNDS == 1
    assert a1.MAX_SEARCH_ROUNDS != a1.MAX_COMPARE_ROUNDS