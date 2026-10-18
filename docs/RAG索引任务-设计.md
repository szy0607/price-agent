# RAG 索引任务链路 — 设计

> 拍板沿革：2026-10-16 20:51 大宋拍板**不建 `embedding_task` 表**，改用
> **业务表状态列 + arq 队列 + 独立 reaper 进程**。20:56 最终确认七项决策（见 §11）。
> 本文是施工依据，**代码由大宋写，小宋出文档 + 逐文件审**。
>
> 前置：docs/流式输出-设计.md 已完成；`app/repository/vector_repo.py`（检索层）
> 与 `app/services/embed_slice.py`（切片）已就绪，本设计只补「谁去调它」。

---

## 0. 方案全貌

```
① 保存业务数据（HTTP 请求内，MySQL 事务）
   INSERT/UPDATE 商品  +  index_status='PENDING'     ← 同一事务，一起 commit
        │
        ├─ 事务提交成功后，投 arq 队列（Redis）
        │  投递失败 → 只记日志，状态留 PENDING，等 reaper 兜（§6.2）
        ▼
② arq worker（独立进程，async def，与全异步栈同构）
   置 RUNNING → 调 embedding 模型 → 写 PGVector
        │
        ▼
③ 🔴 只有 PGVector 写入成功，才置 SYNCED（大宋定的地基约束）
   失败 → 抛 Retry 让 arq 重试；用尽 → 置 FAILED，等 reaper 兜
        ▼
④ reaper 进程（独立，每 5 分钟）
   捞PENDING/RUNNING 超时/FAILED 的行 → 重新投队列
```

**与 00:36 那版的差别**：不建独立任务表，改在业务表上挂两列。省一张表 + 它的 repo/迁移/清理逻辑，代价是**三张表都要加列**（§1）。

---

## 1. 数据模型：三张表各加两列

### 1.1 加在哪

`cart_item` / `owned_item` / `purchase_record` ——**三张都要**，因为 `SOURCE_TYPES = ("cart", "owned", "purchase")`（`vector_repo.py:10`）。

```python
# app/models/cartitem.py / owned_item.py / purchase_record.py 各加：
index_status : Mapped[str] = mapped_column(
    String(16), nullable=False, default="PENDING", server_default=text("'PENDING'")
)
index_time : Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

### 1.2 两个字段的职责边界（**别混**）

| 字段 | 何时写 | 写什么 | 为什么需要 |
|---|---|---|---|
| `index_status` | 每次改动都写 | 当前索引状态 | RAG 判断能否检索；reaper 决定捞谁 |
| `index_time` | **只在置 SYNCED 时**写 | 那次的时刻 | 「用户上次成功索引是什么时候」 |

**`index_time` 置 RUNNING 时不要动** —— 它记的是「成功时刻」不是「最后尝试时刻」。混了就失去意义。

### 1.3 🔴 状态值的命名分歧（要写明，否则后来人会改错）

| 体系 | 风格 | 在哪 |
|---|---|---|
| 索引状态 | **大写** `PENDING`/`RUNNING`/`SYNCED`/`FAILED` | 本设计，大宋拍板 |
| 消息状态 | 小写 `completed`/`interrupted`/`failed` | `chat_message.status` |

两套并存。**大宋只为本设计定了大写，没说统一** —— 本文按拍板执行，但**§11 遗留一条「是否统一」给未来定**。改任何一边都要同步另一边，否则跨模块判断会静默失效。

### 1.4 不加索引（刻意的）

不加 `index_status` 单列索引。**理由**：三张表每人的数据量在几百~几千行，全表扫 `WHERE index_status IN (...)` 走索引反而不如顺序扫（`vector_repo.search_similar` 里「每人的向量就几百条，暴力扫比走索引快」是同一条理由）。**十万量级再考虑加。**

### 1.5 迁移纪律

`alembic revision --autogenerate` 后**逐行读**，确认三张表都加上了、且 `server_default` 没漏（autogenerate 在加NOT NULL 列时**经常漏 server_default**，导致存量行插入失败）。最后 `alembic current == alembic heads`。

---

## 2. 🔴 事务边界：置 PENDING 必须和业务数据同一个事务

**这是整个链路最容易写错的一处。**

```python
# ❌ 错误：分两次提交
row = CartItem(..., index_status="PENDING")   # 第一次 commit
await session.commit()
# ← 崩在这里 = 商品存了但状态还是 SYNCED，永远不会重新索引（静默坏）
await session.execute(update(...).values(index_status="PENDING"))
await session.commit()

# ✅ 正确：同一个事务
row = CartItem(..., index_status="PENDING")   # INSERT 时就带上
session.add(row)
await session.commit()      # 业务数据 + PENDING 一起落库
```

**新建时**：`INSERT` 直接带 `index_status='PENDING'`。
**更新时**：`UPDATE` 同一语句里 `SET name=..., index_status='PENDING'`。

**为什么必须这样**：状态列是「这份数据需要重建索引」的**声明**。声明和数据分两次写，中间任何一步崩溃都会产生「数据变了但没人知道要重建」的永久不一致——**而且不报错，只是这件商品永远检索不到**。

---

## 3. 🔴 Redis 投递必须在 commit **之后**

```python
async with async_session_local() as session:
    async with session.begin():
        # ... 业务数据 + index_status='PENDING'
    # ← 事务已提交（async with 块结束）
# ← 事务块外才投递
ok = await index_queue.enqueue_sync(user_id, "cart", row.id)
if not ok:
    logger.warning("投递失败，留 PENDING 等 reaper")
