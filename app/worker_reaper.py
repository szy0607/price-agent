import asyncio
import logging

from app.core.config import settings
from app.services.index_service import reap_once

logger = logging.getLogger(__name__)
INTERVAL = 300

async def _loop()->None:
    while True:
        await asyncio.sleep(INTERVAL)
        try:
            picked = await reap_once()
            if picked:
                logger.info(f"reap {picked}条任务")
        except Exception :
            logger.exception("reap_once 失败")


async def main()->None:
    logger.basicConfig(level = logging.INFO)
    logger.info("reaper 启动，每 %ss 扫一次，僵死阈值 %ss", INTERVAL, settings.index_stale_seconds)
    await _loop()

if __name__ == "__main__":
    asyncio.run(main())
