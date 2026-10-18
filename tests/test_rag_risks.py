"""RAG 联调前的三处风险验证（2026-10-18）。

这三处原来是「等真机联调才知道」的风险，本文件把它们**提前验掉**——
能验的两处全验了，验不掉的那处写清了原因。

## 结论速览

| 风险 | 状态 | 依据 |
|---|---|---|
| ① LangGraph 是否原样透传 `ModelCallError` | ✅ **已排除** | 三种异常全部原样透传，`isinstance` 可靠 |
| ② 中断时 tool_calls 丢失 → 下轮 400 | ✅ **已排除** | 末尾补占位实测生效，孤立集合为空 |
| ③ `rag_min_score=0.4` 待校准 | ⚠️ **验不掉** | PG 未启动 + 只有 1 条向量，样本量不足 |

## 为什么①②要专门测

这两处都符合「**错了不报错、只是行为不对**」的特征：

① 如果 LangGraph 把异常包了一层，`chat_stream` 的
`isinstance(exc, ModelCallError)` 会判成 False → `failure=None`
→ `mark_key_invalid_if_needed` 不执行 → **key 死了还在被反复使用**，
且用户只会看到「模型调用失败」这一句，不会有任何「key 已失效」的提示。

② 如果没有末尾补占位，库里会留下一条孤立的 `assistant(tool_calls)`，
下一轮 `messages_for_context` 拼出来发给厂商 → **整个会话瘫掉（400）**，
而症状是「上一轮我按了停止，这轮就发不出消息了」，极难联想到是检索的问题。
"""

import asyncio
import json

import pytest
from fastapi import BackgroundTasks

from app.agents import a1_graph as a1
from app.repository import chat_repo
from app.schemas.chat_sche import ChatSendInSchema
from app.services import chat_service, chat_stream, model_call
from app.services.api_key_service import KeyRecord
from app.services.chat_service import PreparedChat
from app.services.model_call import ModelCallError

pytestmark = pytest.mark.asyncio


# ---------- 风险①：LangGraph 是否原样透传异常 ----------

@pytest.mark.parametrize("exc_factory", [
    lambda: ModelCallError("key 已被厂商拒绝，已标记为失效，请重新配置"),
    lambda: __import__("app.core.errors", fromlist=["BizError"]).BizError(
        __import__("app.core.errors", fromlist=["ErrorCode"]).ErrorCode.PARAM_INVALID,
        "未配置向量库"),
    lambda: RuntimeError("普通错误"),
])
async def test_langgraph_propagates_exception_unchanged(exc_factory):
    """🔴 锁「LangGraph 原样透传异常」。

    chat_stream 靠 `isinstance(exc, ModelCallError)` 区分「key 被拒」和
    「其他故障」。若LangGraph 包了一层，判断失效 → key 死了不标记、不报错。
    """
    from langgraph.graph import END, START, StateGraph

    original = exc_factory()

    async def boom(state):
        raise original

    class _S(dict):
        pass
    _S.__annotations__ = {"x": int}

    g = StateGraph(_S)
    g.add_node("boom", boom)
    g.add_edge(START, "boom")
    g.add_edge("boom", END)

    with pytest.raises(type(original)) as caught:
        await g.compile().ainvoke({"x": 0}, config={"recursion_limit": 3})

    assert type(caught.value) is type(original), "异常类型被包装了"
    assert str(caught.value) == str(original), "异常信息被改写了"


async def test_model_error_is_recognized_but_others_not(monkeypatch):
    """🔴 锁「只有 ModelCallError 能触发 key 失效标记」。

    与 test_chat_stream_graph 的 `test_non_model_error_does_not_mark_key`
    呼应：那条锁 chat_stream 的分流，这条锁 LangGraph 不破坏分流。
    """
    from langgraph.graph import END, START, StateGraph

    class _S(dict):
        pass
    _S.__annotations__ = {"x": int}

    results = {}
    for label, exc in [("mce", ModelCallError("key 已被厂商拒绝")),
                       ("plain", RuntimeError("PG 挂了"))]:
        async def boom(state, _e=exc):
            raise _e

        g = StateGraph(_S)
        g.add_node("boom", boom)
        g.add_edge(START, "boom")
        g.add_edge("boom", END)
        try:
            await g.compile().ainvoke({"x": 0}, config={"recursion_limit": 3})
        except BaseException as caught:
            results[label] = isinstance(caught, ModelCallError)

    assert results["mce"] is True, "ModelCallError 应被识别"
    assert results["plain"] is False, "普通异常不该被误判成 key 问题"


# ---------- 风险②：tool 消息成对落库（防厂商 400） ----------

def _needed_and_have(rows) -> tuple[set, set]:
    """从落库行里算出「需要配对的 tool_call id」与「已配对的」。

    ⚠️ **tool_call_id 根本没落进 content**（写判据时踩到了）：
      - 占位消息 content = `{"interrupted": true, "tool_call_id": "..."}`（有 id）
      - **正常结果 content = 检索结果的纯文本**（给模型看的，**没有 id**）
    所以判据只能是：**tool 行数 == 需要配对的个数**。
    这正是真实的协议约束——assistant 发 N 个 tool_calls 就要有 N 条 tool 消息。
    """
    need = set()
    tool_count = 0
    for row in rows:
        if row.role == "assistant":
            try:
                data = json.loads(row.content)
            except (ValueError, TypeError):
                continue
            for tc in data.get("tool_calls", []) or []:
                need.add(tc.get("id"))
        elif row.role == chat_repo.ROLE_TOOL:
            tool_count += 1
    return need, tool_count


