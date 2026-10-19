"""A5 推荐：按画像推荐**用户还没有的**商品。

🔴 **与大宋 18:20 定的关系**：「推荐不局限于用户的商品库」——
    候选必须来自**联网**，不是从用户库里挑。所以本模块与
    `compare_specs_service` 的区别是**先搜再提**，而不是拿到商品名直接提。

    ## 流程（4 步）
    ```
    ① 读画像        profile_service.load_profile_context（现成，0 成本）
    ② 画像 → 搜索词   主模型，1 次（关键：🔴 见下面的隐私红线）
    ③ 搜候选商品      web_search × N（花钱）
    ④ 提参数 + 排序   compare_specs_service + 主模型
    ```

    ## 🔴 隐私红线（最容易犯且不报错）
    **绝不能把用户的画像/物品库内容原样当搜索词发给博查。**
    那是把用户购物数据出境，撞项目铁律「隐私最小化」。

    正例 ❌ → ✅：
    ```
    ❌ "用户有3件索尼耳机，买个类似的降噪耳机"    ← 购物数据出境
    ✅ "降噪耳机 2000元 续航长"                    ← 从画像抽象出的商品特征
    ```
    第 ② 步的 prompt 里**明确要求模型做这层抽象**，
    并且搜完之后**不打回任何含用户身份的信息**。

    ## 成本（⚠️ 真跑要花钱）
    单次推荐 ≈ 1 次主模型（搜词）+ 1-3 次博查 + N 次取参 + 1 次排序
    **≈ 0.1-0.2 元**（详见 docs/A4对比与A5推荐-设计.md §3.1）。
"""

import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError
from app.services import (model_call, profile_service, search_filter,
                         web_search_service)
from app.services.api_key_service import KeyRecord
from app.services import compare_specs_service

logger = logging.getLogger(__name__)

# 🔴 候选商品数上限：4 个。再多用户也不会看，而且每个都要 1 次博查（0.036 元）。
MAX_CANDIDATES = 4
# 搜索次数上限。一次搜索拿 5 条，2-3 次通常够找出 3-4 个候选。
MAX_SEARCHES = 3


# ---------- ② 画像 → 搜索词 ----------

_QUERY_HINT_SYSTEM = """你在为一个「智能导购助手」生成**网络搜索词**。

输入是用户的偏好画像。你要做的是：**把画像抽象成商品搜索特征**。

绝对不要做的事：
- 不要把用户的具体商品、订单、价格、历史**原样**写进搜索词。
  那些是用户隐私，不该发给搜索服务。
- 不要写「用户」「我朋友」这类人称，用商品特征本身表述。

正确示范：
  画像说「买过3件索尼降噪耳机，偏好长续航」→ 搜索词「降噪耳机 长续航 2000元」
  画像说「偏好运动跑步相关」→ 搜索词「跑鞋 缓震 轻便」

输出格式（严格 JSON，不要 markdown 代码块）：
{"searches": ["搜索词1", "搜索词2"]}

最多给 2 个搜索词，每个 5-15 个字。"""


async def build_searches(profile_text: str, user_question: str,
                         key: KeyRecord) -> list[str]:
    """从画像 + 用户问题生成搜索词。**失败返回空列表**（不是抛）。

    🔴 **没有画像时也能用**——退化成「按用户问题直接搜」。
    新用户没画像是很正常的状态，不该因此推荐不了。
    """
    hint = (f"用户当前的问题：{user_question}\n"
            if user_question else "")
    body = (f"{hint}"
            f"用户偏好画像：\n{profile_text}\n\n"
            "请生成搜索词。")

    try:
        raw, _model, _tc = await model_call.call_model(
            key, [{"role": "system", "content": _QUERY_HINT_SYSTEM},
                  {"role": "user", "content": body}])
    except Exception:
        logger.warning("生成搜索词失败，退化为直接用用户问题搜", exc_info=True)
        return []

    try:
        data = json.loads(_strip_fence(raw))
        searches = data.get("searches") or []
        if not isinstance(searches, list):
            return []
        return [str(s).strip() for s in searches[:MAX_SEARCHES] if str(s).strip()]
    except (ValueError, TypeError, AttributeError):
        logger.warning("搜索词输出不是合法 JSON")
        return []


