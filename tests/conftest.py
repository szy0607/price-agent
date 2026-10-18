"""pytest 全局配置。

🔴 **最重要的一件事：把 arq 队列名改成测试专用**（2026-10-17 加）。

背景：`tests/test_index_service.py` 里有两处**故意**保持 `enqueue_sync` 的
真实实现——mock 掉反而测不到「投递失败自己吞掉」这条降级路径。但后果是
测试会往**生产的 `arq:queue`** 里塞真任务。跑完测试再起 worker，worker 会
消费到**测试造的假用户数据**并**真调向量模型 API（花钱）**。

实测：跑一次全量测试留下 39 个 `arq:job:*`，arq:queue 里是真任务。

解法：这里把队列名改成 `arq:queue:pytest`。worker 只监听 `arq:queue`，
所以测试任务**永远不会被 worker 执行**。job 定义仍会写进 `arq:job:*` 键
（arq 的设计如此），但没人消费就不会执行 —— 最多是几条垃圾键，过期自动清理。

⚠️ **必须在 import app 之前设**：redis_client.get_pool 是懒单例，
若在它已被创建后才设env，队列名不会变。所以放在文件最顶部。
"""

import os

# 🔴 在 import app.* 之前设置
os.environ.setdefault("ARQ_QUEUE_NAME", "arq:queue:pytest")