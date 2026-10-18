"""chat_stream 接 LangGraph 编排后的行为测试（2026-10-18）。

编排从「直接调stream_model」改成「跑 a1_graph 的 decide 图」后，
本模块锁四类「漏了不报错」的行为：

1. **最后一个字不能丢**：图跑完那一刻 sink 里可能还有字没被 flush 走，
   while 循环外必须再取一次。漏了 → 「每次回答结尾被截断」，且不报错。
2. **用户点停止必须落库**：`_persist` 要在 CancelledError 分支里执行到。
   漏了 → 前端显示「已停止」，一刷新消息就没了。
3. **只有 ModelCallError 能触发 key 失效标记**：PG 挂了之类不能误标好 key。
4. **半截文本在任何结局下都要保住**（failed / interrupted 都要落）。

## 为什么用假 graph 而不是真图

真图要连 PG + 真调 embedding（花钱）。本模块锁的是**编排层的行为**，
所以只把「图往 sink 里写字」这一层换掉，节点逻辑由 a1_graph 自己的测试管。

🔴 **写这个文件时踩过一个坑**：第一版假 graph 没接 sink（`self.sink = None`），
图永远写不进东西，三个测试全红成 `status=failed`——**看起来像代码坏了，其实是探针错了**。
教训：打桩时凡是「需要拿到外部对象」的字段，都要确认真接上了。
"""

import json

import pytest
from fastapi import BackgroundTasks

from app.schemas.chat_sche import ChatSendInSchema
from app.services import chat_stream as cs
from app.services.api_key_service import KeyRecord
from app.services.chat_service import PreparedChat
from app.services.model_call import ModelCallError

pytestmark = pytest.mark.asyncio

_captured: dict = {}


class FakeSink:
    """替身：跟 a1_graph.TextSink 同接口，但不依赖真实模型。"""

    def __init__(self) -> None:
        self._pending: list[str] = []
        self._agents: list[dict] = []

    def write(self, chunk: str) -> None:
        if chunk:
            self._pending.append(chunk)

    def write_agent(self, name: str, phase: str, label: str = "") -> None:
        self._agents.append({"name": name, "phase": phase, "label": label})

    async def flush(self) -> list[str]:
        # 🔴 这里用 sleep(0) 而非真的等：探测「循环外补flush」有没有生效，
        #    真的等会把测试拖成 10 秒级。
        out, self._pending = self._pending, []
        return out

    async def flush_agents(self) -> list[dict]:
        out, self._agents = self._agents, []
        return out


def _make_build(script, boom=None, extra_messages=None, agents=None):
    """造 build_graph 的替身：接sink、按时序写文本、可选抛异常、可选返回新增消息。

    🔴 `sink` 必须从 build_graph 的入参拿——真实 a1_graph 里
       sink 是闭包捕获的（见 build_graph 里的 node_decide）。
       第一版探针写成 `self.sink = None` 就因为漏了这步全红。

    `extra_messages` 模拟图跑完后 final_state["messages"] 的完整内容
    （= 初始 messages + 新增）。为 None 时表示**没有新增**。

    `agents` 模拟节点调用 `sink.write_agent(...)`——格式 [(name, phase, label), ...]，
    在文本之前发出（对应真实场景：节点开始跑 -> 出文本 -> 节点结束）。
    """
    def _build(key, sink):
        class _FakeGraph:
            async def ainvoke(self, state, config=None):
                for name, phase, label in (agents or []):
                    sink.write_agent(name, phase, label)
                    await _sleep(0)
                for chunk, delay in script:
                    sink.write(chunk)
                    if delay:
                        await _sleep(delay)
                if boom is not None:
                    raise boom
                messages = extra_messages if extra_messages is not None \
                    else state.get("messages", [])
                return {
                    "answer": "".join(c for c, _ in script),
                    "round_no": 2,
                    "messages": messages,
                }
        return _FakeGraph()
    return _build


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


async def _fake_persist(user_id, prepared, reply, status, failure,
new_messages=None) -> list[int]:
    _captured.clear()
    _captured.update(reply=reply, status=status, failure=failure,
                     new_messages=new_messages)
    # 🔴 2026-10-18：_persist 返回类型从 int|None 变成 list[int]
    #    （工具化后一轮落多条）。返回列表，调用方取 [-1] 当 message_id。
    return [1234]


async def _fake_prepare(user_id, payload, session) -> PreparedChat:
    return PreparedChat(
        conversation_id=999,
        messages=[
            {"role": "system", "content": "你是导购"},
            {"role": "user", "content": "送人送什么好"},
        ],
        key=KeyRecord(key_id=1, provider="t", base_url="https://x.invalid/v1",
                      api_key="k", model_name="m"),
        model_name="m",
    )


@pytest.fixture(autouse=True)
def stub_all(monkeypatch):
    """把三个外部依赖全打桩：prepare_chat / _persist / build_graph+TextSink。"""
    monkeypatch.setattr(cs, "_persist", _fake_persist)
    monkeypatch.setattr(cs.chat_service, "prepare_chat", _fake_prepare)
    monkeypatch.setattr(cs, "_schedule_profile", lambda *a, **k: None)
    monkeypatch.setattr(cs.a1_graph, "TextSink", FakeSink)
    _captured.clear()


