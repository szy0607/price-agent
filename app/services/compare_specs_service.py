"""A4 对比取参：从网络查每件商品的参数。

🔴 **这个模块存在的原因**：`a1_graph.compare` 节点要拿到「每件商品的参数」
才能做分维度对比。而这些商品**用户不一定有**（库里只有 1 条向量），
所以必须联网 ——复用 `spec_complete_service.complete_specs`（内部 = web_search + 主模型）。

**为什么不直接写在节点里**：节点只该关心「编排」，取参是独立能力。
拆出来才能单独测（**测试里全 mock，一次博查都不花**）。

🔴 **成本（⚠️ 真跑要花钱）**：
    每件商品 = 1 次博查（0.036 元）+ 1 次主模型调用。
    3 件 = **0.108 元/次对比**。测试里必须全 mock。
"""

import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError
from app.services import model_call, spec_complete_service

logger = logging.getLogger(__name__)

# 🔴 同时查几件。3 件要花 1.1 秒（0.108 元）—— 并发能省时间，
#   但**并发打满会让厂商限流**，3 件是「快」与「稳」的平衡点。
_CONCURRENCY = 3

# 单件商品的取参 prompt 上限：让 web_search 少返回点无关网页
_SEARCH_COUNT = 5


async def _fetch_one(item: str, user_id: int,
                     session: AsyncSession) -> tuple[str, dict | None]:
    """查一件商品的参数。**返回 (商品名, 参数 或 None)**。

    🔴 **失败返回 None 而不是抛**——理由与 a1_graph 的 search/compare 节点一致：
    异常会打断整个图，而「这件查不到」是可以**告诉模型继续**的信息。
    「把失败变成信息，而不是事故。」
    """
    try:
        draft = await spec_complete_service.complete_specs(
            name=item, category=None, user_id=user_id, session=session)
        return item, draft
    except BizError as exc:
        logger.warning("对比取参失败 item=%s: %s", item, exc.msg)
        return item, None
    except Exception:
        # 🔴 complete_specs 内部还有别的异常路径（httpx / json 解析），
        #   一律吞掉转成「查不到」。
        logger.warning("对比取参异常 item=%s", item, exc_info=True)
        return item, None


async def fetch_specs(items: list[str], user_id: int,
                      session: AsyncSession) -> dict[str, dict]:
    """批量取参。**返回 {商品名: 参数}，查不到的 key 不会出现在结果里**。

    ⚠️ 用 `asyncio.gather` 并发而不是循环 await —— 串行 3 件要 3.3 秒，
    并发只要 1.1 秒。用户等流式的时候这个差别很明显。
    """
    results = await asyncio.gather(
        *[_fetch_one(item, user_id, session) for item in items]
    )
    return {name: draft for name, draft in results if draft}


def format_specs_line(name: str, draft: dict) -> str:
    """把一份参数压成一行，给对比 prompt 用。

    ⚠️ **刻意压成一行**：对比的 prompt 里要放 3 件商品的参数，
    结构化太啰嗦会挤掉「按用户问题选维度」那段指令。
    """
    specs = draft.get("specs") or {}
    price = draft.get("price")
    bits = []
    if price is not None:
        bits.append(f"¥{price}")
    for k, v in specs.items():
        bits.append(f"{k}: {v}")
    return f"- {name}" + ("｜" + "；".join(bits) if bits else "")