```

**为什么不能放进事务里**：

| 放里面 | 后果 |
|---|---|
| commit 失败 | Redis 里已有任务，但MySQL 没数据 → worker 处理一个不存在的 id |
| Redis 投递失败 | 事务回滚 → **用户数据丢了**（商品根本没存上） |

**Redis 没有「跟着 MySQL 事务回滚」的机制**，所以只能放后面。

### 3.1 投递失败绝不能回滚业务事务

数据已经存了（用户看得见），回滚就是丢用户数据。**正确做法**：记日志，状态留 `PENDING`，让 reaper 兜。**这正是 reaper 存在的核心价值**——它兜的不只是「worker 崩溃」，还有「Redis 投递瞬间失败」。

---

## 4. arq worker

### 4.1 为什么是 arq 而不是 RQ（大宋 20:56 拍板，理由备查）

**实测依据**：RQ 的 worker 是同步阻塞的（任务函数必须 `def`），而本项目全异步（SQLAlchemy 2.x 异步 + aiomysql + asyncpg + `httpx.AsyncClient`）。用 RQ 需在同步 worker 里 `asyncio.run()` 包一层，每次调用建销事件循环，且 `AsyncClient` 无法跨任务复用。

**arq 的任务函数是 `async def`**，与全栈同构，无需任何包装。

### 4.2 WorkerSettings（`app/worker.py`，新建）

```python
from arq.connections import RedisSettings

async def startup(ctx: dict) -> None:
    """起 PG 引擎 + HTTP 客户端 —— 与 lifespan 同款，否则 PG 引擎是 None。"""
    start_http_client()
    start_pg_engine()
    ctx["pg_ready"] = True

async def shutdown(ctx: dict) -> None:
    await close_http_client()
    await close_pg_engine()

class WorkerSettings:
    functions = [index_service.sync_one]      # ← arq 按函数名注册
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host=..., port=6379)
    # job_timeout 要大于 embedding 调用的 20 秒 timeout，见 §4.5
    job_timeout = 60
    max_tries = 3
```

**启动命令**（`docs/启动命令.md` 要补一条）：
```bash
arq app.worker.WorkerSettings
```

### 4.3 🔴 `on_startup` 必须起 PG 引擎

`pg_session.py:10` 的 `_engine` 是**模块级全局**，由 `start_pg_engine()` 赋值，`get_pg_session()` 读它（:36-39）。

**worker 是独立进程**，不跑 FastAPI 的 lifespan，所以 **`_engine` 恒为 None**，任何 PG 调用都会抛 `BizError("未配置向量库")`。**忘记这行 = worker 全程失败，且报错文案误导（会以为是 PG_URL 没配）。**

### 4.4 任务函数的三态落库

```python
async def sync_one(ctx: dict, user_id: int, source_type: str, item_id: int) -> None:
    """把一件商品向量化并写入 PG。**只有 PG 成功才置 SYNCED**。"""
```

**执行顺序（大宋定的地基约束，逐条对应）**：

```
1. 置 RUNNING            （MySQL）
2. 读业务数据 + 切片      （MySQL → embed_slice）
3. 调 embedding 模型      （embedding_client，需 MySQL session 查 key）
4. 写 PGVector           （vector_repo.upsert_embedding，自开 PG session）
5. 置 SYNCED + 写 index_time   （MySQL）  ← 🔴 必须在 4 成功之后
```

**为什么 RUNNING 要先置**：worker 崩溃时，能从「停在哪一步」看出是模型慢还是 PG 写失败。没有 RUNNING 就只有 PENDING 和 SYNCED 两态可辨，排查时抓瞎。

**为什么第 5 步必须在第 4 步之后**：这是大宋明确说的约束。**反过来的话**，PG 写失败但状态已标 SYNCED → RAG 认为可检索 → 检索命中一条不存在的向量 → **模型拿着空数据回答，且不报错**。

### 4.5 三个超时不能混

| 超时 | 值 | 谁的 |
|---|---|---|
| embedding HTTP timeout | 20 秒（已有） | `embedding_client` |
| arq `job_timeout` | **60 秒** | 需 > 20，否则任务被 arq 砍掉但模型调用还在跑 |
| reaper 判 RUNNING 僵死 | 建议 **10 分钟** | 依据：20 秒 × 30 倍（沿用 00:36 的推算） |

### 4.6 🔴 失败处理：**按可重试性分流**，不是一律抛 Retry

> 2026-10-17 大宋拍板改为异常类型分流。下文「原方案（错误）」保留，是为了说明
> 为什么不能一律重试——那段是真会发生的坑，不是假设。

#### 四种错误，两种可重试性

`embedding_client` 的错误**不是同质的**，全走 `raise Retry` 是错的：

| 异常类型 | 触发 | 可重试 | 依据 |
|---|---|---|---|
| `EmbeddingKeyRejected` | 401/403 | ❌ | 本函数已 `mark_invalid`，key 已死，重试只是重复撞同一堵墙 |
| `EmbeddingDimMismatch` | 向量长度 ≠ 1024 | ❌ | 配置错，改配置才能好，重试到天荒地老同一结果 |
| `EmbeddingCallFailed` | 非 200（含 402 欠费/网关 5xx）、**响应体解析失败** | ✅ | 短暂故障，退避后可能成功 |
| （`EmbeddingError` 基类） | — | — | 保持向后兼容 |

**分流代码**：

```python
    async with async_session_local() as session:
        try:
            vectors = await embedding_client.embed_texts(user_id, [text], session)
        except (embedding_client.EmbeddingKeyRejected,
                embedding_client.EmbeddingDimMismatch) as exc:
            # 不可重试 → 立即置 FAILED。FAILED 在 reap_once 的捞取范围内（§6.1），
            # key 修好/配置改好后仍能被重新捞起，不会永久失联。
            logger.warning("embedding 不可重试，置 FAILED %s:%s:%s —— %s",
                           source_type, item_id, user_id, exc)
            async with async_session_local() as s2:
                await set_failed(user_id, source_type, item_id, s2)
                await s2.commit()
            return
        except embedding_client.EmbeddingCallFailed as exc:
            # 可重试 → 抛 Retry 让 arq 退避 5/10/15 秒。
            # ⚠️ arq 重试用尽**不会**改业务表状态，停在 RUNNING 等 reaper 超时自愈。
            logger.warning("embedding 可重试失败，交 arq %s:%s:%s —— %s",
                           source_type, item_id, user_id, exc)
            raise Retry(defer=ctx.get("job_try", 1) * 5) from exc