def _deltas(frames: list[str]) -> list[str]:
    """从 SSE 帧里抽出所有 delta 文本。"""
    out = []
    for frame in frames:
        for line in frame.split("\n"):
            if line.startswith("data: ") and '"text"' in line:
                out.append(json.loads(line[6:])["text"])
    return out


async def _run(script, boom=None) -> list[str]:
    """跑一遍chat_stream，收集所有 SSE 帧。"""
    cs.a1_graph.build_graph = _make_build(script, boom)
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())
    return [frame async for frame in gen]


# ---------- 1. 正常收完 ----------

async def test_normal_completes_with_full_text(monkeypatch):
    """🔴 锁「循环外补 flush」：最后一个字不能丢。

    图在while 条件为 False 的那一刻才刚写完最后一块，循环内那次 flush
    拿不到它。漏掉循环外的补flush → 回答结尾被截断，**且不报错**。
    """
    frames = await _run([("你", 0.02), ("好", 0.02), ("世界", 0)])

    assert "".join(_deltas(frames)) == "你好世界"
    assert _captured["reply"] == "你好世界"
    assert _captured["status"] == "completed"
    assert any("event: meta" in f for f in frames)
    assert any("event: done" in f for f in frames)


# ---------- 2. 用户点停止 ----------

async def test_cancel_persists_partial():
    """🔴 锁「取消后必须落库」。

    取消态下 `await` 被 cancel 的 task 会立刻抛 CancelledError，
    不包 try 的话异常冒出去 → `_persist` 永远执行不到 →
    用户看到「已停止」，一刷新消息就没了。
    """
    import asyncio

    cs.a1_graph.build_graph = _make_build([("慢", 0.05)] * 60)
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())

    frames = []
    with pytest.raises((asyncio.CancelledError, GeneratorExit)):
        async for frame in gen:
            frames.append(frame)
            if len(frames) >= 3:
                await gen.aclose()# 模拟用户 abort
                raise asyncio.CancelledError()

    assert _captured["status"] == "interrupted", "取消后没落库"
    assert _captured["reply"], "半截文本应该被保存"


# ---------- 3. 异常分流 ----------

async def test_model_error_marks_key():
    """ModelCallError → failed + 把 failure 传下去（key失效标记靠这个）。

    少传failure → 用户 key 其实已死却还在被反复使用（chat_service.mark_key_invalid_if_needed
    靠文案匹配，没有 failure 就不会标）。
    """
    frames = await _run(
        [("部分", 0)],
        boom=ModelCallError("key 已被厂商拒绝，已标记为失效，请重新配置"),
    )

    assert _captured["status"] == "failed"
    assert _captured["failure"], "ModelCallError 必须传 failure，否则 key 不会被标失效"
    assert "部分" in _captured["reply"], "半截文本要保住"
    assert any("event: error" in f for f in frames)
    assert any("event: done" in f for f in frames)


async def test_non_model_error_does_not_mark_key():
    """🔴 锁「不误标好 key」。

    PG 挂了、SQL 写错、bizError……这些跟厂商 key 无关。
    如果把它们也当 failure 传下去 → 一个好好的 key 被标成失效，
    用户下次再也用不了。
    """
    frames = await _run([("x", 0)], boom=RuntimeError("PG 挂了"))

    assert _captured["status"] == "failed"
    assert _captured["failure"] is None, "非 ModelCallError 不能传 failure"
    assert any("PG 挂了" in f for f in frames), "error 文案要能让人看懂"


# ---------- 4. 边界 ----------

async def test_empty_answer_still_sends_done():
    """模型什么都没说（空回答）→ 仍要发 done，否则前端永远转圈。

    `persist_reply` 内部对空文本返回 None 不落库（设计文档 §1.3），
    所以这里断言的是「前端能正常结束」。
    """
    frames = await _run([])

    assert _deltas(frames) == []
    assert any("event: done" in f for f in frames)


async def test_recursion_limit_passed_to_graph():
    """🔴 锁「recursion_limit 必须显式传」。

    LangGraph 1.2.4 默认 10007（不是 0.x 的 25）→ 不传 = 死循环 ≈ 4 小时 +烧钱。
    """
    seen = {}

    def _build(key, sink):
        class _G:
            async def ainvoke(self, state, config=None):
                seen.update(config or {})
                return {"answer": "", "round_no": 2, "messages": state.get("messages", [])}
        return _G()

    cs.a1_graph.build_graph = _build
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())
    _ = [f async for f in gen]

    assert "recursion_limit" in seen, "没传 recursion_limit —— 默认 10007 会死循环"
    assert seen["recursion_limit"] == cs.a1_graph.RECURSION_LIMIT


# ---------- 5. 9g：按 messages 逐条落库 ----------

