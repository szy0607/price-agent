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

### 4.6 失败处理：抛 Retry，不吞

```python
if 失败:
    raise Retry(defer=...)      # 让 arq 退避重试
# arq 重试用尽（max_tries=3）后：
#任务标记为 failed，业务表状态仍是 RUNNING → reaper 捞（§6）
```

**⚠️ 注意**：arq 重试用尽**不会**自动把业务表置FAILED。所以有两条兜底路径：
- arq 自身重试（快，秒级）
- reaper 扫 `RUNNING` 超时（慢，分钟级）

**这两条不冲突**，reaper 是最终正确性保证。

**「置 FAILED 后也要能被捞」**：`FAILED` 必须在 reaper 的捞取范围里（§6.1）—— 否则一次失败就永久失联。

---

## 5. 商品CRUD 的接线：8 个入口，一个都不能漏

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

### 5.3 🔴 转移（transfer）是特例，两张表都要处理

`transfer_to_owned_item`（`cart_repo.py:61`）把购物车商品变成物品库商品。**它同时影响两处**：

- 旧 cart 行被删 → **删掉它的向量副本**
- 新 owned 行产生 → **新行 PENDING + 投递**

**漏任一边**：要么 PG 里留一条指向已删商品的孤儿向量（检索命中后回 MySQL 查不到 → 检索结果里出现空条目），要么新物品永远不索引。

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

## 8. RAG 读取侧如何用状态（**不改这部分，只定契约**）

`rag_service.retrieve_relevant` 检索到 id 后回 MySQL 取原文时，**顺带取 `index_status`**：

| 状态 | 模型看到的 | 依据（00:36 大宋定的 6 条 prompt 规则） |
|---|---|---|
| `SYNCED` | 正常列参数 | 可以基于检索资料回答 |
| `PENDING`/`RUNNING` | 「该商品正在建立向量索引」 | **明确告知处理中** |
| `FAILED` | 「该商品暂时无法检索」 | 不说「商品不存在」 |

**🔴 铁律复述**：**索引未完成 ≠ 商品不存在**。商品自身参数在 MySQL 里是完整的（`chat_service._format_item` 已经能直接读），向量化只是为了召回**其他**物品。**所以 PENDING 绝不能拦截请求，也不该报错。**

**具体到 prompt**：
```
【语义检索到的相关物品】
- 联想拯救者Y9000P｜品牌: 联想；型号: Y9000P（索引处理中）
```
——**写「索引处理中」而不是静默省略**。静默省略会让模型以为这件商品不存在。

---

## 9. 施工顺序

| # | 内容 | 产出 |
|---|---|---|
| 1 | 三张表加 `index_status` / `index_time` + 迁移 | autogenerate 后**逐行读**，查 server_default |
| 2 | `app/services/index_service.py`：状态读写 + `enqueue_sync` | lazy Redis 单例 |
| 3 | `app/worker.py`：WorkerSettings + `on_startup` 起 PG | 🔴 漏这行全程失败 |
| 4 | `sync_one` 三态落库 | 🔴 PG 成功才 SYNCED |
| 5 | 8 个 CRUD 入口接线（含 transfer 双表、删除清副本） | 最容易漏的一步 |
| 6 | `app/worker_reaper.py`：每 5 分钟扫 | 独立进程 |
| 7 | `rag_service.py` + `chat_service` 接线（读取侧） | §8 契约 |
| 8 | 启动文档补两条命令 | `arq app.worker.WorkerSettings` / `python -m app.worker_reaper` |

**第 1、3、4、5 步各有一个「不报错但静默坏」的坑**，见 §11 自查清单。

---

## 10. 测试清单

| # | 场景 | 断言 |
|---|---|---|
| 1 | 业务数据与 PENDING 同事务 | 崩溃在中间不留「数据变了但状态没变」的行 |
| 2 | Redis 投递失败 | 业务数据**仍在**（不回滚），状态留 PENDING |
| 3 | PG 写失败 | 状态**不是** SYNCED；arq 重试用尽后 reaper 能捞到 |
| 4 | 🔴 **顺序约束** | **注入 PG 写失败 → 断言状态绝非 SYNCED**（这条锁死 §4.4 地基） |
| 5 | worker 崩溃 | RUNNING 超 10 分钟被 reaper 捞起并转 SYNCED |
| 6 | 🔴 **transfer 双表** | cart 侧向量副本被删 + owned 侧新行被索引 |
| 7 | 删除清副本 | 删商品后 `search_similar` 命中不到它 |
| 8 | RAG 状态提示 | PENDING 商品在 prompt 里带「索引处理中」，**且请求不失败** |

第 4、6 条最重要：**第 4 条锁死你定的地基约束，第 6 条是唯一会「两处只做一处」的转移逻辑。**

---

## 11. 开工前自查清单

**全是「漏了不报错、静默坏掉」的地方：**

- [ ] 🔴 `index_status='PENDING'` 和业务数据在**同一个事务**（`async with session.begin()` 内）
- [ ] 🔴 **消费记录那 3 个入口**（无 repo 层、写在 router 里）也已接线（§5.1.1）
- [ ] 🔴 Redis 投递在 **commit 之后**，且**投递失败不回滚**
- [ ] 🔴 `sync_one` 里 **PG 写入成功后才置 SYNCED**（顺序不能反）
- [ ] 🔴 `app/worker.py` 的 `on_startup` 调了 `start_pg_engine()`（独立进程不跑 lifespan）
- [ ] 🔴 `transfer_to_owned_item` **两边都处理**（删 cart 副本 + 建 owned 索引）
- [ ] 🔴 三个 `delete_*` 都调了 `vector_repo.delete_by_source`（否则留孤儿向量）
- [ ] arq `job_timeout` **大于** embedding 的 20 秒 HTTP timeout
- [ ] reaper 捞取范围**包含 FAILED**（否则一次失败永久失联）
- [ ] reaper 里**每轮开新 session**，不长期持有
- [ ] `enqueue_sync` 的 Redis 连接池是**单例复用**，不是每次 `create_pool`
- [ ] reaper 投递失败**跳过当前项**，不中断整批
- [ ] 迁移里三张表都有 `server_default='PENDING'`
- [ ] `docs/启动命令.md` 补了 worker 与 reaper 两条命令

---

## 12. 待定 / 遗留

| # | 事项 | 说明 |
|---|---|---|
| 1 | 🟡 状态值大小写是否统一 | 本设计按拍板用大写；`chat_message.status` 是小写。改任一边要同步另一边 |
| 2 | 📌 消费记录的分层不一致 | `create/update/delete_record` **直接写在 router 里，没有 repo 层**（其他两张表都有）。本设计不改造，只按§5.1.1 接线。要不要补 repo 层另议 |
| 3 | 🟡 切片是否含分组 | 现状 = `name + specs + note`（不含分组）。**保持现状**，别顺手加 |
| 4 | 📌 Redis 在服务器上的部署 | 与服务器部署一并做（与流式设计 §2.5 的连接池待办一起） |
| 5 | 📌 arq / redis 包未装 | 实测 `pip show redis rq` → 均未安装；`requirements.txt:46` 只写了 `redis>=5.0`，**`arq` 完全没提**。Redis 服务本身在跑（6379 监听中） |