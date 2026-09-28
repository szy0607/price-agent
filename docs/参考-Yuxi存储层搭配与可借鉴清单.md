# 参考 · Yuxi 存储层搭配与可借鉴清单

> **这份文档是什么**：对参考项目 `F:\Yuxi`（LangGraph + FastAPI + Vue 的智能知识库/知识图谱平台）存储层的实地调研记录。
> **为什么写**：2026-09-27 大宋提「以后项目搭建可以全程借鉴 Yuxi」——先把它的**实际搭配**摸清，再划清「能借鉴 / 不能照搬」的界，避免把 PG 方言和已拍板选型一起搬过来。
> **怎么用**：每条结论都标了实测文件与行号，可直接跳去读原文。
>
> ⚠️ **一句话前提**：Yuxi 是 **PostgreSQL + asyncpg**，本项目是 **MySQL 8 + aiomysql**（已拍板）。
> **能借鉴的是「结构」和「边界感」，不能照搬的是「方言」和「选型」。**

---

## 1. 选型全貌（2026-09-27 实测）

五种后端存储，来自 `backend/package/pyproject.toml` + `docker-compose.yml`：

| 存储 | 镜像 / 版本 | 承担什么 | Python 驱动 | 备注 |
|---|---|---|---|---|
| **PostgreSQL** | `postgres:16` | 业务数据（**25 表**）+ 知识库元数据（**11 表**）+ **LangGraph checkpoint** | `asyncpg`（SQLAlchemy ORM）+ `psycopg[binary,pool]`（checkpointer 原生池） | `max_connections=600` |
| **Redis** | `redis:7.4.10-alpine` | 缓存 + **arq 任务队列** + 会话类数据 | `redis`（同步）/ `redis.asyncio`（异步）双客户端 | 启动参数 `--appendonly yes`（AOF 持久化） |
| **Milvus** | `milvusdb/milvus:v2.5.6`（standalone） | 向量检索（RAG） | `pymilvus` | **依赖 etcd + MinIO** |
| **Neo4j** | `neo4j>=5.28.1` | 知识图谱 | `neo4j`（**同步**驱动） | `bolt://neo4j:7687` |
| **MinIO** | `RELEASE.2023-03-20` | 对象存储：业务文件 **+ Milvus 的底层存储** | `minio` / `aioboto3` | 一个 MinIO 服务两用 |

**compose 里的容器**（`docker-compose.yml`）：`api`、`worker`、`storage-migrator`、`sandbox-provisioner`、`web`、`graph`(neo4j)、`etcd`、`minio`、`milvus`、`postgres`、`redis`、`mineru-api`、`paddlex`。

> 📌 **值得记的架构信号**：它是「**api 与 worker 分离**」的部署形态——读接口在 `api`，重活（文档解析、图谱构建、embedding）在 `worker`，两者共享同一套存储。这解释了后面很多设计为什么长那样。

---

## 2. PostgreSQL 连接配置（实测代码 + 逐条理由）

文件：`backend/package/yuxi/storage/postgres/manager.py`

### 2.1 引擎创建（`:358-374`）

```python
self.async_engine = create_async_engine(
    db_url,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    json_deserializer=json.loads,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=get_int_env("POSTGRES_POOL_SIZE", 10),
    max_overflow=get_int_env("POSTGRES_MAX_OVERFLOW", 20, minimum=0),
    pool_timeout=get_int_env("POSTGRES_POOL_TIMEOUT_SECONDS", 30),
)

self.AsyncSession = async_sessionmaker(
    bind=self.async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

| 参数 | 值 | 为什么 |
|---|---|---|
| `pool_pre_ping` | `True` | 取连接前先探活，避免"MySQL/PG 把空闲连接掐了但池子里还留着死连接" |
| `pool_recycle` | `1800`（30 分钟） | 主动回收，比等 `wait_timeout` 被动报错好。**本项目现在用 3600，也在合理区间** |
| `pool_size` / `max_overflow` | `10` / `20` | 走环境变量，**开箱 10 连接 + 突发 20** |
| `pool_timeout` | `30` | 取不到连接时的等待上限 |
| `json_serializer` | `ensure_ascii=False` | **PG 的 JSONB 场景**：中文不转义成 `\uXXXX`。本项目 MySQL 的 JSON 列同理值得加 |
| `expire_on_commit` | `False` | 与本项目一致（已实测这是标准做法） |

### 2.2 第二个连接池：专给 LangGraph checkpointer（`:376-391`）

**这条最值得本项目注意**，因为本项目也是 LangGraph 技术栈：

```python
# ⚠️ 注意：psycopg 不认识 "+asyncpg" 这样的 SQLAlchemy 方言标识。
langgraph_db_url = db_url.replace("+asyncpg", "").replace("+psycopg", "")