async def test_new_messages_sliced_not_whole_history():
    """🔴 锁「只落图新增的那几条」。

    `final_state["messages"]` 开头是 prepare_chat 已经落过的
    system / user / 历史。**全量落会把整个历史重复插一遍**，
    会话里凭空多出几十条重复消息 —— 而且不报错。
    """
    initial = [{"role": "system", "content": "你是导购"},
               {"role": "user", "content": "送人送什么好"}]
    added = [
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "search_my_items",
                                      "arguments": '{"query":"耳机"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "检索到 1 件"},
    ]

    cs.a1_graph.build_graph = _make_build([("推荐索尼耳机。", 0)],
                                          extra_messages=initial + added)
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())
    _ = [f async for f in gen]

    passed = _captured["new_messages"]
    assert passed == added, f"落库的应是图新增部分，实际 {passed}"
    assert len(passed) == 2
    assert all(m.get("role") != "system" for m in passed), "system 不能重复落"
    assert all(m.get("role") != "user" for m in passed), "user 不能重复落"


async def test_persist_routes_to_graph_messages_when_present():
    """有 new_messages 时走 persist_graph_messages（逐条 + 补占位）。

    🔴 `extra_messages` 必须包含**初始 messages** —— 因为 chat_stream 是按
    「初始长度」切片取新增的（final_state["messages"][len(prepared.messages):]）。
    只给新增部分的话切片结果是空。
    """
    initial = [{"role": "system", "content": "你是导购"},
               {"role": "user", "content": "送人送什么好"}]
    cs.a1_graph.build_graph = _make_build([("答", 0)], extra_messages=initial + [
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "结果"},
    ])
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())
    _ = [f async for f in gen]
    assert _captured["new_messages"], "有新增消息时应传给 _persist"


async def test_no_new_messages_falls_back_to_single_persist():
    """没有新增消息（模型直接回答）时 new_messages 为空列表 → 走单条路径。

    不是 None 也不是有值 —— 是**空列表**。
    """
    cs.a1_graph.build_graph = _make_build([("直接回答", 0)], extra_messages=None)
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())
    _ = [f async for f in gen]
    assert _captured["new_messages"] in (None, [])

# ---------- 7. agent 事件（阶段 1：管道已铺好，节点还没用） ----------

async def test_agent_events_are_sent_as_sse():
    """🔴 节点调 `write_agent` 时，SSE 要发出 `agent` 事件。

    协议位见 docs/流式输出-设计.md §5.4——2026-10-18 之前只在前端留了
    「先按协议留着」的注释，后端从不发。这一项锁住管道是通的。
    """
    cs.a1_graph.build_graph = _make_build(
        [("推荐索尼。", 0.01)],
        agents=[("A4", "start", "正在对比索尼和 AirPods"),
                ("A4", "end", "")],
    )
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())
    frames = [f async for f in gen]

    agent_frames = [f for f in frames if "event: agent" in f]
    assert len(agent_frames) == 2, f"应该有 start + end 两帧，实际 {len(agent_frames)}"

    payload = json.loads(agent_frames[0].split("data: ", 1)[1])
    assert payload["name"] == "A4"
    assert payload["phase"] == "start"
    assert payload["label"] == "正在对比索尼和 AirPods"


async def test_agent_events_not_polluted_into_saved_text():
    """🔴 锁「agent 事件不进落库文本」。

    agent 是过程提示（「正在对比…」），不是正文。混进 `collected` 会让
    落库的文本里出现噪声，用户刷新后看到「正在对比…推荐索尼。」这种内容。

    🔴 **这条必须在「中断路径」上测**（2026-10-18 写测试时踩到）：
       正常收完时落库用的是 `final_state["answer"]`，**根本不经过 collected**，
       所以在正常路径上污染测不出来。只有**中断 / 失败**那条走
       `_persist(reply="".join(collected))` 才会暴露。
       第一版测试写的是正常路径，回退-验证也是绿的 —— 白写了。
    """
    import asyncio

    # 中断：先发一个 agent 事件，然后慢文本，第 3 帧就停止
    cs.a1_graph.build_graph = _make_build(
        [("推荐索尼。", 0.05)] * 60,
        agents=[("A4", "start", "正在对比索尼和 AirPods")],
    )
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())
    frames = []
    with pytest.raises((asyncio.CancelledError, GeneratorExit)):
        async for frame in gen:
            frames.append(frame)
            if len(frames) >= 3:
                await gen.aclose()
                raise asyncio.CancelledError()

    assert _captured["status"] == "interrupted"
    # 🔴 核心断言：中断落库走的是 collected，所以只有这里会看到污染
    assert "正在对比" not in _captured["reply"], (
        f"agent 提示污染了中断落库的文本：{_captured['reply']!r}")
    assert _captured["reply"] == "推荐索尼。"


async def test_no_agent_events_when_nodes_dont_call_it():
    """现阶段还没有节点调 write_agent → **不能凭空造出 agent 事件**。

    这条是回归保护：万一 flush_agents 写错了（比如返回 list 而不是空 list），
    前端会收到空事件。
    """
    cs.a1_graph.build_graph = _make_build([("普通回答", 0.01)])
    gen = cs.chat_stream(1, ChatSendInSchema(text="hi"), BackgroundTasks())
    frames = [f async for f in gen]
    assert not [f for f in frames if "event: agent" in f]
