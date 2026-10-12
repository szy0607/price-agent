"""进程内滑动窗口限流 —— 零 Redis 方案。

口径（与 AGENTS.md / 契约一致）：限流用进程内字典；多 worker 各自为政、
每人一份账，搬 Redis 是「上多 worker」那个触发点才该做的事，现在不提前铺路。

用法：
    check_rate_limit(f"upload:{user.id}", limit=10, window=60)
超限抛 BizError(RATE_LIMITED)。

边界：_windows 只在上限流 key 出现时创建，每个 key 的命中列表按窗口惰性清理；
key 数失控（> _KEY_CEILING）时整体清一次过期项——演示期够用，不假装是分布式限流。
"""
import time

from app.core.errors import BizError, ErrorCode

_windows: dict[str, list[float]] = {}
_KEY_CEILING = 10_000  # 超过就整体扫一次过期，防止字典无限涨


def check_rate_limit(key: str, limit: int, window: float) -> None:
    now = time.time()
    if len(_windows) > _KEY_CEILING:
        for stale in [k for k, hits in _windows.items()
                      if not hits or now - hits[-1] >= window]:
            del _windows[stale]
    hits = [t for t in _windows.get(key, []) if now - t < window]
    if len(hits) >= limit:
        raise BizError(ErrorCode.RATE_LIMITED, "操作太频繁，请稍后再试")
    hits.append(now)
    _windows[key] = hits
