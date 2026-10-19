import asyncio
import logging

from app.core.config import settings
from app.services.index_service import reap_once

logger = logging.getLogger(__name__)
INTERVAL = 300

async def _reap_once_with_log()->None:
    """扫一轮并记日志。**不抛异常** —— 扫失败不该让整个进程退出。"""
    try:
        picked = await reap_once()
        if picked:
            logger.info("reap %s 条待索引任务", picked)
        else:
            logger.info("reap：没有待索引任务")
    except Exception:
        # 🔴 异常只记不抛 —— 否则一轮失败进程就死了，
        #   5 分钟后才会有人发现「定时任务好像没在跑」
        logger.exception("reap_once 失败")


async def _loop()->None:
    while True:
        await asyncio.sleep(INTERVAL)
        await _reap_once_with_log()


async def main()->None:
    # 🔴 basicConfig 是 **logging 模块级**函数，不是 Logger 实例的方法。
    #   写成 logger.basicConfig(...) 会抛
    #   `AttributeError: 'Logger' object has no attribute 'basicConfig'`
    #   （2026-10-19 大宋启动时才发现，reaper 根本起不来）
    logging.basicConfig(level=logging.INFO)
    logger.info("reaper 启动，每 %ss 扫一次，僵死阈值 %ss", INTERVAL, settings.index_stale_seconds)
    # 🔴 启动时**先扫一次**再进 sleep 循环。
    #   原来 `while True: sleep(300); reap()` 的意思是「起来后干等 5 分钟才干第一件事」，
    #   66 条存量要等 5 分钟才开始处理 —— 联调时看起来像「定时任务没生效」。
    await _reap_once_with_log()
    await _loop()

if __name__ == "__main__":
    asyncio.run(main())