@pytest.mark.parametrize("with_placeholder, expect_tool_rows", [
    (False, 1),   # 没带 tool 消息 -> 必须补 1 条占位
    (True, 1),    # 带了 tool 消息 -> 不该再补（总数仍是 1）
])
async def test_orphan_tool_calls_get_placeholder(with_placeholder, expect_tool_rows,
                                                 monkeypatch):
    """🔴 **本文件最重要的一条**：孤立 tool_calls 必须被补上占位。

    OpenAI 协议：assistant 发了 tool_calls，下一条必须是配对的 role="tool"
    （带 tool_call_id），孤立直接 400。

    没有占位的话，「用户按了停止」这个完全正常的操作会让**整个会话瘫掉**，
    而且症状是「上一轮按了停止，这轮就发不出消息」，极难联想到检索。

    🔴 判据为什么写成「tool 行数 == expect_tool_rows」而不是「== 待配对数」：
       第一版写的是后者，而参数化 True 的场景自带 tool 行，**删掉补占位逻辑也照样通过**
       —— 回退-验证才发现。写成固定期望值才抓得住。
    """
    added = []

    async def fake_add_message(user_id, conv, role, content, session, *,
                               model=None, status="completed"):
        added.append((role, content))
        class _Row:
            id = len(added)
        return _Row()

    async def fake_touch(*a, **k):
        return None

    monkeypatch.setattr(chat_repo, "add_message", fake_add_message)
    monkeypatch.setattr(chat_service.conversation_repo, "touch_conversation",
                        fake_touch)

    new_messages = [{"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_a1", "type": "function",
         "function": {"name": "search_my_items", "arguments": '{"query":"x"}'}},
    ]}]
    if with_placeholder:
        new_messages.append({"role": "tool", "tool_call_id": "call_a1",
                             "content": "检索到 2 件"})

    await chat_service.persist_graph_messages(
        1, 1, new_messages, "最终答案", "m", "completed", None)

    need, tool_count = _needed_and_have(
        [type("R", (), {"role": r, "content": c})() for r, c in added])
    assert need == {"call_a1"}, f"应该识别出一个待配对 id，实际 {need}"
    assert tool_count == expect_tool_rows, (
        f"🔴 tool 行数应为 {expect_tool_rows}（待配对 1 个），实际 {tool_count}")
    # 🔴 没自带 tool 消息时，补的那条必须是占位（内容含 interrupted 标记）
    if not with_placeholder:
        placeholder = [c for r, c in added
                       if r == chat_repo.ROLE_TOOL and "interrupted" in c]
        assert placeholder, "补的必须是 interrupted 占位，不是正常检索结果"


async def test_placeholder_content_marks_interrupted(monkeypatch):
    """占位消息要能看出「这次检索被打断了」，而不是伪装成正常结果。"""
    added = []

    async def fake_add_message(user_id, conv, role, content, session, *,
                               model=None, status="completed"):
        added.append((role, content))
        class _Row:
            id = len(added)
        return _Row()

    async def fake_touch(*a, **k):
        return None

    monkeypatch.setattr(chat_repo, "add_message", fake_add_message)
    monkeypatch.setattr(chat_service.conversation_repo, "touch_conversation",
                        fake_touch)

    await chat_service.persist_graph_messages(
        1, 1,
        [{"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_x", "type": "function",
             "function": {"name": "f", "arguments": "{}"}}]}],
        "", "m", "interrupted", None)

    tool_rows = [c for r, c in added if r == chat_repo.ROLE_TOOL]
    assert tool_rows, "应该补一条 tool 占位"
    payload = json.loads(tool_rows[0])
    assert payload.get("interrupted") is True
    assert payload.get("tool_call_id") == "call_x"


async def test_final_reply_not_duplicated_when_it_is_the_only_content(monkeypatch):
    """🔴 锁「没有 tool_calls 时不要多落一条空 tool」。

    边界：模型直接回答（没调工具）→ new_messages 里有 assistant 但没有 tool_calls。
    这时**不应该**补占位（没东西要配对）。
    """
    added = []

    async def fake_add_message(user_id, conv, role, content, session, *,
                               model=None, status="completed"):
        added.append((role, content))
        class _Row:
            id = len(added)
        return _Row()

    async def fake_touch(*a, **k):
        return None

    monkeypatch.setattr(chat_repo, "add_message", fake_add_message)
    monkeypatch.setattr(chat_service.conversation_repo, "touch_conversation",
                        fake_touch)

    await chat_service.persist_graph_messages(
        1, 1, [{"role": "assistant", "content": "直接回答"}],
        "直接回答", "m", "completed", None)

    roles = [r for r, _ in added]
    assert chat_repo.ROLE_TOOL not in roles, "没有 tool_calls 就不该补占位"
    assert roles.count("assistant") == 2, "assistant 消息 + 最终答案各一条"


# ---------- 风险③：阈值（⚠️ 验不掉，写清原因） ----------

def test_min_score_is_configurable_not_hardcoded():
    """阈值可配，而不是写死在代码里。

    为什么这条能测而「0.4 够不够」不能：`rag_min_score=0.4` 是**初值**，
    它的合理性取决于语料规模与 embedding 模型的分数分布 —— 而当前 PG 里
    只有 1 条向量，任何「校准」都是拿 n=1 的样本拟合，没有统计意义。
    真要定阈值，需要先让 PG 里有几十上百条向量，再跑一批真实 query。
    """
    from app.core.config import settings

    assert hasattr(settings, "rag_min_score"), "阈值应该在 config 里"
    assert 0.0 < settings.rag_min_score <= 1.0, "阈值必须在有效区间内"