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


def _key():
    """假 KeyRecord —— call_model 要的是这个类型不是 None（我第一版传了 None）。"""
    from app.services.api_key_service import KeyRecord
    return KeyRecord(key_id=1, provider="t", base_url="https://x.invalid/v1",
                     api_key="k", model_name="m")


class _FakeSession:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, *a, **k): return None


@pytest.fixture(autouse=True)
def no_paid_calls(monkeypatch):
    """🔴 **绝不能让测试真调博查 / 主模型**。

    compare_specs_service.fetch_specs 内部 = 每件 1 次博查（0.036 元），
    compare_service 那步 = 1 次主模型。3 件 = 0.108 元/次。
    跑 205 个测试时只要有一个没 mock，就是真花钱。

    这条 fixture 是**阶段 3 加的**——之前 compare 是占位实现，不花钱，
    所以没有 mock。现在接了真实现，必须挡住。
    """
    async def fake_fetch(items, user_id, session):
        return {n: {"name": n, "price": 100, "specs": {"品牌": "测试"}}
                for n in items}

    async def fake_call_model(key, messages, **kw):
        system = messages[0].get("content") or ""
        # 🔴 按 system prompt 分流：A4 对比 / A5 排序 / A5 搜词
        if "排序" in system:
            return (json.dumps({"items": [
                {"name": "索尼 WH-1000XM5", "reason": "他偏好续航"}]},
                ensure_ascii=False), "fake-model", [])
        return (json.dumps({
            "dimensions": [{"name": "重量", "values": {"a": "250g", "b": "61g"},
                            "winner": "b"}],
            "summary": "b 更轻"
        }, ensure_ascii=False), "fake-model", [])

    monkeypatch.setattr(a1.compare_specs_service, "fetch_specs", fake_fetch)
    monkeypatch.setattr(a1.model_call, "call_model", fake_call_model)


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
    requested = {}

    async def spy_fetch(items, user_id, session):
        requested["items"] = list(items)
        return {n: {"name": n, "price": 1, "specs": {}} for n in items}

    a1.compare_specs_service.fetch_specs = spy_fetch

    sink = a1.TextSink()
    call = _call(a1.COMPARE_TOOL_NAME, {
        "question": "哪个好",
        "items": ["商品甲", "商品乙", "商品丙", "商品丁"],
    })
    out = await a1.compare(_state([call]), sink, _key(), _FakeSession())

    # 🔴 断言要看**「取参时实际请求了哪几件」**，而不是「输出文本里出现哪个名字」。
    #    截断的意义就是省钱（少 1 次博查），所以关键证据是请求列表。
    #   （第一版断言写在输出文本上，mock 固定返回 a/b 所以测不出来，白跑一轮。）
    assert requested["items"] == ["商品甲", "商品乙", "商品丙"], (
        "取参只应请求 3 件，实际：" + str(requested["items"]))
    assert "商品丁" not in requested["items"]
    assert out["compare_rounds"] == 1


async def test_compare_rejects_fewer_than_two():
    """少于 2 件没法比 —— 要给模型明确指引，不是空结果。"""
    sink = a1.TextSink()
    call = _call(a1.COMPARE_TOOL_NAME, {"question": "q", "items": ["只有一个"]})
    out = await a1.compare(_state([call]), sink, _key(), _FakeSession())
    assert "至少需要 2 件" in out["messages"][-1]["content"]


# ---------- 3. question 为空要降级 ----------

async def test_compare_degrades_when_question_missing():
    """🔴 question 为空 → **降级**成按品类对比，不报错。

    「维度按用户问题定」是 A4 的核心，但模型漏填时
    退化到「按品类对比」远好过整个对比失败（三道保险的第三道）。
    """
    # 🔴 降级现在发生在**拼 prompt 时**（compare_service.build_messages），
    #    不是返回一段占位文本（那是阶段 2 的行为，阶段 3 换掉了）。
    #    所以要看**传给 call_model 的 messages 里有没有「按品类」那句**。
    seen = {}

    async def spy_call(key, messages, **kw):
        seen["messages"] = messages
        return (json.dumps({"dimensions": [], "summary": "s"}), "m", [])

    a1.model_call.call_model = spy_call

    sink = a1.TextSink()
    call = _call(a1.COMPARE_TOOL_NAME, {"items": ["索尼", "AirPods"]})
    await a1.compare(_state([call]), sink, _key(), _FakeSession())

    user_msg = seen["messages"][-1]["content"]
    assert "品类" in user_msg, "question 为空时应按品类通用维度对比：" + user_msg
    assert "真正关心的问题" not in user_msg, "不该出现「用户关注点」的措辞"