```

#### 为什么不能一律抛 Retry（**原方案错在哪**）

```python
# ❌ 原方案：任何失败都重试
except EmbeddingError:
    raise Retry(defer=...)
```

三个具体后果：

1. **白烧额度**：key 已死 / 维度配置错时，重试 3 次（`max_tries=3`）得到的都是同一个错
2. **状态滞后**：arq 重试用尽**不会**改业务表，状态停在 `RUNNING`，要等 reaper 判超时（`index_stale_seconds`，10 分钟）才自愈。而直接置 FAILED 是**立即可观测**的——查库就知道这件商品索引失败，不会「明明失败却查不出原因」
3. **排序挤占**：`max_tries` 是**每个任务**的额度，不可重试的任务把它烧完就走，不影响别的任务；但同一批次的其他任务如果也在重试队列里排队，整体延迟被拉长

#### 🔴 响应体解析失败必须归一化（**第四种情况，原方案漏了**）

`embedding_client.py` 原本这样解析响应：

```python
data = resp.json()                          # ← 厂商返回 HTML 错误页时抛 JSONDecodeError
batch_vector = [row["embedding"] for row in data["data"]]   # ← 结构不对时抛 KeyError/TypeError
```

**这两行抛的不是 `EmbeddingError`**，会被调用方的 `except EmbeddingError` 漏掉，
变成「未知错误」：**arq 既不重试也不改业务表状态**，只能等 reaper 超时。

**改法**：

```python
try:
    data = resp.json()
    batch_vector = [row["embedding"] for row in data["data"]]
except (ValueError, KeyError, TypeError, IndexError) as exc:
    # 归一化成 EmbeddingCallFailed（可重试）——网关返回 HTML 错误页是可重试的
    raise EmbeddingCallFailed("向量模型返回了无法解析的内容") from exc
```

同理，维度校验要挡非 list：

```python
if not isinstance(vec, list) or len(vec) != _EMBEDDING_DIM:
    raise EmbeddingDimMismatch("向量模型返回的向量维度与配置不一致")
```

#### 为什么用异常类型而不是匹配文案

**踩过的坑**：`EmbeddingKeyRejected` 之前是靠 `"key 已被厂商拒绝" in str(exc)` 匹配的。
文案一改，判断静默变False → 不可重试的错误被当成可重试 → **白烧三次重试，不报错**。

异常类型是**编译期保证**的，改文案不影响分类。

**向后兼容**：三个子类都继承 `EmbeddingError`，所以现有 `except EmbeddingError`
的调用方行为不变（B 批 `embedding_client.py` 目前零引用，但这个兼容性要保住）。

#### 两条兜底路径不冲突

| 路径 | 时机 | 覆盖什么 |
|---|---|---|
| arq 自身重试 | 秒级 | 可重试错误的快速恢复 |
| reaper 扫 `RUNNING` 超时 | 分钟级 | 一切漏网（含 worker 崩溃、arq 用尽、Redis 投递失败） |

**reaper 是最终正确性保证**。

---

## 5. 商品 CRUD 的接线：10 个入口，一个都不能漏

### 5.1 完整入口清单（实测扫描结果）

| # | 函数 | 文件:行 | 动作 |
|---|---|---|---|
| 1 | `add_cart_item` | `cart_repo.py:20` | INSERT + PENDING |
| 2 | `update_cart_item` | `cart_repo.py:42` | UPDATE + PENDING |
| 3 | `delete_cart_item` | `cart_repo.py:28` | **DELETE + 删向量副本** |
| 4 | `transfer_to_owned_item` | `cart_repo.py:61` | 🔴 **一次操作影响两张表**（§5.3） |
| 5 | `add_owned_item` | `owned_repo.py:20` | INSERT + PENDING |
| 6 | `update_owned_item` | `owned_repo.py:45` | UPDATE + PENDING |
| 7 | `delete_owned_item` | `owned_repo.py:30` | DELETE + 删向量副本 |
| 8 | `create_record` | `purchase_record.py:148` | INSERT + PENDING |
| 9 | `update_record` | `purchase_record.py:175` | UPDATE + PENDING |
| 10 | `delete_record` | `purchase_record.py:188` | DELETE + 删向量副本 |

### 5.1.1 🔴 消费记录没有 repo 层，写库代码直接写在 router 里

实测：`app/repository/` 下**没有 purchase_record 的 repo**。`create_record`（`purchase_record.py:148`）直接：

```python
async with async_session_local() as db:
    async with db.begin():
        row = PurchaseRecord(user_id=user.id, **fields)
        db.add(row)
        await db.flush()
        await db.refresh(row)
return success(_row_dict(row))
```

**两点影响**：

1. **接线点在这三个 router 函数里**，不是在 repo。`db.begin()` 这个事务块就是「业务数据 + index_status='PENDING'」同事务的位置——把 `index_status='PENDING'` 加进 `PurchaseRecord(...)` 的构造即可。
2. **提交后投递要写在 `async with db.begin()` 块之外**（`success()` 之前），与 §3 同理。

**顺带一提**：这三处不经过 repo，是分层上的一个既存不一致（其他两张表都有 repo）。**本设计不去动它**——改造成本超出「接索引」的范围，记在 §12 遗留里。

### 5.2 建议的收口方式：不在 repo 里写队列代码

**repo 层不该知道 Redis 的存在**——那会让「单库操作」这个分层假设破掉，且测试 repo 时还得配 Redis。

**建议**：repo 只管把 `index_status` 设对，**投递由 service / router 层做**：

```
router 收到请求
  → 调 repo（同一事务里带 index_status）
  → commit 之后调 index_service.enqueue_sync(...)
