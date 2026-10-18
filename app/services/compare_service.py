"""A4 分维度对比。

    与 compare_specs_service 的分工：
      compare_specs_service：联网把每件商品的参数查出来（花钱的部分）
      本模块：按用户问题选维度 → 逐维度判断 → 输出对比表

    🔴 **为什么不给单一总分**（大宋 18:20 拍板走分维度的理由，见
    docs/A4对比与A5推荐-设计.md §2.1）：总分会掩盖真实差异 ——
    「索尼降噪 9 分 / 佩戴 6 分」与「AirPods 降噪 6 分 / 佩戴 9 分」
    用总分算可能是 7.5 vs 7.5「打平」，用户看完还是不知道买哪个。

    🔴 **本模块不做联网**（不花钱），因此可以随便测。
"""

import json
import logging

from app.services import model_call

logger = logging.getLogger(__name__)

# 🔴 维度上限 5 个：7 个以上前端表格要横向滚动，手机上没法看；
#   且维度多说明模型在「凑数」而不是在回答问题（大宋 22:40 拍板三件上限时的同款理由）。
MAX_DIMENSIONS = 5

_COMPARISON_SYSTEM = """你是一个商品参数对比助手。

**你的任务**：根据用户「真正关心的问题」，选出对比维度，逐维度判断，输出对比表。

**绝对不要做的事**：
- 不要给出「综合评分」或「总分」。用户会把它当成客观结论，
  但那只是你按自己选的维度算出来的，会掩盖真实差异。
- 不要对比用户没问的方面。用户问「戴久了耳朵不难受」时，
  对比表里就不该出现「降噪深度」。
- 不要编造参数。参数字段里没有的就是「资料未提及」。

**输出格式**（严格 JSON，不要包裹 markdown 代码块）：
{
  "dimensions": [
    {"name": "维度名", "values": {"商品名A": "判断", "商品名B": "判断"}, "winner": "商品名A"}
  ],
  "summary": "一句话总结：按用户关注的点，谁更合适、为什么"
}

`winner` 填占优的商品名；打平填 null。**最多 5 个维度。**"""


def build_messages(items: list[str], specs_lines: list[str],
                   question: str) -> list[dict]:
    """拼对比 prompt。

    🔴 **question 为空时走「按品类对比」**（三道保险的第三道）：
    模型漏填 question 时退化到品类通用维度，远好过整个对比失败。

    🔴 **返回 dict 而不是 HumanMessage/SystemMessage**（2026-10-18 实测后改）：
    本项目 messages 全链路是 dict（见 a1_graph 的 `_append_messages` 注释）。
    我实测过把 `HumanMessage` 丢进那个 reducer —— **它不会转，会原样混进列表**：
        [dict, HumanMessage(content='x', ...)]        ← 破坏全链路 dict 约定
    所以这里全程用 dict，靠 `role` 字段区分 system / human。
    """
    focus = (f"**用户真正关心的问题**：「{question}」\n"
             f"→ 只对比与这个问题相关的维度。\n"
             if question else
             "用户没有说明关注点，**按商品品类的通用关键参数对比**。\n")

    parts = [focus, "商品参数（来源：网络，仅供参考）：", *specs_lines]
    return [
        {"role": "system", "content": _COMPARISON_SYSTEM},
        {"role": "user", "content": "\n".join(parts)},
    ]


def parse_comparison(raw: str, items: list[str]) -> dict:
    """把模型的 JSON 输出解析成对比结果。**解析失败返回降级结构**。

    🔴 **降级而不是抛**：模型输出不可解析时，让 decide 拿一段「没能完成结构化对比」
    的文字继续答，比中断整轮对话好（口径与 search/compare 节点一致）。

    降级结构：dimensions 为空 + summary 说明情况 —— 这样 decide 仍然能
    把「模型说了什么」转述给用户，而不是假装什么都没发生。
    """
    text = (raw or "").strip()
    #模型有时会包markdown 代码块```json ... ```
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        logger.warning("对比结果不是合法 JSON，长度=%d", len(raw or ""))
        return {"dimensions": [], "summary": "未能生成结构化对比",
                "raw": raw}

    if not isinstance(data, dict):
        return {"dimensions": [], "summary": "对比结果格式异常", "raw": raw}

    dims = data.get("dimensions")
    if not isinstance(dims, list):
        dims = []
    # 🔴 维度上限在这里也兜一次（跟 items 的三件上限同款：模型会无视指令）
    truncated = len(dims) > MAX_DIMENSIONS
    if truncated:
        dims = dims[:MAX_DIMENSIONS]

    return {
        "dimensions": dims,
        "summary": str(data.get("summary") or ""),
        "truncated": truncated,
        "items": items,
    }


def format_comparison(result: dict) -> str:
    """把解析后的对比渲染成给模型看的文本（它会基于这段组织最终回答）。

    ⚠️ **不给单一总分**，只给逐维度占优方 + 总结 —— 与 parse 的口径一致。
    """
    dims = result.get("dimensions") or []
    summary = result.get("summary") or ""
    if not dims:
        #降级路径：把模型原话带上，别假装什么都没发生
        raw = result.get("raw")
        return (f"未能完成结构化对比（模型输出无法解析）。"
                f"模型原始输出：{(raw or '')[:400]}")

    lines = []
    for d in dims:
        if not isinstance(d, dict):
            continue
        name = d.get("name") or "(未命名维度)"
        values = d.get("values")
        winner = d.get("winner")
        if isinstance(values, dict):
            cell = "｜".join(f"{k}: {v}" for k, v in values.items())
        else:
            cell = str(values)
        mark = f"（{winner} 占优）" if winner else "（持平）"
        lines.append(f"- {name}: {cell} {mark}")

    body = "按用户关注的维度对比：\n" + "\n".join(lines)
    if summary:
        body += f"\n总结：{summary}"
    if result.get("truncated"):
        body += "\n（维度过多已截断，只保留前 5 个）"
    body += "\n⚠️ 参数来源：网络，仅供参考。"
    return body