async def test_compare_emits_agent_events():
    """🔴 前端要显示「正在对比…」→ 必须发 start / end 两个事件。

    ⚠️ 必须都发：节点抛异常时 end 不会自动补（TextSink 里刻意不自动配对），
    只有 try/finally 保证。只有 start 的话前端会永远转圈。
    """
    sink = a1.TextSink()
    call = _call(a1.COMPARE_TOOL_NAME, {"question": "q", "items": ["a", "b"]})
    await a1.compare(_state([call]), sink, _key(), _FakeSession())
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

# ---------- 5. A5 recommend 节点（阶段 4） ----------

def test_route_dispatches_recommend():
    """🔴 route 必须认识第三个工具（加 recommend 时忘了改就会漏）。"""
    rec = _call(a1.RECOMMEND_TOOL_NAME, {"question": "推荐个耳机"})
    assert a1.route({"tool_calls": [rec]}) == "recommend"


def test_recommend_is_separate_counter():
    """🔴 锁「推荐有自己的次数上限」。

    推荐比检索贵得多（0.1-0.2 元 vs 0 元），不能共用检索的额度。
    """
    assert a1.MAX_RECOMMEND_ROUNDS == 1
    assert a1.MAX_RECOMMEND_ROUNDS != a1.MAX_SEARCH_ROUNDS


def test_recursion_limit_covers_three_tools():
    """🔴 三种工具的最坏路径。

    实测（2026-10-18 探针）：检索2 + 对比1 + 推荐1 = 9 次节点执行，
    **limit=9 撞，10 才通** —— END 那一跳也算一步。
    """
    steps = 2 * (a1.MAX_SEARCH_ROUNDS + a1.MAX_COMPARE_ROUNDS
                 + a1.MAX_RECOMMEND_ROUNDS) + 1
    assert steps == 9, "公式变了要同步更新这个断言"
    assert a1.RECURSION_LIMIT >= steps + 1, (
        "RECURSION_LIMIT=%d 连 END 那一步都不够（需要 %d）"
        % (a1.RECURSION_LIMIT, steps + 1))


@pytest.fixture(autouse=True)
def mock_recommend_deps(monkeypatch):
    """🔴 挡 recommend 节点用到的全部花钱依赖。"""
    async def fake_profile(user_id, session):
        return "用户偏好：长续航降噪"

    async def fake_searches(profile_text, question, key):
        return ["降噪耳机 长续航"]

    async def fake_candidates(searches):
        return ["索尼 WH-1000XM5"]

    async def fake_specs(items, user_id, session):
        return {n: {"name": n, "price": 2299, "specs": {"重量": "254g"}}
                for n in items}

    async def fake_rank(key, messages, **kw):
        return (json.dumps({"items": [
            {"name": "索尼 WH-1000XM5", "reason": "他偏好续航"}]},
            ensure_ascii=False), "m", [])

    monkeypatch.setattr(a1.profile_service, "load_profile_context", fake_profile)
    monkeypatch.setattr(a1.recommend_service, "build_searches", fake_searches)
    monkeypatch.setattr(a1.recommend_service, "search_candidates", fake_candidates)
    monkeypatch.setattr(a1.compare_specs_service, "fetch_specs", fake_specs)
    #🔴 **不要再 mock 一次 call_model**：上面 no_paid_calls 已经 mock 了它，
    #    两个 autouse fixture 里**后定义的那个会覆盖前面的**，
    #    于是这里返回的是 no_paid_calls 的「搜词 JSON」而不是排序结果，
    #    表现为「排序结果全被过滤」。
    #    正确做法：让 no_paid_calls 的 fake_call_model **认得出这是排序那一步**。
    #    （改 no_paid_calls 的 fake 比重叠定义可靠——一个桩，一处口径。）


async def test_recommend_node_emits_agent_events():
    """🔴 前端要显示「正在根据你的偏好推荐」→ start / end 必须成对。"""
    sink = a1.TextSink()
    call = _call(a1.RECOMMEND_TOOL_NAME, {"question": "推荐个耳机"})
    out = await a1.recommend(_state([call]), sink, _key(), _FakeSession())
    assert [ev["phase"] for ev in sink._agents] == ["start", "end"]
    assert out["recommend_rounds"] == 1
    assert sink._agents[0]["name"] == "A5"


async def test_recommend_node_returns_text_to_model():
    """recommend 节点必须返回一段给 decide 看的文本（含推荐理由）。"""
    sink = a1.TextSink()
    call = _call(a1.RECOMMEND_TOOL_NAME, {"question": "推荐个耳机"})
    out = await a1.recommend(_state([call]), sink, _key(), _FakeSession())
    text = out["messages"][-1]["content"]
    assert "索尼 WH-1000XM5" in text
    assert "偏好续航" in text
