"""截断告警的修复验证（2026-10-19）。

## 背景：这是个**假告警**

真机日志里每次正常对话都刷：

```
WARNING app.services.model_call: model output truncated:
        completion=772 reasoning=193
```

根因：流式路径里**只要 chunk 带 usage 就打截断警告**，
而厂商在**正常结束的流末尾也会带 usage**（token 用量统计）。
`finish_reason == "length"`（真截断）的判据**只有非流式那条有**——
**两边口径不一致**。

## 两条测试缺一不可

- 「不再误报」——修好了没
- 「真截断仍然报」——**防修过头**（为了让告警消失而删掉告警）
"""

import json
import logging

import httpx
import pytest

from app.services import model_call
from app.services.api_key_service import KeyRecord

pytestmark = pytest.mark.asyncio

# 🔴 model_call 每个入口都先跑 validate_public_url，它做真实 DNS 解析。
#    测试用的假域名解析不了 → ValueError，压根走不到 stream_model。
#    **不要用真实域名**：会让测试依赖外部 DNS，CI 上必挂。
# （这坑我第一版又踩了一次：先换 .invalid、又换 127.0.0.1 —— 后者被 SSRF
#   校验当私网地址挡掉。正确做法就是 stub 掉校验函数。）
model_call.validate_public_url = lambda base_url: None

_KEY = KeyRecord(key_id=1, provider="test",
                 base_url="https://api.example.invalid/v1",
                 api_key="sk-test", model_name="test-model")


def _sse(chunks: list[dict]) -> bytes:
    lines = [b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks]
    lines.append(b"data: [DONE]\n\n")
    return b"".join(lines)


async def _run(chunks: list[dict]):
    """跑一次 stream_model，返回 (text, tool_calls, 捕获的 WARNING 文本)。"""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, content=_sse(chunks)))
    client = httpx.AsyncClient(transport=transport)
    old_client = model_call.get_http_client
    model_call.get_http_client = lambda: client

    records: list[str] = []

    class H(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    log = logging.getLogger("app.services.model_call")
    handler = H()
    old_level = log.level
    log.addHandler(handler)
    log.setLevel(logging.WARNING)
    try:
        text, tool_calls = "", []
        async for ev in model_call.stream_model(_KEY, [{"role": "user", "content": "hi"}]):
            if ev.kind == "text":
                text += ev.text
            elif ev.tool_call:
                tool_calls.append(ev.tool_call)
        return text, tool_calls, records
    finally:
        log.removeHandler(handler)
        log.setLevel(old_level)
        model_call.get_http_client = old_client
        await client.aclose()


def _truncations(records: list[str]) -> list[str]:
    return [r for r in records if "truncated" in r]


# ---------- 核心：不再误报 ----------

async def test_normal_end_with_usage_does_not_warn():
    """🔴 **本文件最重要的一条**：正常结束（带 usage）不该报截断。

    复现大宋真机那条日志：`completion=772 reasoning=193`，输出其实完整。
    """
    chunks = [
        {"choices": [{"delta": {"content": "你好"}}], "model": "m"},
        # ⚠️ 流末尾厂商会带 usage（token 统计），finish_reason 是 "stop"
        {"choices": [{"delta": {}, "finish_reason": "stop"}],
         "usage": {"completion_tokens": 772,
                   "completion_tokens_details": {"reasoning_tokens": 193}}},
    ]
    text, _tc, records = await _run(chunks)

    assert text == "你好", "正文应该完整收到：" + repr(text)
    assert not _truncations(records), (
        "正常结束不该报截断，实际报了：" + str(_truncations(records)))


async def test_usage_without_finish_reason_does_not_warn():
    """🔴 usage 的 chunk 常常**不带 choices**，取不到 finish_reason 就不报。

    「宁可漏报不可误报」——假告警会让人以为出了问题。
    """
    chunks = [
        {"choices": [{"delta": {"content": "hi"}}], "model": "m"},
        {"usage": {"completion_tokens": 500}},      # 没有 choices
    ]
    _text, _tc, records = await _run(chunks)
    assert not _truncations(records)


async def test_tool_call_flow_also_not_warned():
    """🔴 工具调用路径末尾也会带 usage —— 同样不该报。

    大宋真机那次是「OPPO Find X9s Pro 和 vivo X300 直接对比」，
    走 compare 工具（会调两次模型），两次都刷了假告警。
    """
    chunks = [
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "c1", "type": "function",
            "function": {"name": "compare_items", "arguments": "{}"},
        }]}}], "model": "m"},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}],
         "usage": {"completion_tokens": 300}},
    ]
    _text, tc, records = await _run(chunks)
    assert len(tc) == 1, "工具调用应该被解析出来"
    assert not _truncations(records)


# ---------- 🔴 反面：真截断仍然要报（防修过头） ----------

async def test_real_truncation_still_warns():
    """🔴 **修过头就是漏报** —— finish_reason == "length" 必须仍然告警。

    这条是防「为了让告警消失而删掉告警」的。
    """
    chunks = [
        {"choices": [{"delta": {"content": "很长的内容"}}], "model": "m"},
        {"choices": [{"delta": {}, "finish_reason": "length"}],
         "usage": {"completion_tokens": 6000,
                   "completion_tokens_details": {"reasoning_tokens": 100}}},
    ]
    _text, _tc, records = await _run(chunks)

    trunc = _truncations(records)
    assert trunc, "真截断（finish_reason=length）必须告警"
    assert "6000" in trunc[0], "告警里应带 completion token 数：" + trunc[0]