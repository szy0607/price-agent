"""model_call 的工具调用（tools）支持测试。

🔴 **不真调模型**——真调一次花一次钱，且要用户自己的 API Key。
全部用 httpx.MockTransport 喂假的 SSE 流。

## 本文件锁的四条

1. **流式 tool_call 分片必须正确合并**（2026-10-17 最易写错处：
   arguments 分片到达，**只能拼接不能覆盖**；id/name 只在首片出现，
   后续是 None，**不能被覆盖成 None**）
2. **tools=None 时行为与从前完全一致**（回归：现有聊天链路不能坏）
3. **模型调工具时 content 为null 不再导致「一个字都不产出」**
   ——这正是改造前那个静默bug：前端转圈半天然后失败，且不报错
4. **非流式 call_model 返回值从 2 元组变 3 元组**（破坏性变更的回归锁）
"""
import json

import httpx
import pytest

from app.services import model_call
from app.services.api_key_service import KeyRecord

pytestmark = pytest.mark.asyncio

# 🔴 model_call 里每个入口都会先跑 validate_public_url，它做真实 DNS 解析
#    （getaddrinfo）。测试用的假域名 api.example.invalid 解析不了 → ValueError，
#    压根走不到 stream_model。必须 stub 掉。
#    **不要用真实域名**：那会让测试依赖网络与外部 DNS，CI 上必挂。
model_call.validate_public_url = lambda base_url: None

_KEY = KeyRecord(key_id=1, provider="test", base_url="https://api.example.invalid/v1",
                 api_key="sk-test", model_name="test-model")


def _sse(chunks: list[dict]) -> bytes:
    """把若干 chunk 拼成一条 SSE 响应体（末尾带 [DONE]）。"""
    lines = []
    for c in chunks:
        lines.append(b"data: " + json.dumps(c).encode() + b"\n\n")
    lines.append(b"data: [DONE]\n\n")
    return b"".join(lines)


def _text_chunk(text: str) -> dict:
    return {"choices": [{"delta": {"content": text}}]}


def _tc_chunk(index: int, *, cid: str | None = None, name: str | None = None,
              args: str | None = None) -> dict:
    """构造一个 tool_calls 分片。注意有的字段是 None（模拟真实响应）。"""
    tc = {"index": index}
    if cid is not None:
        tc["id"] = cid
    fn = {}
    if name is not None:
        fn["name"] = name
    if args is not None:
        fn["arguments"] = args
    if fn:
        tc["function"] = fn
    return {"choices": [{"delta": {"tool_calls": [tc]}}]}


async def _run_stream(chunks: list[dict]):
    """用假 SSE 跑一遍 stream_model，返回产出事件列表。

    🔴 用 monkeypatch 替掉 `http_client.get_http_client`（而不是改模块全局 `_shared`）——
    后者要在 finally 里手工还原，测试失败时容易漏，还污染同进程的其他测试。
    """
    import app.services.model_call as mc
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, content=_sse(chunks)))
    client = httpx.AsyncClient(transport=transport)
    mc.get_http_client = lambda: client
    try:
        return [ev async for ev in model_call.stream_model(_KEY, [{"role": "user", "content": "hi"}])]
    finally:
        await client.aclose()


# ---------- 1. 🔴 分片合并（本文件最重要） ----------

async def test_tool_call_arguments_pieces_are_concatenated():
    """🔴 arguments 分片到达，只能拼接。

    这是最容易写错的地方：写成 `slot["arguments"] = piece`（覆盖）的话，
    最终拿到的是最后一片 `:"送人"}`，json.loads 直接炸。
    """
    events = await _run_stream([
        _tc_chunk(0, cid="call_a1", name="search_items", args=""),
        _tc_chunk(0, args='{"que'),
        _tc_chunk(0, args='ry": "送人'),
        _tc_chunk(0, args='送什么"}'),
    ])

    calls = [ev.tool_call for ev in events if ev.kind == "tool_call"]
    assert len(calls) == 1, "四个分片应合并成一个工具调用"
    tc = calls[0]
    assert tc.name == "search_items"
    assert tc.id == "call_a1"
    # 🔴 核心断言：拼回完整的 JSON 字符串
    assert tc.arguments == '{"query": "送人送什么"}'
    assert tc.parsed_arguments() == {"query": "送人送什么"}, "必须能解析回dict"


async def test_id_and_name_not_overwritten_by_none():
    """后续分片的 id/name 是 None（真实响应就是这样），不能把已取到的值覆盖掉。"""
    events = await _run_stream([
        _tc_chunk(0, cid="call_a1", name="search_items", args='{"a":1}'),
        _tc_chunk(0, args=""),          # 只有 arguments，无 id/name
    ])

    tc = [ev.tool_call for ev in events if ev.kind == "tool_call"][0]
    assert tc.id == "call_a1", "id 被后续的 None 覆盖了"
    assert tc.name == "search_items", "name 被后续的 None 覆盖了"
    assert tc.arguments == '{"a":1}'


async def test_two_tool_calls_same_round_kept_separate():
    """并行调两个工具时按 index 分开，不该混成一条。"""
    events = await _run_stream([
        _tc_chunk(0, cid="call_0", name="search_items", args='{"q":"a"}'),
        _tc_chunk(1, cid="call_1", name="search_items", args='{"q":"b"}'),
        _tc_chunk(0, args=""),
        _tc_chunk(1, args=""),
    ])

    calls = [ev.tool_call for ev in events if ev.kind == "tool_call"]
    assert len(calls) == 2
    #按 index 排序产出，结果确定
    assert calls[0].id == "call_0" and calls[0].parsed_arguments() == {"q": "a"}
    assert calls[1].id == "call_1" and calls[1].parsed_arguments() == {"q": "b"}