self.langgraph_pool = AsyncConnectionPool(
    conninfo=langgraph_db_url,
    max_size=get_int_env("LANGGRAPH_POSTGRES_POOL_SIZE", 10),
    timeout=get_int_env("LANGGRAPH_POSTGRES_POOL_TIMEOUT_SECONDS", 30),
    kwargs={"autocommit": True},  # LangGraph Checkpoint 强依赖 autocommit
    check=AsyncConnectionPool.check_connection,
)
```

三个要点：
1. **不能复用 SQLAlchemy 池**——LangGraph 的 `AsyncPostgresSaver` 要的是原生 `psycopg_pool.AsyncConnectionPool`
2. **URL 要清洗**：SQLAlchemy 方言后缀（`+asyncpg`）psycopg 不认识，两个驱动共用一个 URL 时必须在用之前剥掉
3. **`autocommit=True` 是硬要求**，注释里写明了

> 🔴 **本项目将来的对照点**：LangGraph 在 **MySQL** 上的 checkpointer 是 `langgraph-checkpoint-mysql`（`aiomysql`）。
> 到时候一样会遇到"要不要复用主池"的问题，**结论待实测**——不能直接假设和 PG 一样。

### 2.3 单例管理器（`:329`）

```python
class PostgresManager(metaclass=SingletonMeta):
```

全局一个 `pg_manager = PostgresManager()`（`:1538`）。`initialize()` 幂等（靠 `_initialized` 标志），**失败只记日志不抛异常**（`:395-397`），真正的失败留到 `_check_initialized()` 抛。

> ⚠️ 这个"初始化失败静默、使用时才炸"的选择，好处是**应用能启动**（能看到健康检查/日志），坏处是**错误延迟暴露**。本项目要不要照抄，值得掂量——我们已有 `M0-基座` 的启动自检设计。

---

## 3. 迁移机制：**它根本没用 Alembic**（最值得看的一节）

### 3.1 实证

```bash
$ find F:/Yuxi -iname "alembic*"          # → 空
$ grep -rn "alembic" backend/*/pyproject.toml   # → 空
```

**零 Alembic**。取而代之的是一套自研的「**域 + 整数版本**」机制。

### 3.2 三个常量（`manager.py:26-28`）

```python
BUSINESS_SCHEMA_VERSION = 7
KNOWLEDGE_SCHEMA_VERSION = 2
SCHEMA_VERSION_TABLE = "yuxi_schema_migrations"
```

### 3.3 版本表（`manager.py:462-467`）

```sql
CREATE TABLE IF NOT EXISTS yuxi_schema_migrations (
    domain  VARCHAR(32) PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version > 0),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

就一张表、一个 `domain` 主键、一个整数版本。**没有 revision 链、没有 down 脚本、没有 metadata 反射比对。**

### 3.4 四个角色，边界划得很清

| 角色 | 位置 | 干什么 |
|---|---|---|
| **迁移器**（一次性容器） | `backend/package/yuxi/storage_migration.py`（177 行）<br>入口 `python -m yuxi.storage_migration` | 拿锁 → 建版本表 → 读版本 → 建表/改表 → 记版本 → 跑数据迁移 |
| **跨进程串行锁** | `manager.py:435-453` `schema_migration_lock()` | `pg_advisory_lock(hashtextextended('yuxi:schema-migration', 0))`，防两个进程同时迁移 |
| **运行时只读校验** | `server/utils/lifespan.py:67` | `await pg_manager.require_current_schema()`，**版本不符直接拒绝启动** |
| **幂等 DDL** | `manager.py:545` `ensure_knowledge_schema()`<br>`manager.py:919` `ensure_business_schema()` | 一串 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `DROP COLUMN IF EXISTS` |

**设计哲学，原文注释（`lifespan.py:66`）**：

```python
# Schema 只由 Compose 中的 storage-migrator 修改；运行进程仅校验兼容版本。
pg_manager.initialize()
await pg_manager.require_current_schema()
```

### 3.5 校验逻辑（`manager.py:500-514`）

```python
async def require_current_schema(self) -> None:
    """只读校验运行进程需要的 Schema 域均为精确当前版本。"""
    versions = await self.get_schema_versions()
    required = {
        "business":  BUSINESS_SCHEMA_VERSION,
        "knowledge": KNOWLEDGE_SCHEMA_VERSION,
    }
    mismatches = [
        f"{domain}={versions.get(domain, 'missing')} (required {version})"
        for domain, version in required.items()
        if versions.get(domain) != version
    ]
    if mismatches:
        detail = ", ".join(mismatches)
        raise RuntimeError(f"Database schema migration is incomplete or incompatible: {detail}")
```

启动时把两个域的版本各对一次，**不等就崩**。这就是"代码上了但迁移忘跑了"的防线。

### 3.6 compose 里 migrator 是个一次性容器（`docker-compose.yml:165-199`）

```yaml
storage-migrator:
  working_dir: /app
  command: uv run --no-sync --no-dev python -m yuxi.storage_migration
  restart: "no"                       # ← 跑完就退，不重启
  depends_on:
    postgres:
      condition: service_healthy      # ← 等 PG 健康才动手
```

`api` 与 `worker` 都依赖它先跑完。

### 3.7 两种迁移分开，别混

| 类型 | 位置 | 幂等凭证 |
|---|---|---|
| **Schema 迁移**（建表/改列） | `manager.py` 的 `ensure_*_schema()` + 域版本表 | `yuxi_schema_migrations` 的 `domain` |
| **数据迁移**（搬历史数据） | `storage_migrations/v071_*.py`（如 `v071_options.py`） | 各脚本自己的 `_MIGRATION_VERSION = 1`，版本号存在**业务表**里（如 `ConfigOption.params`） |

`v071_options.py` 的写法（`storage_migrations/v071_options.py:17-30`）：

```python
_MIGRATION_VERSION = 1

async def migrate_system_options(db: AsyncSession, *, legacy_config_file: Path) -> None:
    ...
    params = dict(record.params or {})
    if int(params.get(SYSTEM_OPTIONS_MIGRATION_VERSION_PARAM) or 0) >= _MIGRATION_VERSION:
        return                      # ← 已做过就跳过，天然幂等
```

---

## 4. Redis / Neo4j：职责边界的写法（可以直接学）

### 4.1 Redis（`storage/redis/manager.py`，204 行）

开篇注释就把边界钉死了：

```python
"""Redis 客户端管理。

本模块只负责 Redis 连接参数、客户端创建和连接生命周期；
业务 key、TTL、序列化格式留在调用方模块中。
"""
```

配置用 **frozen dataclass** 承载，**不建连接**：

```python
@dataclass(frozen=True)
class RedisConfig:
    url: str = DEFAULT_REDIS_URL
    max_connections: int = DEFAULT_REDIS_MAX_CONNECTIONS
    decode_responses: bool = True
    socket_timeout: float | None = None
    socket_connect_timeout: float | None = None

    @classmethod
    def from_env(cls, *, decode_responses=None, socket_timeout=None, ...) -> RedisConfig:
        ...
```

还有日志脱敏（`:29-37`）——**本项目正好需要**：

```python
def redact_redis_url(url: str) -> str:
    """隐藏 url 中的密码部分用于日志输出。"""
    try:
        parsed = urlparse(url)
        if parsed.password:
            parsed = parsed._replace(netloc=parsed.netloc.replace(parsed.password, "***"))
        return urlunparse(parsed)
    except Exception:
        return url
```

异步客户端是**全局单例 + asyncio.Lock**（`:153-173`），不是每个请求新建。

### 4.2 Neo4j（`storage/neo4j/manager.py`，93 行）

同步驱动 + 全局单例 + 双检锁（`:81-87`）：

```python
def get_shared_neo4j_connection() -> Neo4jConnectionManager:
    global _shared_neo4j_connection
    if _shared_neo4j_connection is None or not _shared_neo4j_connection.driver:
        with _shared_neo4j_connection_lock:
            if _shared_neo4j_connection is None or not _shared_neo4j_connection.driver:
                _shared_neo4j_connection = Neo4jConnectionManager()
    return _shared_neo4j_connection
```

> ⚠️ **注意**：`neo4j_read` / `neo4j_write` 用的是 **`with driver.session()`（同步）**（`:24-34`）。
> 在 async 代码里直接调会**阻塞事件循环**。本项目若将来接图库，这块要么用 `asyncio.to_thread` 包，要么用异步驱动——**别照抄**。

---

## 5. 可借鉴清单（分三档）

### 🟢 直接可用 —— 跟选型无关，成本几乎为零

| # | 借鉴点 | 出处 | 对本项目的价值 |
|---|---|---|---|
| 1 | **日志脱敏 `redact_*_url()`** | `redis/manager.py:29` | 直接治我们已知的 🔴 欠账：`.env` 密码入库 / 日志里带密码 |
| 2 | **配置用 frozen dataclass + `from_env()`** | `redis/manager.py:40-71` | 比散落的 `os.getenv` 好；我们已有 `pydantic-settings`，思路一致 |
| 3 | **模块注释写明职责边界**（"只负责连接，业务 key/TTL 留在调用方"） | `redis/manager.py:1-5` | 我们 `repository/` 层正缺这份自觉 |
| 4 | **session 三段式**（commit / except rollback / finally close） | `postgres/manager.py:1488-1501` | 我们文档 `代码审查-异步连接与Session规范.md` 已讲，可对照 |
| 5 | **引擎参数取值**（`pool_pre_ping` / `pool_recycle=1800` / `pool_timeout=30`） | `postgres/manager.py:362-367` | 我们已有，数值可对齐 |
| 6 | **`json_serializer` 加 `ensure_ascii=False`** | `postgres/manager.py:360` | 将来有 JSON 列时，中文不转义 |
| 7 | **容器健康检查 + `depends_on: condition: service_healthy`** | `docker-compose.yml:417-421, 197-199` | 我们上 Docker 时直接用 |
| 8 | **结构化启动自检**（`startup_components`，`required=True` 失败即拒启动） | `server/utils/lifespan.py:_initialize_startup_component` | 可并入我们 `M0-基座` 的健康检查设计 |
| 9 | **`storage-migrator` 独立容器 + `restart: "no"`** | `docker-compose.yml:165-199` | 若将来上 compose，迁移不该躺在 api 启动里 |

### 🟡 有条件借鉴 —— 需要先验证/改造

| # | 借鉴点 | 障碍 | 建议 |
|---|---|---|---|
| 10 | **「运行时只读校验 schema 版本」** | 我们没版本表 | **但目标可以用 Alembic 达成**：lifespan 里比对"当前 revision == head"，不符就拒启动。**零成本、防「代码上了迁移忘跑」，建议做** |
| 11 | **LangGraph checkpointer 独立连接池** | 我们是 MySQL，驱动/方言全不同 | 等真要接 checkpointer 时**实测**再定，别照搬 `autocommit=True` 的结论 |
| 12 | **`arq` + worker 容器做后台任务** | 我们现在没有后台任务 | 等有"文档解析/图谱构建"这类重活时再评估 |
| 13 | **`metadata.create_all` 兜底建表** | 与 Alembic 职责重叠 | 不混用；二选一 |

### 🔴 不能照搬 —— 方言 / 已拍板决策

| 点 | Yuxi | 本项目（已拍板） | 为什么不能搬 |
|---|---|---|---|
| 数据库 | PostgreSQL 16 | **MySQL 8** | `JSONB` / `TIMESTAMPTZ` / `ADD COLUMN IF NOT EXISTS` / `pg_advisory_lock` / `hashtextextended` —— **MySQL 全都没有** |
| 异步驱动 | `asyncpg` | **`aiomysql`** | — |
| 密码哈希 | Argon2（`argon2-cffi`） | **bcrypt cost=12** | 已拍板；且我们有 72 字节截断口径要守 |
| 登录态 | JWT（`pyjwt`） | **Session Cookie**（落 MySQL，库内只存 sha256） | 已拍板，属安全红线 |
| 迁移工具 | 自研域版本表 | **Alembic** | 见下 §6 |
| session 获取 | repository 内部 `async with self._session()` | **`Depends(get_db_session)`** | 已拍板（判据：给框架调 → 写函数名） |
| 时间列默认 | `default=utc_now_naive` + `server_default=func.now()` | 我们：`default=utc_now_naive` + `server_default=text("(UTC_TIMESTAMP())")` | 结论已在 `注册登录-实现指引.md` §13.6 坑四对齐 |

---

## 6. 一个需要你拍板的问题：要不要学它的迁移机制？

**这不属于"影响不大"**——它撞已落地的决策（Alembic 已配置完成 + 第一个迁移 `f7fa5f121d6e_create_users` 已生成）。所以摆清影响，等你一句话。

### 现状
本项目用 **Alembic**：`alembic.ini` + `alembic/env.py` 已改完（§13.7/§13.8），迁移链已起步。

### Yuxi 那套的**真实优势**
它**不做"metadata ↔ 数据库"的反射比对**，因此**天然没有我们踩过的那个坑**：
`server_default` 文本差一个括号 → 每次 `autogenerate` 多一条无意义 `modify_default`（§13.6 坑二，MySQL 8.0.46 实测）。

### 但代价是实打实的
1. **方言全不一样**：`pg_advisory_lock` → MySQL 要换 `GET_LOCK()`；`ADD COLUMN IF NOT EXISTS` → MySQL **不支持**，得自己查 `information_schema` 判断列是否存在再决定发不发 DDL。**等于重写一套**
2. **它那套复杂度是为特定场景付的**：Yuxi 要处理「**多容器 + 多 schema 域 + 停机窗口内把 v0.7.1 本地文件搬进库**」（见 `storage_migration.py` 里那套 `_require_quiescence_proof()` 停机证明机制）。
   **我们现在：1 张表、单容器、无历史数据要搬**——这个复杂度现在买不到东西
3. **我们那个坑已经解决了**：`text("(UTC_TIMESTAMP())")`（带括号）实测往返零差异，§13.6 坑二已有结论

### 我的判断（结论先行）

> **现在不换。** 理由不是"Alembic 更好"，而是**Yuxi 那套的价值兑现在「多域 + 多容器 + 停机数据迁移」，我们还没到那个阶段。**
> 等真出现「多个 schema 域 + 后台 worker 容器 + 需要搬历史数据」时，再回头评估。

**但有一条建议现在就做**（见 🟡#10）：**在 FastAPI lifespan 加一句「Alembic 当前 revision 必须等于 head，否则拒绝启动」**。
这是从 Yuxi 学到的**思路**（运行时只读校验），而不是搬它的**实现**，成本几乎为零，能挡住"代码上线了、迁移忘了跑"这一类事故。

---

## 7. 附：实测命令备忘

```bash
# 确认 Yuxi 没用 Alembic
find F:/Yuxi -iname "alembic*" -not -path "*/node_modules/*"

# 看存储层全貌
find F:/Yuxi/backend/package/yuxi/storage -type f -name "*.py" | grep -v __pycache__

# 看迁移三个角色的调用点
grep -rn "require_current_schema\|ensure_business_schema\|setup_langgraph_checkpointer" F:/Yuxi/backend --include=*.py

# 看 compose 里的存储服务
grep -n "^  [a-z_-]*:" F:/Yuxi/docker-compose.yml
```

---

_调研日期：2026-09-27 · 执行：小宋 · 依据：`F:\Yuxi` 工作区实地读取（含 `docker-compose.yml` / `pyproject.toml` / `storage/` / `storage_migration.py` / `server/utils/lifespan.py`）_