```

或者更省事：**在 repo 函数里 commit 之后直接调**，但要把enqueue 的异常全吞（投递失败不能影响已提交的数据）。**两种都行，大宋选。**

### 5.3 🔴 转移（transfer）是特例：**三张表**都要处理

> 2026-10-17 修正：本节原写「两张表」，是**漏看了 `cart_repo.py:77-81`**
> —— `transfer_to_owned_item` 还会同时创建一条 `PurchaseRecord`。

`transfer_to_owned_item`（`cart_repo.py:61-90`）把购物车商品变成物品库商品。
**它同时动三处**：

```python
owned_item = OwnedItem(...)      # :72  新建 owned 行
record = PurchaseRecord(...)# :77  🔴 同时新建一条消费记录
session.add_all([owned_item, record])
await session.flush()        # :83
await session.delete(item_in_cart)    # :84  删旧 cart 行
```

所以接线要三件事：

| 动作 | 为什么 |
|---|---|
| 删 cart 侧向量副本 | 旧 cart 行没了，PG 里留着的向量成了孤儿 |
| owned 新行投递 | 新物品要能被检索到 |
| 🔴 **purchase 新行投递** | `PurchaseRecord` 是第三个可检索来源（`SOURCE_TYPES` 里有 `purchase`），不投递的话这张表在 RAG 里**永远是空的** |

**漏任一边**：要么 PG 里留孤儿向量（检索命中后回 MySQL 查不到 → 结果里出现空条目），
要么新物品永远不索引，要么消费记录这条检索线完全空转。

**实现前提**：`transfer_to_owned_item` 目前只 `return owned_item`（:90），
**拿不到 `record.id`**。需要它改成返回 `(owned_item, record)`。
**保持 repo 不碰 Redis**——投递仍在 router 层做。

### 5.4 删除：删向量副本，不只是删行

删商品时**必须**调 `vector_repo.delete_by_source`。**漏了会留孤儿向量**——`search_similar` 照样能命中它，只是回 MySQL 取原文时什么都取不到。

**这是「回 MySQL 取原文」这条铁律的反面**：PG 里有什么不代表 MySQL 里有什么。

### 5.5 顺带：`repoint_refs_on_transfer`

`group_repo.py:214` 的分组引用重指向，在转移时也会跑。**它不改商品内容，所以不需要重新索引**——除非你决定「分组也进切片文本」（记忆里切片 = `name + specs + note`，**不含分组**）。**保持现状即可，别顺手加。**

---

## 6. reaper 进程（独立，每 5 分钟）

### 6.1 捞取范围

```sql
WHERE index_status IN ('PENDING', 'RUNNING', 'FAILED')
  AND (index_status <> 'RUNNING' OR update_time < NOW() - INTERVAL 10 MINUTE)
```

| 状态 | 为什么捞 |
|---|---|
| `PENDING` | Redis 投递失败 / worker 没接到 / reaper 上一次投递又失败 |
| `RUNNING` 超 10 分钟 | worker 崩溃或被杀，**状态机自愈**（00:36 大宋拍板必须保留这条） |
| `FAILED` | embedding 持续失败（key 欠费等），key 修好后要能重新索引 |

### 6.2 投递失败就跳过，别死循环

reaper 扫到一批 → 逐个投递。**某个投递失败就记日志跳过**，下一轮（5 分钟后）再捞。**绝不能因为一个失败就中断整批**。

### 6.3 为什么必须是独立进程（大宋拍板）

挂在 lifespan 后台循环有两个问题：
1. 多 worker 时**每个 worker 都跑一遍**，重复扫描 + 重复投递（要额外加分布式锁）
2. worker 挂了但 Web 还活着时，**没人跑补偿**

独立进程 `python -m app.worker_reaper`：只跑一个实例、崩了不影响 Web、可用 systemd / 计划任务托管。

### 6.4 reaper 里的 session 纪律

**每次循环开一个新 session，用完即关**：

```python
async with async_session_local() as session:
    rows = await session.scalars(select(...))     # 查
# ← session 关闭
for row in rows:
    await enqueue(...)                            # 投递，不持连接
```

**别在循环里长期持有一个 session**——那是 10 分钟的连接占用，正是今天上午在流式那边刚踩过的 `pool_size` 坑。

---

## 7. 投递端（`app/services/index_service.py`）

### 7.1 两个函数

```python
async def enqueue_sync(user_id: int, source_type: str, item_id: int) -> bool:
    """投任务。**永不抛异常**——投递失败只返回 False，由 reaper 兜。"""

async def sync_one(ctx: dict, user_id: int, source_type: str, item_id: int) -> None:
    """arq 任务函数。见 §4.4。"""