def _strip_fence(raw: str | None) -> str:
    """剥掉模型可能加的 ```json 代码块围栏。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


# ---------- ③ 搜候选 ----------

async def search_candidates(searches: list[str]) -> list[str]:
    """按搜索词找候选商品名。**去重**，返回最多 MAX_CANDIDATES 个。

    🔴 **这里只用博查的 `name` 字段**（网页标题）当商品名——
    它可能含「参数_详细参数_太平洋产品报价」这类后缀，
    下一阶段 `complete_specs` 会再搜一次并自己纠偏，所以这里不用过度清洗。
    """
    if not searches:
        return []

    async def one(q: str) -> list[dict]:
        try:
            return await web_search_service.web_search(q, count=5)
        except BizError as exc:
            logger.warning("搜索失败 q=%s: %s", q, exc.msg)
            return []
        except Exception:
            logger.warning("搜索异常 q=%s", q, exc_info=True)
            return []

    batches = await asyncio.gather(*[one(q) for q in searches])

    # 🔴 2026-10-19 改用 search_filter：
    #   原来这里自己写了一套去重（前18 字），**实测基本无效**——
    #   「精选_京东牛奶_国内优惠排行_第203页」与「...第124页」
    #   前 18 字里第 203 vs 第 124 不同，两个都留下了，
    #   于是用户看到的是「同一件商品的 6 个不同页面」。
    #   过滤器会挡掉聚合页 + 按主体名去重。见 search_filter 模块docstring。
    merged: list[dict] = []
    for batch in batches:
        merged.extend(batch)
    return [it["name"] for it in
            search_filter.clean_results(merged, MAX_CANDIDATES)]


# ---------- ④ 排序 ----------

_RANK_SYSTEM = """你在按用户偏好给候选商品排序。

**只做排序，不要编造参数。** 参数字段里没有的信息不许出现在理由里。

输出格式（严格 JSON，不要 markdown 代码块）：
{"items": [
  {"name": "商品名", "reason": "为什么适合他（必须指向他画像里的具体偏好）"}
]}

最多 4 条，按推荐顺序排。reason 要具体，
「性价比高」这种空话等于没说——要说「他画像里偏好续航 30 小时以上」。"""


def build_rank_prompt(profile_text: str, user_question: str,
                      specs: dict[str, dict]) -> list[dict]:
    """拼排序 prompt。"""
    lines = [compare_specs_service.format_specs_line(n, d)
             for n, d in specs.items()]
    focus = (f"用户当前的问题：{user_question}\n" if user_question else "")
    body = (f"{focus}"
            f"用户偏好画像：\n{profile_text}\n\n"
            f"候选商品参数（来源：网络，仅供参考）：\n" + "\n".join(lines))
    return [{"role": "system", "content": _RANK_SYSTEM},
            {"role": "user", "content": body}]


def parse_ranking(raw: str, available: list[str]) -> list[dict]:
    """解析排序结果，**过滤掉不在候选里的 name**。

    🔴 **必须过滤**：模型可能编造一个不存在的商品名，或把名字写错。
    不过滤的话会给用户推荐一个「不存在」的商品——**不报错，但推荐是假的**。
    """
    try:
        data = json.loads(_strip_fence(raw))
        items = data.get("items")
        if not isinstance(items, list):
            return []
    except (ValueError, TypeError, AttributeError):
        return []

    allowed = set(available)
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        # 宽松匹配：模型可能把「索尼 WH-1000XM5」写成「索尼WH-1000XM5」
        matched = next((a for a in allowed
                        if a == name or a.replace(" ", "") == name.replace(" ", "")
                        or name in a or a in name), None)
        if not matched:
            logger.info("排序结果里的「%s」不在候选中，已丢弃", name)
            continue
        out.append({"name": matched,
                    "reason": str(it.get("reason") or "").strip()})
    return out


def format_recommendation(rankings: list[dict], specs: dict[str, dict]) -> str:
    """渲染成给模型看的文本。"""
    if not rankings:
        return ("未找到合适的推荐（可能搜索没结果，"
                "或没有与画像匹配的候选）。请直接说明情况，不要编造商品。")

    lines = []
    for i, r in enumerate(rankings, 1):
        draft = specs.get(r["name"], {})
        price = draft.get("price")
        price_txt = f"¥{price}" if price is not None else "价格未提及"
        lines.append(f"{i}. {r['name']}（{price_txt}）")
        if r.get("reason"):
            lines.append(f"   推荐理由：{r['reason']}")

    return ("根据你的偏好，推荐以下商品：\n" + "\n".join(lines) +
            "\n⚠️ 参数来源：网络，价格随渠道变动，仅供参考。")