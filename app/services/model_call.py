import asyncio
import ipaddress
import json
import logging
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx

from app.core.errors import BizError, ErrorCode
from app.core.http_client import get_http_client
from app.services.api_key_service import KeyRecord


logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(35.0, connect=8.0)


class ModelCallError(Exception):
    """模型调用错误,不携带响应体内容"""


@dataclass
class ToolCall:
    """模型请求调用一个工具。

    arguments 是**未解析的 JSON 字符串**（不是 dict）：OpenAI 协议里它就是字符串，
    且流式下是分片到达的（见 _merge_tool_call_delta）。提前 json.loads 会因为
    半截字符串直接炸。
    """

    id: str
    name: str
    arguments: str

    def parsed_arguments(self) -> dict:
        """把 arguments 解析成 dict。**解析失败返回空 dict，不抛**。

        为什么吞：arguments 是模型自己生成的，可能不合 JSON（被截断、幻觉出
        别的格式）。让它炸掉整个请求没有意义——工具节点会收到空参数并自行
        兜底（检索用空 query 得到空结果，如实告诉模型即可）。
        """
        try:
            data = json.loads(self.arguments or "{}")
        except (ValueError, TypeError):
            logger.warning("tool_call arguments 不是合法 JSON: %r", self.arguments[:200])
            return {}
        return data if isinstance(data, dict) else {}


@dataclass
class StreamEvent:
    """流式产出的一格。原来只有文本，现在多了工具调用这一种。

    🔴 **不能再yield 裸 str**：模型决定调工具时 delta.content 是 null（内容全在
    delta.tool_calls 里），只yield str 会让整个响应一个字都不产出——前端看到
    「转圈半天然后失败」，而且**不报错**（2026-10-17 排查发现）。
    两种事件调用方必须能区分，所以用 dataclass 而不是字符串。
    """

    kind: Literal["text", "tool_call"]
    text: str = ""
    tool_call: ToolCall | None = None


def _merge_tool_call_delta(acc: dict[int, dict], delta_list: list) -> None:
    """把 delta.tool_calls 的分片并进累积器。**原地改 acc**。

    🔴 这是流式工具调用最容易写错的地方：tool_calls 是**数组**，每个元素只带
    自己那次的增量，靠 `index` 标识是哪一次调用。三种分片都要处理：

      首个 chunk： {"index":0, "id":"call_a1", "function":{"name":"search_items","arguments":""}}
      中间 chunk： {"index":0, "function":{"arguments":"{\\"query\\""}}
      末尾 chunk： {"index":0, "function":{"arguments":":\\"...\\"}"}}

    arguments 只能**拼接**不能覆盖——覆盖会把前面的片段丢掉，最终拿到残缺JSON。
    反过来 name/id 只在首个 chunk 出现，后续是 None，**不能覆盖成 None**。
    """
    for item in delta_list or ():
        idx = item.get("index", 0)
        slot = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if item.get("id"):
            slot["id"] = item["id"]
        fn = item.get("function") or {}
        if fn.get("name"):
            slot["name"] = fn["name"]
        piece = fn.get("arguments")
        if piece:
            slot["arguments"] += piece


def _parse_tool_calls(raw) -> list[ToolCall]:
    """非流式路径：从 message.tool_calls 提取工具调用。

    与流式的区别：**这里不需要累积**（非流式响应是完整的，一次拿全）。
    但仍然要防三件事，缺一个就是静默坏：
      - raw 是 None（模型没调工具）→ 返回空列表
      - 某个元素缺 name（模型给了残缺请求）→ 跳过并告警
      - arguments 不是字符串（部分厂商返 dict）→ 统一成字符串
    """
    if not raw:
        return []
    out: list[ToolCall] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        fn = item.get("function") or {}
        name = fn.get("name")
        if not name:
            logger.warning("tool_call[%s] 缺少函数名，已跳过", i)
            continue
        args = fn.get("arguments")
        if not isinstance(args, str):
            # 有些厂商把 arguments 返成 dict（标准是 JSON 字符串）。
            # 不统一的话下游 json.loads 会 TypeError。
            args = json.dumps(args, ensure_ascii=False) if args else ""
        out.append(ToolCall(id=item.get("id") or f"call_{i}", name=name, arguments=args))
    return out


def _log_truncation(data: dict)->None:
    usage = data.get("usage") or {}
    detail = usage.get("completion_tokens_details") or {}
    logger.warning(
        "model output truncated: completion=%s reasoning=%s",
        usage.get("completion_tokens"),
        detail.get("reasoning_tokens"),
    )