```

### 7.2 🔴 Redis 连接池的生命周期

`enqueue_sync` 被HTTP 请求调用，**每次都 `create_pool` 会漏连接**。三种做法：

| 做法 | 评价 |
|---|---|
| 全局单例 + lifespan 里建 | 🟡 与 arq worker 的生命周期割裂 |
| 模块级 lazy 单例 + `asyncio.Lock` 防并发建 | ✅ **推荐**：首次调用建，之后复用 |
| 每次 `create_pool` + `finally: await pool.close()` | 🟡 最简单但有开销，且高频调用时容易漏 |

**推荐 lazy 单例**：`enqueue_sync` 内部用一个模块级变量 + Lock，首次创建后复用。

### 7.3 `_job_id` 去重

arq 的 `enqueue_job(..., _job_id=...)`：同 ID 已在队列时**返回 None**。

**用它做天然去重**：`_job_id = f"idx:{source_type}:{item_id}"`。

**好处**：同一商品被连改 5 次，只会排队一次任务；worker 处理时读的是**当时最新的 MySQL 数据**（不是入队时的快照），所以中间几次修改不需要单独索引。

**⚠️ 但要注意**：如果任务已被 worker 取走正在跑，此时又投递同 ID，**能重复入队**。真正的去重要靠 MySQL 的 `RUNNING` 状态判断（§4.4 第 1 步）。

---

## 8. RAG 读取侧：检索位置与状态提示

> 🔴 **2026-10-17 大宋撤回「固定前置」拍板，改为工具化。**
> 本节 §8.1 / §8.2 的原结论已作废，下面是现行设计。

### 8.0 拍板变更记录（保留决策留痕）

| 时间 | 结论 | 为什么变 |
|---|---|---|
| 2026-10-17 17:10 | ~~固定前置，不做模型自主判断~~ | 我给的成本对比（工具化多 1.5s） |
| **2026-10-17 18:00** | **工具化（LangGraph）** | **大宋指出他一直要的是「让模型自己判断」，撤回上条** |

**教训**：拍板当场就该写文档（已记）；**反过来也成立——写进文档的拍板，下一轮开工前必须跟大宋对一次**。
拿文档当既定事实往下推是错的。

### 8.1 检索位置：**工具化**（大宋 18:05 撤回后拍板）

模型自己决定要不要调检索工具，走 **LangGraph 编排**（`app/agents/rag_graph.py`）。

```
START → decide ─┬─ 要检索 & round_no<2 → search ─┐
                ├─ 不检索→ answer → END
                └─ round_no>=2（兜底）   → answer → END
```

**与固定前置的对比账**（原17:10 我给的论据，现在只作对照）：

|场景 | 固定前置 | 工具化 | 差 |
|---|---|---|---|
| 需要检索（认真问商品，**多数**） | 3.4s | 4.9s | 🔴 慢 1.5s |
| 不需要（你好/谢谢，**少数**） | 3.4s | 1.5s | 🟢 快 1.9s |

**为什么最后还是选工具化**：大宋判断「你好/谢谢」这类不值得优化，而**用户看得到系统
在翻他的物品库**是更重要的（见 §8.4）。固定前置在体验上「凭空给答案」。

**检索耗时实测（2026-10-17，千问 qwen3.7-text-embedding-flash）**：

| 步骤 | 耗时 | 占比 |
|---|---|---|
| ① 调 embedding 拿查询向量 | **335–470 ms** | **91%** |
| ② PG 向量检索 | 31–35 ms | 8% |
| ③ 回 MySQL 取原文 | ~5 ms | 1% |

🔴 **重要修正（实测否掉了我原来的推断）**：我曾以为「批量 6 条 363ms」是批量效应，
实测**单条稳定 ~300ms，与条数几乎无关**（20 条也只有 695ms）——厂商侧约 250ms 固定开销。
**所以「优化 embedding 调用」这条建议对读侧不成立**：读侧只有 1 条 query，没有第二条可批。

⚠️ **PG 那 31ms 也是固定的**（1 条数据和上万条一样快）——**PG 性能现在根本不是瓶颈**，
语料上万条才是。

### 8.2 🔴 LangGraph 1.2.4 的三条硬约束（**全部实测，不是文档**）

| # | 约束 | 不这么写会怎样 |
|---|---|---|
| 1 | 默认 `recursion_limit`是 **10007**，不是网上说的 25 | 死循环 ≈ 4 小时 + 无限烧钱 |
| 2 | **只能在 `ainvoke/astream` 的 `config` 里传**，`compile(recursion_limit=)` 不存在 | `TypeError: unexpected keyword argument` |
| 3 | 递归计数是 **super-step** 不是「轮」：每轮 = decide+search+answer = 3 步 | 2 轮要设 6，设 4 会在半路截断 |

**双保险**（业务控制 vs 死循环兜底）：

| | 作用 | 撞满后 |
|---|---|---|
| 状态里的 `round_no` | **业务控制**：最多检索 2 次 | 主动走 answer，**正常回答** |
| `recursion_limit=6` | **兜底**：防死循环 | 抛 `GraphRecursionError`，流断 |

⚠️ 撞 `recursion_limit` 是**抛异常**，SSE 流会断在半路、用户看到「生成失败」。
所以业务上必须靠 `round_no` 提前收尾，让上限永远撞不到。

### 8.3 `index_status`：**不进 prompt**，只在对话页给一条提示

**大宋 18:00 拍板**：状态提示**不在商品列表**，**在对话页单独一条**（「向量库正在更新中」）。

| 出口 | 消费者 | 要什么 |
|---|---|---|
| 商品列表页 | 用户 | （**不做**，推翻原设计） |
| **对话页顶部 banner** | 用户 | **一个布尔值**：有没有非 SYNCED 的行 |
| **prompt** | 模型 | **什么都不给** |

**🔴 为什么 `index_status` 不能进 prompt**（这一条与大宋的直觉相反，他一开始认为该进）：

1. **模型会当事实复述** —— prompt 里写「苹果 iPhone（索引处理中）」，用户问「我的手机多少钱」，
   模型很可能答「你的 iPhone 还在建立索引」。把内部技术状态漏给用户了，
   违反 `chat_service.SYSTEM_PROMPT` 里「不得声称已经查询、验证」那条铁律。
2. **对模型是纯噪音** —— 它对「这台手机适不适合送人」的判断毫无帮助，只占 token。
3. **⚠️ 原设计混淆了两种情况**：
   - **情况 A**：PG 里有向量，但 MySQL 里 `index_status=PENDING`（刚改完还没同步）→ 模型**会**看到它
   - **情况 B**：PG 里没向量（PENDING 期间从没建过索引）→ 检索**根本命中不到**，模型压根看不到

   原 §8 那句「写『索引处理中』而不是静默省略」只对情况 A 成立，而处理方式是**前端角标**，不是塞进 prompt。

**所以 `rag_service` 不返回 `index_status` 给 prompt 用**——但 `fetch_items_for_rag`
仍然带出这个字段，供两处用：写排查日志、写进落库的 tool 消息 JSON（前端展示）。

**🔴 铁律复述（不变）**：**索引未完成 ≠ 商品不存在**。
商品参数在 MySQL 里是完整的（`chat_service._format_item` 能直接读），向量化只是为了召回**其他**物品。
**PENDING 绝不能拦截请求，也不该报错。**

### 8.4 🔴 tool 消息：**落库**（方案 B，content 存 JSON）

模型调工具时，返回值是 `role="tool"` 的消息——这是**协议要求**，没有它模型下一轮无法继续。

**大宋拍板落库**，理由：**用户刷新页面后应当看得到「系统翻了我的物品库」**。
不落的话用户看到的是一个**凭空出现的答案**，会怀疑「它凭什么推荐这个」——
在导购场景下这是**信任问题**。

**存储形态**（表结构一个字节都不改）：

```
id=100  role=user       content=「送人送什么好」
id=101  role=assistant  content={"tool_calls":[{"id":"call_a1",...}]}  ← 存JSON（不是 NULL）
id=102  role=tool       content={"query":"...","count":2,"items":[...]}← 存 JSON
id=103  role=assistant  content=「推荐索尼耳机…」

