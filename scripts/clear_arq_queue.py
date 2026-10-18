"""清空 arq 任务队列。开发调试用，可重复执行。

为什么需要它（2026-10-17 实测踩到）：
  - 队列里堆着**测试造的假用户任务**，起了 worker 会被消费并**真调向量模型 API（花钱）**
  - 或worker 崩了留下一堆永远不会被执行的孤儿任务，reaper 重投时会撞 _job_id 去重

🔴 **arq 0.28 的 `arq:queue` 是 zset（有序集合），不是 list**。
   文档里曾写`redis-cli DEL arq:queue` —— DEL 对 zset 恰好能用，
   但当时给的 Python 备选方案用了 `pool.delete("arq:queue")`，
   而**真正要清的不止队列本身**：`arq:job:*` 里还存着每个任务的定义。
   只删队列不删定义，会留下一堆`arq:job:*` 垃圾键（它们会自然过期，但很难排查）。
   本脚本两个都清。

用法：
    python scripts/clear_arq_queue.py            # 只清生产队列 arq:queue
    python scripts/clear_arq_queue.py --all      # 连测试队列一起清
    python scripts/clear_arq_queue.py --dry-run  # 只看有什么，不删
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def main(dry_run: bool, clear_all: bool) -> None:
    from app.core.config import settings
    from app.core.redis_client import TEST_QUEUE, _DEFAULT_QUEUE

    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_url)
    try:
        targets = [_DEFAULT_QUEUE, TEST_QUEUE] if clear_all else [_DEFAULT_QUEUE]

        for name in targets:
            kind = await client.type(name)
            size = await client.zcard(name) if kind == b"zset" else 0
            print(f"队列 {name}：type={kind.decode()} 成员数={size}")
            if size and not dry_run:
                removed = await client.delete(name)
                print(f"  -> 已删除（{removed} 个键）")

        # 任务定义键：无论清哪个队列，这些都可能残留
        job_keys = await client.keys("arq:job:*")
        print(f"任务定义 arq:job:* 共 {len(job_keys)} 个")
        if job_keys and not dry_run:
            await client.delete(*job_keys)
            print(f"  -> 已删除 {len(job_keys)} 个任务定义")
    finally:
        await client.aclose()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    allq = "--all" in sys.argv
    if dry:
        print("=== DRY RUN：以下只是查看，不会删除 ===")
    asyncio.run(main(dry, allq))