def validate_public_url(base_url: str)->None:
    """验证公共URL是否有效"""
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("公共URL必须是HTTPS协议且包含主机名")
    try :
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"公共URL {base_url} 无效") from exc
    if not infos:
        raise ValueError(f"公共URL {base_url} 无效")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])#得到IP地址对象
        if not ip.is_global:
            raise ValueError(f"目标地址不是公网地址")
async  def call_model(
        key: KeyRecord,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        max_token: int | None = 6000) -> tuple[str, str, list[ToolCall]]:
    """非流式。返回 (文本, 模型名, 工具调用列表)。

    🔴 返回值加了第三个元素 = **破坏性变更**。非流式链路（POST /chat/message）
    必须同步改成解包三个值，否则会静默拿到「文本=第一个工具调用对象」这种垃圾
    （旧代码只解包前两个，Python 不报错，多余的第三个被丢掉）。

    工具调用时 content 可能是 null（内容全在 tool_calls 里），所以这里把
    content 或空串返回，让调用方靠tool_calls 是否为空判断走哪个分支。
    """
    if not messages:
        raise ModelCallError("messages 不能为空")
    try:
        await asyncio.to_thread(validate_public_url, key.base_url)
    except ValueError as exc:
        raise BizError(ErrorCode.PARAM_INVALID, "配置的 base_url 不是可用的公网 https 地址") from exc
    url = key.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": key.model_name,
        "messages": messages,
        "max_tokens": max_token,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {
        "Authorization": f"Bearer {key.api_key}",
        "Content-Type": "application/json",
    }
    client = get_http_client()
    if client is None:
        async with httpx.AsyncClient(
                timeout=_TIMEOUT,
                follow_redirects=False,
            ) as one_off:
            resp = await one_off.post(url, headers=headers, json=payload)
    else:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code in(401, 403):
        # 本函数无 session，不能自己调 mark_invalid。**调用方必须在自己持有的
        # session 里标记 key 失效**，否则一个已死的 key 会被反复使用。
        raise ModelCallError(f"key 已被厂商拒绝，已标记为失效，请重新配置")
    if resp.status_code == 402:
        logger.warning("model call rejected: http 402 provider=%s body=%s",
                       key.provider, resp.text[:200])
        raise ModelCallError("模型服务已欠费，请前往对应平台充值后重试")
    if resp.status_code != 200:
        logger.warning("model call http %s ", resp.status_code)
        raise ModelCallError(f"模型调用失败")
    try:
        data = resp.json()
        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice["finish_reason"] or ""
        tool_calls = _parse_tool_calls(message.get("tool_calls"))
        content = message.get("content") or ""
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("model call unexpected response shape")
        raise ModelCallError("模型返回了无法解析的内容") from exc
    if not isinstance(content, str):
        raise ModelCallError("模型返回了无法解析的内容")
    if finish_reason == "length":
        _log_truncation(data)
    return content, data.get("model") or key.model_name, tool_calls