role: String(16)装得下 "tool"  ✅
status: 复用 "completed"✅
content: Text NOT NULL → 存 JSON 字符串刚好  ✅
```

**下一轮重建上下文时要还原成协议格式**（库里是 JSON 字符串，发给模型前必须转回去）：

```
{"role":"assistant", "content": null, "tool_calls":[...]}
{"role":"tool", "tool_call_id":"call_a1", "content":"结果文本"}
```

⚠️ **不能直接把 JSON 字符串当 content 塞进去** —— 协议层等于没有工具调用记录。

**🔴 成对落库是硬要求**：协议规定 assistant 发了 `tool_calls`，下一条必须是配对的
`role="tool"`（带 `tool_call_id`），孤立会被厂商拒绝。

**中断场景必然产生孤立**（`user → assistant(只发了 tool_calls) → [用户按停止]`）。
**大宋拍板：中断也落 tool 占位**（content 写 `{"interrupted": true}`），保证永远成对。

理由：「检索被中断有可能就是用户主动中断的」——用户自己知道是怎么回事，
这不是内部状态泄露（推翻了我原先「内部状态不外露」的反对理由）。

**为什么用 `status="completed"` 而不是 `failed`**：`status` 的既有语义是「生成结局」，
检索**成功**了却标成失败是数据污染，会让以后查「failed 有多少」时捞出 tool 消息。
代价是 `messages_for_context` 要**显式加 `role != "tool"` 条件**。

### 8.5 降级：检索失败**永不抛异常**

与写入侧 `index_service.drop_vector` 同口径——**Redis/PG 侧的失败不阻塞业务**。
RAG 是增强功能，对话是主功能，让「向量库没配好」变成「用户发消息报 500」是本末倒置。

| 失败点 | 抛出 | 用户看到 |
|---|---|---|
| 没配向量模型 key | `BizError` | banner「未配置向量模型」 |
| PG 引擎没起 | `BizError` | banner「向量库未配置」 |
| PG 连不上 / SQL 错 | asyncpg 异常 | 检索不到，但能正常聊 |

**🔴 全异常自吞的代价**：它会把**代码 bug 一起吞掉**。
2026-10-17 实测踩到：`rag_service` 调错了函数名（`fetch_items_for_refs`），
一调必 `AttributeError`，但被 `except Exception` 吞掉 → **永远返回空列表，
表现是「配好 key 也搜不出东西」且不报错**。

**排查这类问题的第一件事：去看那条 `RAG 检索异常` 日志的完整堆栈**（`exc_info=True`）。
---

## 9. 施工顺序

> **2026-10-17 20:40 更新**：
> 第 1–8 步全部完成（端到端实测通过）；**读取侧已改走工具化**（§8.1），
> 原「固定前置」路线作废。步骤 9 拆成了 9a–9e。
>
> 已完成：`model_call` 支持 tools（含流式分片累积）、`rag_service`（检索 + 三处降级）、
> `purchase_repo.fetch_by_ids`、`chat_repo.fetch_items_for_rag`。
> 端到端实测：相关 query 召回 1 条、无关 query 被阈值挡成 0 条。
>
> 遗留已清：两处未使用 import、队列隔离（见步骤 10）。

| # | 内容 | 状态 | 产出 /备注 |
|---|---|---|---|
| 1 | 三张表加 `index_status` / `index_time` + 迁移 | ✅ | `49a0c3b7f694`；67 行存量全回填 PENDING |
| 2 | `config.py` 加 `redis_url` / `index_stale_seconds` + `app/core/redis_client.py` | ✅ | 🔴 `redis_url` 不给默认值（§14） |
| 2.5 | `embedding_client.py` 四个异常类（可重试性分流） | ✅ | 见 §4.6 |
| 3 | `app/services/index_service.py`：状态读写 + `enqueue_sync` + `reap_once` | ✅ | 含 `drop_vector`（自吞异常） |
| 4 | `app/worker.py`：WorkerSettings + `on_startup` 起 PG | ✅ | 🔴 `functions`（单数会静默失效）/ `max_tries`（不是 RQ 的 `max_retries`） |
| 5 | `sync_one` 五步 + 按异常类型分流 | ✅ | 🔴 PG 成功才 SYNCED |
| 6 | **10 个** CRUD 入口接线（含 transfer **三表**、删除清副本） | ✅ | 最容易漏的一步，已全接 |
| 7 | `app/worker_reaper.py`：每 5 分钟扫 | ✅ | 实测精确捞到 67 条 |
| 8 | `main.py` lifespan 补 `close_pool()` | ✅ | — |
| 9a | `vector_repo` 相似度阈值（`rag_min_score`） | ✅ | 🔴 **实测发现原来没有阈值**，0.19 分的垃圾也召回 |
| 9b | `model_call` 支持 tools + 流式 tool_call 分片累积 | ✅ | 产出改 `StreamEvent`；🔴 `[DONE]` 处必须 `break` 不能 `return` |
| 9c | `rag_service.retrieve_relevant` + 三处降级 | ✅ | 端到端实测通过 |
| 9d | `purchase_repo.fetch_by_ids` + `chat_repo.fetch_items_for_rag` | ✅ | 🔴 查不到必须**静默跳过**，与 refs 相反 |
| 9e | 🔴 `app/agents/rag_graph.py`（LangGraph 状态图） | ⬜ **下一步** | `recursion_limit=6`（§8.2 三条约束） |
| 9f | `chat_stream` 接编排 + `agent` 事件透传 | ⬜ | 现在 tool_call 事件被 warn 后丢弃 |
| 9g | tool 消息落库（方案 B）+ `messages_for_context` 加 role 过滤 | ⬜ | §8.4 |
| 9h | `GET /conversations/rag-index-status` | ⬜ | ⚠️ 必须声明在动态路径 `/{conversation_id}/` **之前** |
| 9i | 前端：tool 消息渲染 + 对话页 banner | ⬜ | 归大宋 |
| 10 | 测试队列隔离 + `scripts/clear_arq_queue.py` | ✅ | `arq:queue:pytest`，实测生产队列恒为 0 |

**第 2、4、5、6 步各有一个「不报错但静默坏」的坑**，见 §11 自查清单。

---

## 10. 测试清单

| # | 场景 | 断言 |
|---|---|---|
| 1 | 业务数据与 PENDING 同事务 | 崩溃在中间不留「数据变了但状态没变」的行 |
| 2 | Redis 投递失败 | 业务数据**仍在**（不回滚），状态留 PENDING |
| 3 | PG 写失败 | 状态**不是** SYNCED；arq 重试用尽后 reaper 能捞到 |
| 4 | 🔴 **顺序约束** | **注入 PG 写失败 → 断言状态绝非 SYNCED**（这条锁死 §4.4 地基） |
| 5 | worker 崩溃 | RUNNING 超 10 分钟被 reaper 捞起并转 SYNCED |
| 6 | 🔴 **transfer 三表** | cart 副本被删 + owned 新行被索引 + **purchase 新行也被索引** |
| 7 | 删除清副本 | 删商品后 `search_similar` 命中不到它 |
| 8 | RAG 状态提示 | PENDING 商品在 prompt 里带「索引处理中」，**且请求不失败** |
| 9 | 🔴 **不可重试不烧额度** | 抛 `EmbeddingKeyRejected` → **arq 重试次数为 0** 且状态直接 FAILED |
| 10 | 🔴 **可重试才退避** | 抛 `EmbeddingCallFailed` → `Retry(defer=5/10/15)` |
| 11 | 🔴 **响应体异常被归一化** | 厂商返回 HTML 错误页 → 抛 `EmbeddingCallFailed`，**不是裸 `JSONDecodeError`** |
| 12 | 异常子类兼容 | `except EmbeddingError` 仍能捕到三个子类（B 批调用方不受影响） |

第 9、11 条对应 §4.6 的两个修正——**没有这两条测试，分类逻辑退化不会有人发现**。

第 4、6 条最重要：**第 4 条锁死你定的地基约束，第 6 条是唯一会「两处只做一处」的转移逻辑。**

---

## 11. 开工前自查清单

**全是「漏了不报错、静默坏掉」的地方：**

- [ ] 🔴 `index_status='PENDING'` 和业务数据在**同一个事务**（`async with session.begin()` 内）
- [ ] 🔴 **消费记录那 3 个入口**（无 repo 层、写在 router 里）也已接线（§5.1.1）
- [ ] 🔴 Redis 投递在 **commit 之后**，且**投递失败不回滚**
- [ ] 🔴 `sync_one` 里 **PG 写入成功后才置 SYNCED**（顺序不能反）
- [ ] 🔴 `app/worker.py` 的 `on_startup` 调了 `start_pg_engine()`（独立进程不跑 lifespan）
- [ ] 🔴 `transfer_to_owned_item` **三处都处理**（删 cart 副本 + 建 owned 索引 + **建 purchase 索引**，§5.3）
- [ ] 🔴 三个 `delete_*` 都调了 `vector_repo.delete_by_source`（否则留孤儿向量）
- [ ] 🔴 **按异常类型分流**，不是一律 `raise Retry`（`KeyRejected`/`DimMismatch` 直接 FAILED，§4.6）
- [ ] 🔴 `embedding_client` 的**响应体解析已包 try**（厂商返 HTML 错误页时抛的是裸 `JSONDecodeError`，会被漏掉）
- [ ] 🔴 **没有靠文案匹配**判断可重试性（改文案会让分类静默失效）
- [ ] 🔴 `redis_url` **不给默认值**，强制从 `.env` 来（§14）
- [ ] `.env.example` 补了 `PG_URL` 与 `REDIS_URL`（该模板进 Git，协作者靠它配环境）
- [ ] `arq_redis_settings` 在 `app/core/redis_client.py`，**不在 `config.py`**（那里是纯声明）
- [ ] `main.py` 的 lifespan `finally` 调了 `close_pool()`
- [ ] arq `job_timeout` **大于** embedding 的 20 秒 HTTP timeout
- [ ] reaper 捞取范围**包含 FAILED**（否则一次失败永久失联）
- [ ] reaper 里**每轮开新 session**，不长期持有
- [ ] `enqueue_sync` 的 Redis 连接池是**单例复用**（在 `redis_client` 里），不是每次 `create_pool`
- [ ] reaper 投递失败**跳过当前项**，不中断整批
- [ ] 迁移里三张表都有 `server_default='PENDING'`（✅ `49a0c3b7f694` 已验证）
- [ ] `docs/启动命令.md` 补了 worker 与 reaper 两条命令

---

## 12. 待定 / 遗留

| # | 事项 | 说明 |
|---|---|---|
| 1 | 🟡 状态值大小写是否统一 | 本设计按拍板用大写；`chat_message.status` 是小写。改任一边要同步另一边 |
| 2 | ✅ **消费记录已补 repo（只读）** | 2026-10-17 新建 `app/repository/purchase_repo.py`，只有 `fetch_by_ids`。**写侧仍在 router 里**（`_fields` / `_row_dict` / `_validate_specs` / `_owned_for_update` 五个私有函数）——本设计不改造。当前是**半分层**状态，有意为之的中间态 |
| 3 | 🟡 切片是否含分组 | 现状 = `name + specs + note`（不含分组）。**保持现状**，别顺手加 |
| 4 | 📌 Redis 在服务器上的部署 | 与服务器部署一并做（与流式设计 §2.5 的连接池待办一起） |
| 5 | ✅ **`arq` / `redis` 已装** | 2026-10-17 实测 `pip show`：`arq 0.28.0`、`redis 5.3.1`；Redis 服务在跑（`redis_version=5.0.14.1`）。⚠️ **`requirements.txt` 还没同步**（只写了 `redis>=5.0`，**`arq` 完全没提**）—— 别人 clone 下来跑不了 worker |
| 6 | ⚠️ **`arq` 已进入 maintenance-only** | PyPI 官方元数据：`arq 0.28.0`，作者声明仅维护、不计划新功能。**功能上够用**（异步任务/Retry/_job_id 去重/cron 都有）；风险是将来要优先级、结果面板得迁——**迁移成本低**（任务函数是普通 `async def`，只改 WorkerSettings 与投递那几行）。**不推翻 20:56 的拍板**，仅记录以备将来 |
| 7 | ✅ **PG 已启动** | 2026-10-17 实测连通，`item_embedding` 可读写。infra 方案（WSL2 原生 / Docker）**仍是待决**——服务器部署时要一并定 |
| 8 | ✅ `transfer_to_owned_item` 已返回元组 | 已改成 `return (owned_item, record)`，router 用 `record.id` 投递 purchase（§5.3） |
| 9 | ✅ **测试已与生产队列隔离** | 2026-10-17 解决：新增 `tests/conftest.py` 在 import app 前设 `ARQ_QUEUE_NAME=arq:queue:pytest`，`redis_client.get_pool()` 传 `default_queue_name` 给 `create_pool`。实测跑完 175 个测试，生产队列恒为 0。另加 `scripts/clear_arq_queue.py`（`--all` / `--dry-run`） |
| 10 | ✅ 未使用 import 已全项目清理 | 2026-10-17 用 ast 扫了 97 个文件，清掉 9 处（`index_service` 两处 + `chat_message.JSON` + `image.Boolean/Text` + `owned_repo.delete` + `user_sche.Optional` + 测试里 4 处待大宋确认） |
| 11 | 🔴 **`call_model` 返回值破坏性变更** | 2026-10-17 从 2 元组变 3 元组（加 `tool_calls`），`stream_model` 产出从 `str` 变 `StreamEvent`。顺手修出 `spec_complete_service` 的 10-16 遗留 bug——`POST /cart/items/ai-draft` 一直是坏的 |
| 12 | ⬜ **PG infra 方案待决** | WSL2 原生 / Docker / 服务器部署三选一。与 `docs/启动命令.md` §6 的 worker 部署一并定 |

---

## 13. 阻塞项

> 2026-10-17 17:10 更新：**前三个阻塞项全部解除**，链路已端到端跑通。
> 当前**无阻塞项**。

| # | 事项 | 阻塞什么 | 状态 |
|---|---|---|---|
| 1 | ~~PG 没启动~~ | — | ✅ 已解决 |
| 2 | ~~`arq` 没装~~ | — | ✅ 已解决 |
| 3 | ~~`redis_url` 字段没加~~ | — | ✅ 已解决 |

**剩下的不阻塞**：读取侧（第 9 步）是当前唯一在建的东西。

---

## 14. `redis_url` 为什么不给默认值

**`Settings` 里有两种写法，本项目两种都在用，各有理由**：

| 写法 | 现有例子 | 含义 |
|---|---|---|
| `str`（无默认值） | `db_url`、`captcha_key`、`pw_max_length` | **必填**，`.env` 缺了就该在启动时炸 |
| `str \| None = None` | `pg_url`、`bocha_api_key` | **可选**，缺了功能降级 |
| `str = "默认值"` | `cookie_secure: bool = False` | 有安全默认，缺了也能跑 |

`redis_url` 该用**第一种**：

```python
redis_url : str        # 必填
```

**给了默认值的后果**：`.env` 里 key 拼错（比如写成 `REDIS_URL` 写成 `REDIS_URI`）不会报错，
Settings 会静默用上默认值 `127.0.0.1:6379`——**部署到服务器时，worker 连的是服务器本机的 Redis，
而你以为连的是配置的那个**。这类 bug 只在换环境时才暴露，最难查。

**这与 `pg_url` 不同**：`pg_url` 可以是 `None`，因为没有 PG 时 RAG 检索整个降级、
Web 服务照常跑；而 Redis 是**任务队列的唯一通道**，没有它 worker 完全跑不起来，
应当启动即炸。