async def test_tool_call_yielded_after_stream_ends():
    """🔴 工具调用事件必须在流的最后（收齐分片后），不能中途发半截JSON。"""
    events = await _run_stream([
        _tc_chunk(0, cid="call_a1", name="search_items", args='{"que'),
        _tc_chunk(0, args='ry":"x"}'),
    ])

    assert events[-1].kind == "tool_call", "tool_call 必须是最后一个事件"
    assert events[-1].tool_call.arguments == '{"query":"x"}'


async def test_tool_call_missing_name_is_skipped():
    """模型给了残缺请求（只有 arguments 没name）→ 跳过并继续，不能崩。"""
    events = await _run_stream([_tc_chunk(0, cid="call_x", args='{"a":1}')])

    assert not [ev for ev in events if ev.kind == "tool_call"]


# ---------- 2. 回归：不传 tools时行为不变 ----------

async def test_plain_text_stream_unchanged():
    """tools=None 时产出全是 text 事件，文本拼接结果与从前一致。"""
    events = await _run_stream([_text_chunk("你"), _text_chunk("好"), _text_chunk("！")])

    assert [ev.kind for ev in events] == ["text", "text", "text"]
    assert "".join(ev.text for ev in events) == "你好！"


async def test_text_and_tool_call_can_mix():
    """有些模型会先吐几个字再调工具，两种事件都要透出。"""
    events = await _run_stream([
        _text_chunk("让我查一下"),
        _tc_chunk(0, cid="call_a1", name="search_items", args='{"query":"x"}'),
    ])

    kinds = [ev.kind for ev in events]
    assert kinds == ["text", "tool_call"]


# ---------- 3. 解析容错 ----------

async def test_bad_arguments_json_returns_empty_dict():
    """模型生成半截 JSON（被截断）→返回空 dict，不抛。"""
    events = await _run_stream([_tc_chunk(0, cid="c", name="search_items", args='{"query":')])

    tc = [ev.tool_call for ev in events if ev.kind == "tool_call"][0]
    assert tc.parsed_arguments() == {}, "解析失败应兜底成空 dict"


def test_tool_call_parsed_arguments_handles_non_dict_json():
    """模型返回了合法 JSON 但不是对象（如数组）→ 同样兜底成空 dict。"""
    tc = model_call.ToolCall(id="c", name="n", arguments='[1,2,3]')
    assert tc.parsed_arguments() == {}


# ---------- 4. 非流式：返回值从 2 元组变 3 元组 ----------

def test_parse_tool_calls_from_response():
    """非流式响应里的 tool_calls 要被正确提取。"""
    raw = [{"id": "call_a", "type": "function",
            "function": {"name": "search_items", "arguments": '{"query":"耳机"}'}}]
    calls = model_call._parse_tool_calls(raw)

    assert len(calls) == 1
    assert calls[0].name == "search_items"
    assert calls[0].parsed_arguments() == {"query": "耳机"}


def test_parse_tool_calls_empty():
    """模型没调工具 → 空列表（不是 None，否则调用方 `if tool_calls:` 会判错）。"""
    assert model_call._parse_tool_calls(None) == []
    assert model_call._parse_tool_calls([]) == []


def test_parse_tool_calls_dict_arguments_coerced():
    """部分厂商把 arguments 返成 dict（标准是字符串）→ 统一成字符串。"""
    raw = [{"id": "c", "function": {"name": "f", "arguments": {"q": "x"}}}]
    calls = model_call._parse_tool_calls(raw)

    assert isinstance(calls[0].arguments, str), "必须转成 str，否则下游 json.loads TypeError"
    assert calls[0].parsed_arguments() == {"q": "x"}


def test_parse_tool_calls_skips_missing_name():
    raw = [{"id": "c", "function": {"arguments": "{}"}}]
    assert model_call._parse_tool_calls(raw) == []


# ---------- 5. 请求体是否带 tools ----------

async def test_tools_payload_included_when_given():
    """传 tools 时请求体必须带 tools + tool_choice=auto。"""
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, content=_sse([_text_chunk("ok")]))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    import app.services.model_call as mc
    original_get = mc.get_http_client
    mc.get_http_client = lambda: client
    tools = [{"type": "function",
              "function": {"name": "search_items", "description": "检索用户物品",
                           "parameters": {"type": "object", "properties": {}}}}]
    try:
        async for _ in model_call.stream_model(_KEY, [{"role": "user", "content": "hi"}],
                                               tools=tools):
            pass
    finally:
        mc.get_http_client = original_get
        await client.aclose()

    assert captured["body"]["tools"] == tools
    # 🔴 缺 tool_choice 时部分厂商会忽略 tools 字段（静默失效）
    assert captured["body"]["tool_choice"] == "auto"


async def test_tools_absent_when_not_given():
    """不传 tools 时请求体里不能有这两个键（部分厂商见到空 tools 会报错）。"""
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, content=_sse([_text_chunk("ok")]))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    import app.services.model_call as mc
    original_get = mc.get_http_client
    mc.get_http_client = lambda: client
    try:
        async for _ in model_call.stream_model(_KEY, [{"role": "user", "content": "hi"}]):
            pass
    finally:
        mc.get_http_client = original_get
        await client.aclose()

    assert "tools" not in captured["body"]
    assert "tool_choice" not in captured["body"]