async def stream_model(
        key: KeyRecord,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        max_token: int | None = 6000) -> AsyncIterator[StreamEvent]:
    """流式调用，产出 AsyncIterator[StreamEvent]。**只负责生成**。

    契约有两条，调用方都要处理：
      1. `StreamEvent(kind="text", text=...)`——文本增量，照旧往 SSE 吐
      2. `StreamEvent(kind="tool_call", tool_call=...)`——模型要调工具

    🔴 **第2 条是 2026-10-17 新增的**：之前契约只有第 1 条，而模型决定调工具时
    delta.content 是 null，产出里一个字都没有——前端表现为「转圈半天然后失败」，
    且不报错。tools 参数=None 时行为与从前完全一致（回归见tests/test_model_call.py）。

    🔴 **tool_call 事件一定在流的最后**（收到 [DONE] 之后才 yield）：arguments 是
    分片到达的，中途发出去的是半截 JSON。

    🔴 **必须独立设 timeout，不能沿用 _TIMEOUT=35.0**：那是「整个请求 35 秒内完成」
    的总超时。流式下 6000 token 需 100–200 秒，沿用会把**每个长回答在 35 秒硬掐**，
    且截断发生得很自然→ 表现为「回答说到一半停了」，**不报错**，是最难查的一类问题。
    connect 保留 8 秒（连不上要快速失败），read 不设上限（等多久都行）。

    🔴 **401/403 不在这里标记 key 失效**：本函数没有 session，调不了 mark_invalid。
    只抛 ModelCallError，**由调用方（chat_stream）在自己持有的 session 里标记**——
    这是「移除 AsyncSession 参数」带来的责任转移点，别漏。

    usage / finish_reason 从流里捞出来打 truncated 日志：非流式下 _log_truncation
    直接读响应体，流式下 usage 只在最后一个 chunk 出现，漏了这条告警就**静默消失**
    （不报错，只少一行日志）。
    """
    if not messages:
        raise ModelCallError("messages 不能为空")
    try:
        await asyncio.to_thread(validate_public_url, key.base_url)
    except ValueError as exc:
        raise BizError(ErrorCode.PARAM_INVALID, "配置的 base_url 不是可用的公网 https 地址") from exc
    url = key.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": key.model_name,
        "messages": messages,
        "max_tokens": max_token,
        "stream": True,
        # 让厂商在最后一个 chunk 回 usage，否则拿不到 token 统计与截断信号
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools
        # 🔴 厂商默认可能要求必须指定 tool_choice，否则部分模型会忽略 tools。
        # "auto" =让模型自己决定调不调（这正是工具化的意义：固定前置是"总是调"）
        payload["tool_choice"] = "auto"
    headers = {
        "Authorization": f"Bearer {key.api_key}",
        "Content-Type": "application/json",
    }
    stream_timeout = httpx.Timeout(None, connect=8.0)
    client = get_http_client()
    one_off = None
    # 🔴 累积器放在 try 外声明：正常返回/异常都要能访问到（否则 except 分支
    # 里判断「有没有工具调用」会 NameError）
    tool_acc: dict[int, dict] = {}
    try:
        if client is None:
            one_off = httpx.AsyncClient(timeout=stream_timeout, follow_redirects=False)
            http = one_off
        else:
            http = client
        async with http.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code in (401, 403):
                await resp.aread()
                raise ModelCallError("key 已被厂商拒绝，已标记为失效，请重新配置")
            if resp.status_code == 402:
                body = (await resp.aread()).decode("utf-8", "replace")
                logger.warning("model stream rejected: http 402 provider=%s body=%s",
                               key.provider, body[:200])
                raise ModelCallError("模型服务已欠费，请前往对应平台充值后重试")
            if resp.status_code != 200:
                logger.warning("model stream http %s", resp.status_code)
                raise ModelCallError("模型调用失败")
            async for raw in resp.aiter_lines():
                line = raw.strip()
                if not line or not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    #🔴 这里只能 break，**不能 return**——return 会直接退出函数，
                    # 收尾时 yield tool_call 的那段代码根本执行不到
                    # （2026-10-17 实测：所有 tool_call 测试全红，无一产出）。
                    # 流已读完，跳出循环去统一收尾。
                    break
                try:
                    chunk = json.loads(body)
                except json.JSONDecodeError:
                    # 单个 chunk 坏了不该毁掉整条流：跳过继续读
                    logger.warning("model stream: bad chunk skipped")
                    continue
                usage = chunk.get("usage")
                if usage:
                    # 🔴 2026-10-19 修假告警：这里原来**只要有 usage 就打截断警告**，
                    #   但厂商在**正常结束的流末尾也会带 usage**（token 用量统计）。
                    #   症状：每次正常对话都刷
                    #   `WARNING model output truncated: completion=772 reasoning=193`
                    #   而实际输出完整、根本没截断。
                    #
                    #   **只有 finish_reason == "length" 才是真截断**
                    #   （模型撞 max_token 被硬切）。非流式那条判据本来就对
                    #   （见下面 `if finish_reason == "length"`），流式这条漏了——
                    #   **两边口径不一致**。
                    #
                    # ⚠️ usage 的 chunk 常常不带 choices，所以 finish_reason 从同一个
                    #   chunk 的 choices 里取；**取不到就不告警**
                    #   （宁可漏报不可误报——假告警会让人以为出了问题）。
                    _u_choices = chunk.get("choices") or []
                    _u_fr = (_u_choices[0].get("finish_reason")
                             if _u_choices else None)
                    if _u_fr == "length":
                        _log_truncation({"usage": usage})
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                # 🔴 tool_calls 必须先处理，且要累积——它是分片到达的
                # （见 _merge_tool_call_delta）。这里只收不发：分片收齐之前
                # 发出去的 arguments 是半截 JSON，工具节点会解析失败。
                if delta.get("tool_calls"):
                    _merge_tool_call_delta(tool_acc, delta["tool_calls"])
                piece = delta.get("content")
                if piece:
                    yield StreamEvent(kind="text", text=piece)
        #🔴 流结束（收到 [DONE]）后才把工具调用发出去。
        # 此时 arguments 才是完整的 JSON 字符串。
        for idx in sorted(tool_acc):
            slot = tool_acc[idx]
            if not slot["name"]:
                # 只有 arguments 没有 name = 模型给了个残缺请求，跳过
                logger.warning("tool_call 缺少函数名，已跳过: %r", slot)
                continue
            yield StreamEvent(
                kind="tool_call",
                tool_call=ToolCall(
                    id=slot["id"] or f"call_{idx}",
                    name=slot["name"],
                    arguments=slot["arguments"],
                ),
            )
    finally:
        if one_off is not None:
            await one_off.aclose()
