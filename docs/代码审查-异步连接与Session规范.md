# 代码审查：异步连接与 Session 规范

> 日期：2026-09-16 ｜ 审查对象：`app/config.py`、`app/core/session.py`、`app/database/user.py`
> （`app/main.py`、`app/router/register.py`、`app/shcema/user_sche.py` 尚为空文件）
> 依据：`开发流程.md` §6 代码规范 / §7 合规红线 ｜ `docs/用户注册与登录-接口契约.md`

---

## 0. 总评

连接池配置方向是对的（`pool_pre_ping` / `pool_recycle` / `expire_on_commit=False` / `naming_convention` 都做对了，保留）。主要问题是**职责没有分层**、**依赖没有声明**；`get_session` 的空实现就是本轮要补的关键一步（见 §3）。

---

## 1. 决策漂移（需同步文档）

| 点 | 契约原定 | 你的实现 | 处理 |
|----|---------|---------|------|
| 驱动 | 同步 `PyMySQL` | **异步 `aiomysql`** | ✅ 以实现为准，契约已同步为异步 |
| user 字段 | 仅 `email` + `nickname` | 多了 `username` | ⏳ 你定：删掉，还是改成"email / username 双唯一可登录"？ |

---

## 2. 逐文件问题清单

### 2.1 `app/config.py` —— 一个文件装了四件事

| 级别 | 问题 | 改法 |
|------|------|------|
| P0 | 配置 / engine / sessionmaker / Base 混在一个文件 | 拆成 `core/config.py`、`db/session.py`、`db/base.py`（契约 §4 分层） |
| P0 | `echo=True` 硬编码 | 改为配置项 `DB_ECHO`，默认 `False`（生产开 echo 会把 SQL 参数写进日志，有泄露风险） |
| P0 | `os.getenv('DB_URL')` 无校验，取不到会以 `None` 传给 engine，报错难懂 | 缺失即抛明确异常；建议直接上 `pydantic-settings`（契约 §9.2 已约定） |
| P1 | 没用 `pydantic-settings` | 用 `BaseSettings` 集中管理 `DB_URL` / `DB_ECHO`，类型安全 |
| 🟢 | `pool_pre_ping` / `pool_recycle` / `pool_size` / `expire_on_commit=False` / `naming_convention` | 保留，做得规范 |

### 2.2 `app/core/session.py` —— 位置错 + 无用导入

| 级别 | 问题 | 改法 |
|------|------|------|
| P0 | `from sqlalchemy.util import await_only` 是 SQLAlchemy **内部 API**，且你根本用不到 | **删除**。它会在 greenlet 场景抛出误导性报错 |
| P0 | 位置错：依赖注入不该放 `core/` | 移到 `app/db/session.py`（或 `api/deps.py`）；`core/` 只放配置 / 安全 / 日志 / 异常 |
| P0 | `get_session()` 空实现 | 见 §3.1 标准写法 |

### 2.3 `app/database/user.py` —— 目录语义 + 字段缺口

| 级别 | 问题 | 改法 |
|------|------|------|
| P0 | `Mapped[str]` 没给长度 → MySQL 建表直接报错（`VARCHAR` 必须带长度） | `String(254)` / `String(255)` |
| P0 | 缺契约字段：`nickname` / `status` / `created_at` / `updated_at` / `last_login_at` / `deleted_at` | 按契约 §1.1 补齐 |
| P1 | 目录 `database/` 语义模糊 | 改 `app/models/user.py`（模型归 `models/`） |
| P1 | `user_email` 冗余前缀，与契约字段名不符 | 统一为 `email` |
| P1 | `password_hash` 加了 `index=True` | 删掉——哈希不参与查询，索引白白拖慢写入 |
| P1 | `unique=True` 与 `index=True` 并用 | 只留 `unique=True`（唯一约束本身即索引） |

### 2.4 空文件 / 拼写

| 级别 | 问题 | 改法 |
|------|------|------|
| P0 | 目录拼写 `shcema` → **`schemas`**；文件 `user_sche.py` | 改为 `app/schemas/user.py`（或 `auth.py`） |
| — | `main.py` / `router/register.py` 空 | 按契约 §4 顺序补 |

### 2.5 依赖缺失（P0）

当前**没有 `requirements.txt` / `pyproject.toml`，也没有虚拟环境**（违反契约 §6「依赖锁定」）。异步栈至少需要：

```
fastapi
uvicorn[standard]
sqlalchemy>=2.0
aiomysql            # 异步 MySQL 驱动
cryptography        # MySQL 8 caching_sha2_password 认证
greenlet            # SQLAlchemy async 运行时依赖
pydantic>=2
pydantic-settings
email-validator
python-dotenv       # 若不用 pydantic-settings 读 .env
alembic
pytest
pytest-asyncio      # 异步测试
httpx
```

---

## 3. 核心：异步怎么拿到 session（标准写法）

### 3.1 定义（`app/db/session.py`）

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.db_url,
    echo=settings.db_echo,        # 生产 False
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,       # 关键：避免 commit 后属性过期触发隐式 IO
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

### 3.2 在路由里用（依赖注入）

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/register", status_code=201)
async def register(payload: RegisterReq, session: SessionDep):
    data = await auth_service.register(session, payload)
    return {"code": 0, "message": "ok", "data": data}
```

### 3.3 在 service 里用（提交 / 回滚归业务）

```python
async def register(session: AsyncSession, payload: RegisterReq):
    user = User(
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        nickname=payload.nickname or "",
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:          # 唯一索引兜底并发
        await session.rollback()
        raise ConflictError(40901, "邮箱已被注册")
    await session.refresh(user)
    return {"id": user.id, "email": user.email, "nickname": user.nickname}
```

### 3.4 为什么这么设计

- `async with SessionLocal() as session` —— 请求结束**自动 `close()`**，连接归还连接池。这就是"拿到 session 后怎么收尾"的答案，不用手写 close。
- **依赖里不 commit** —— commit 归 service：读接口不该 commit，写接口自己决定事务边界。
- **必须用 `yield` 而不是 `return`** —— FastAPI 只有对 `yield` 依赖才会在「请求结束后」执行清理逻辑，`return` 不行。

---

## 4. 异步专属的 5 个坑

1. **MissingGreenlet**：session 关闭后再访问未加载的 ORM 属性会触发隐式 IO 而报错。`expire_on_commit=False` 挡掉大部分；跨对象读关联用 `selectinload()` 预加载。
2. **session 不能跨请求共享**：每请求一个（依赖注入天然保证），别做成模块级全局单例。
3. **同一 session 不能并发**：别在 `asyncio.gather` 里共用同一个 session。
4. **驱动依赖**：异步必须 `aiomysql`；SQLAlchemy async 还要 `greenlet`；MySQL 8 认证要 `cryptography`。
5. **连接串**：`mysql+aiomysql://...?charset=utf8mb4`（不是 `mysql+pymysql`）。

---

## 5. 整改待办清单

- [ ] 🔴 **`.env` 加入 `.gitignore`**：当前 `.gitignore` 只有 node_modules/dist 等，**没有 `.env` / `.venv` / `__pycache__`** —— 数据库密码有被提交进 Git 的风险
- [ ] 建虚拟环境 + `requirements.txt` / `requirements-dev.txt`（见 §7）
- [ ] 拆 `config.py` → `core/config.py` + `db/base.py` + `db/session.py`（见 §6）
- [ ] 删 `await_only` 导入与空实现，按 §3.1 重写 `get_session`
- [ ] `database/` → `models/`；补齐 `users` 字段与 `String` 长度
- [ ] `shcema` → `schemas`
- [x] 决策已定：**只做 email 登录** → 删掉 `users.username`（与契约 §1.1 一致，无需改契约）

---

## 6. config 怎么拆 + 为什么

### 6.1 拆成三个文件

**`app/core/config.py`** —— 只做"读配置"

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    db_url: str                       # 缺失时启动即报错，而不是把 None 传进 engine
    db_echo: bool = False             # 生产 False
    session_ttl_seconds: int = 7 * 24 * 3600
    cookie_secure: bool = False       # 生产 True


settings = Settings()
```
> 字段名 `db_url` / `db_echo` 自动匹配环境变量 `DB_URL` / `DB_ECHO`（大小写不敏感）。

**`app/db/base.py`** —— 只做"ORM 元数据基类"

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

**`app/db/session.py`** —— 只做"连接与 session"

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.db_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)

SessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

### 6.2 为什么必须拆（三条硬理由）

1. **变化原因不同（单一职责）**：配置随**环境**变（改密码 / 开关）；命名约定随**建模规范**变；连接策略随**驱动 / 池化**变。三件事互不相关，塞一个文件 = 动任何一处都要改同一文件，冲突与回归风险叠加。
2. **依赖方向不能倒挂**：`Base` 是**模型层的基类**，被 `models/` 依赖；它绝不该反向依赖"读配置、建引擎"。拆开后 `models/user.py` 只 `import app.db.base`，方向干净。
3. **避免 import 副作用（最关键）**：Alembic 的 `env.py` 需要 `Base.metadata`，但**不需要 engine**。若 Base 与 engine 同文件，`import Base` 会顺带执行 `create_async_engine(...)` —— 一个纯元数据操作却建立了连接池。拆开后 `import app.db.base` **零副作用**。

> 这也是契约 §4.1「依赖方向铁律」的落地：`core` 只放读配置，`db` 放数据访问基础设施，`models` 放业务表。

### 6.3 迁移注意

- 每个包目录补 `__init__.py`（`app` / `app/core` / `app/db` / `app/models` / `app/schemas` …），否则导入与 Alembic 会发现不了。
- 拆完**删掉旧的 `app/config.py`**，把所有 `from app.config import ...` 改到新路径（别留两份）。

---

## 7. requirements 怎么写

### 7.1 策略

- **两个文件**：`requirements.txt`（运行必需）＋ `requirements-dev.txt`（开发 / 测试，首行 `-r requirements.txt` 复用）。
- **版本约束**：日常用范围约束（`>=2.0` 或 `~=2.0`），避免过早死锁；需要精确复现时再 `pip freeze > requirements.lock.txt` 提交锁文件。
- **别拿 `pip freeze` 当源文件**：它会把传递依赖全列进来，难维护；只把它当锁文件。
- 可选上 `uv`（`uv lock`，更快，原生锁文件）——契约 §6 允许"requirements.txt 或 uv 锁文件"。

### 7.2 内容

`requirements.txt`
```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]>=2.0
aiomysql                # 异步 MySQL 驱动
cryptography            # MySQL 8 caching_sha2_password 认证需要
greenlet                # SQLAlchemy async 运行时依赖
pydantic>=2
pydantic-settings
email-validator         # Pydantic EmailStr
bcrypt
alembic
```

`requirements-dev.txt`
```
-r requirements.txt
pytest
pytest-asyncio
httpx
```

### 7.3 装法

```bash
python -m venv .venv
source .venv/Scripts/activate          # Windows Git Bash
pip install -r requirements-dev.txt
pip freeze > requirements.lock.txt     # 可选：锁精确版本
```

> 记得把 `.venv/`、`__pycache__/`、`.env` 写进 `.gitignore`（当前缺失，见 §5 第一条）。

---

## 8. 复评（2026-09-16 第二轮）

### 已修复
- ✅ `config.py` 已瘦身（只剩 `DB_URL`）；engine → `database/session.py`，`Base` + naming_convention → `database/base.py`。
- ✅ 目录拼写 `shcema` → `schemas`。
- ✅ `.gitignore` 已补 `.env` / `.workbuddy` / `.screenshots`。

### 仍待修（P0）
1. 🔴 **断链**：`app/database/user.py:4` 仍是 `from app.config import Base` —— 但 `Base` 已搬到 `app/database/base.py`，这里会 **ImportError**。改成 `from app.database.base import Base`。
2. 🔴 `app/database/session.py` 仍 `echo=True`；且 **`get_session()` 还没写**（本轮核心，见 §3.1）。
3. 🔴 `.gitignore` 还缺 `.venv/`、`__pycache__/`、`*.pyc`。

### 建议（P1 / P2）
- `app/config.py` 仍是 `os.getenv`、无校验；建议 pydantic-settings —— 缺失时启动即报错，而不是把 `None` 传进 engine 后报晦涩错误（见 §6.1）。
- `session.py` 里 `async_sessionmaker` 变量名 `AsyncSession` 与 SQLAlchemy 的类同名，可读性差，建议 `SessionLocal`。
- 目录：`database/` 可只放 `base.py` + `session.py`（数据访问基础设施）；**ORM 模型应独立到 `models/user.py`**，别混在 `database/`。
- `user` 模型：`username` 待删（已定 email 登录）；`user_email` → `email`（`String(254)`）；`create_time` → `created_at`；补 `nickname / status / updated_at / last_login_at / deleted_at`；`default=func.now()` 建议同时给 `server_default=func.now()`。

---

## 9. 详解：为什么用 pydantic-settings 取代 os.getenv

### 9.1 现状代码的四个真实问题

```python
from dotenv import load_dotenv
load_dotenv()
import os
DB_URL = os.getenv('DB_URL')
```

**问题 1：可能返回 `None`，且没人拦**
`os.getenv` 的类型是 `str | None`。`.env` 没加载到、键名拼错、部署忘了注入环境变量 —— 全部**静默返回 `None`**。它一路传到 `create_async_engine(None, ...)`，最后报一个和根因八竿子打不着的错：

```
AttributeError: 'NoneType' object has no attribute 'drivername'
```

你看到这个错会去查 SQLAlchemy，其实问题在"配置压根没读进来"。

**问题 2：全是字符串，布尔/数字会出 bug（最常见）**
`os.getenv` 只能给你 `str`。一旦要加 `DB_ECHO`：
```python
DB_ECHO = os.getenv("DB_ECHO", "false")   # 你以为是 False
```
`"false"` 是**非空字符串**，`bool("false")` 是 **`True`** —— 你以为关了 echo，生产在狂打 SQL。数字同理：`POOL_SIZE` 拿到的是 `"10"` 而不是 `10`，参与计算时行为诡异。

**问题 3：散落各处，无单一事实源**
每个文件各自 `os.getenv(...)`，键名写错没人提醒；改一个键名要全局搜。

**问题 4：密码会进日志 / repr**
`DB_URL` 含密码。一旦有人 `print` 配置对象或把它打进日志，密码就泄露了（违反 §7「日志脱敏」）。

### 9.2 pydantic-settings 给了什么

| 能力 | 效果 |
|------|------|
| 声明式 + 类型注解 | `db_echo: bool = False` 自动把 `"false"` 转成 `False` |
| 必填校验 | 缺 `db_url` → **启动即 `ValidationError`**，消息直接点名 `db_url` |
| `.env` 自动读取 | `SettingsConfigDict(env_file=".env")`，不用手写 `load_dotenv` |
| 优先级 | 真实环境变量 > `.env`（部署覆盖方便） |
| 字段映射 | 字段 `db_url` ↔ 环境变量 `DB_URL`（大小写不敏感） |
| 默认值 | 可选项给默认值，必填项不给 |
| `SecretStr` | 密码字段打印为 `**********`，`.get_secret_value()` 才拿到真值 |
| 单例集中 | 全局 `settings`，改一处处处生效，编辑器有补全 |

一句话：把"配置读错"从**运行时、离根因很远的晦涩报错**，变成**启动时、点名到字段的清晰报错**（fail fast）。

### 9.3 改造写法

**最小改动**（保留你现在 `DB_URL` 单变量）

`app/config.py`：
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    db_url: str                 # 必填：缺失则启动报错
    db_echo: bool = False       # 可选：默认关


settings = Settings()
```

`app/database/session.py`：

```python
from app.core.config import settings

async_engine = create_async_engine(
    settings.db_url,
    echo=settings.db_echo,  # 布尔，不会再出现 "false" 当 True
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)
```

`.env` 加一行：
```
DB_ECHO=false
```
改造后可删掉 `from dotenv import load_dotenv` 与 `import os`（pydantic-settings 自己会读 `.env`）。

**进阶（可选）：拆字段 + 密码用 SecretStr**
```python
from urllib.parse import quote_plus

from pydantic import SecretStr


class Settings(BaseSettings):
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "price_agent"
    db_password: SecretStr
    db_name: str = "price_agent"
    db_echo: bool = False

    @property
    def db_url(self) -> str:
        pwd = quote_plus(self.db_password.get_secret_value())   # 密码含 @ : / 等要转义
        return (
            f"mysql+aiomysql://{self.db_user}:{pwd}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )
```

### 9.4 雷点

1. **必须从 `pydantic_settings` 导入**（`from pydantic_settings import BaseSettings`）。从 `pydantic` 导入会报错 —— v2 把 `BaseSettings` 拆成了独立包。
2. **`env_file` 相对"当前工作目录"**：在别的目录启动 uvicorn（或 IDE 工作目录不对）时 **`.env` 找不到**，于是必填校验失败。稳妥写法：
   ```python
   from pathlib import Path
   env_file=Path(__file__).resolve().parents[1] / ".env"
   ```
3. **`Settings()` 在 import 时执行** —— 这正是"启动即失败"的来源，是想要的行为；但别在模块顶层塞耗时操作。
4. **测试覆盖配置**：用 `monkeypatch.setenv("DB_URL", ...)` 后重新 `Settings()`，或走依赖注入。
5. **`case_sensitive=False` 是默认**，所以 `db_url` ↔ `DB_URL` 能对上；别写成 `DB_url` 这种混合名。
6. 改造后 `python-dotenv` 不用你显式调用了（它是 pydantic-settings 的间接依赖）。

### 9.5 迁移步骤

1. `requirements.txt` 已含 `pydantic-settings`（无需另加）
2. 重写 `app/config.py` 为 `Settings`
3. `session.py` 改 `from app.config import settings`，用 `settings.db_url` / `settings.db_echo`
4. `.env` 加 `DB_ECHO=false`
5. 删掉 `load_dotenv()` 与 `import os`

### 9.6 动手步骤（照着敲）

**Step 1 · 装包 + 确认 `.env` 在项目根**
```bash
pip install -r requirements.txt     # 已含 pydantic-settings
cat .env                            # 确认 DB_URL 在里面
```

**Step 2 · 重写 `app/config.py`**
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    db_url: str
    db_echo: bool = False


settings = Settings()
```
逐行说明：
- `SettingsConfigDict(...)`：告诉它**去哪读、怎么读**。
- `env_file=".env"`：自动读 `.env` —— 不再需要 `load_dotenv()`。
- `case_sensitive=False`：字段 `db_url` 能匹配环境变量 `DB_URL`（本就是默认值，写上更直观）。
- `extra="ignore"`：环境里多余的变量不触发校验错误。
- `db_url: str`：**没有默认值 = 必填**，缺失就启动报错。
- `db_echo: bool = False`：有默认值 = 可选；且自动把 `"false"` 转成 `False`。
- `settings = Settings()`：**import 时实例化** → 配置错在这一刻就暴露（正是我们要的）。

**Step 3 · 先验证再往下写（重要，别跳）**
```bash
python -c "from app.config import settings; print(settings.db_url); print(repr(settings.db_echo))"
```
预期：打印出 URL；`db_echo` 是 `False`，**不是** `'false'`。

再**故意让它失败**：把 `.env` 里的 `DB_URL` 临时改名为 `DB_URLX`，重跑，应看到：
```
pydantic_core.ValidationError: 1 validation error for Settings
db_url
  Field required [type=missing, ...]
```
看到"**点名字段 + 启动就报**"了吧 —— 这就是它相对 `os.getenv` 的全部价值。看完改回去。

**Step 4 · 接到 `app/database/session.py`**

```python
from app.core.config import settings

async_engine = create_async_engine(
    settings.db_url,
    echo=settings.db_echo,  # 布尔，不会出现 "false" 当 True
    ...
)
```

**Step 5 · `.env` 加一行**
```
DB_ECHO=false
```

**Step 6 · 清掉旧写法**
删掉 `from dotenv import load_dotenv` / `load_dotenv()` / `import os`（整个旧 `config.py` 内容替换）。

### 9.7 常见报错对照表

| 报错 | 原因 | 解法 |
|------|------|------|
| `ValidationError: 1 validation error for Settings / db_url / Field required` | `.env` 没读到，或缺 `DB_URL` | 确认 `.env` 在当前工作目录、键名拼写正确 |
| `ImportError: cannot import name 'BaseSettings' from 'pydantic'` | 用了 v1 的导入路径 | 改 `from pydantic_settings import BaseSettings` |
| `ModuleNotFoundError: No module named 'pydantic_settings'` | 没装包 | `pip install pydantic-settings` |
| `db_echo` 明明是 `false` 却是 `True` | 还在用 `os.getenv` | 交给 pydantic 的 `bool` 注解转换 |
| 本机跑得通、换目录跑不通 | `env_file` 相对「当前工作目录」 | 用绝对路径 `Path(__file__).resolve().parents[1] / ".env"` |
| `ValidationError ... extra_forbidden` | `extra` 被设成 `forbid` 且环境有多余变量 | 设 `extra="ignore"` |

### 9.8 补充：实例化 `Settings` 时到底要不要传参？

**结论：正常业务代码就是空参 `Settings()`；传参是留给"覆盖"用的。**

**为什么空参可行**：取值来源由 `model_config` 决定 —— 环境变量天生支持；`.env` 因为写了 `env_file` 才会读。`Settings()` 时 pydantic 按**字段名**去这些来源查找：找到就赋值并做类型转换；找不到但有默认值 → 用默认值；找不到且无默认值（如 `db_url`）→ `ValidationError`。这正是 12-factor 的做法：**配置进环境，代码里不留明文**（把连接串写死在代码里 = 密码进版本库，前面所有努力白费）。

**默认取值优先级（高 → 低）**：

1. **构造参数** `Settings(db_url=...)`
2. **真实环境变量**
3. **`.env` 文件**
4. 字段默认值

**覆盖用法**（测试 / 临时脚本）：
```python
s = Settings(db_url="sqlite+aiosqlite:///:memory:", db_echo=True)
```

**特殊 init 参数**（以 `_` 开头，**不是字段**）：
```python
Settings(_env_file=".env.test")   # 指定另一个 env 文件
Settings(_env_file=None)          # 完全忽略 .env，只读真实环境变量
```

**易混点**：环境变量**默认就支持**（无需任何配置）；`.env` 文件**必须显式写 `env_file=`** 才会被读。

**FastAPI 里更推荐的另一种写法**（避免 import 副作用、便于测试替换）：
```python
from functools import lru_cache


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
```
测试里可 `app.dependency_overrides[get_settings] = lambda: Settings(...)`。

**自测三条命令**：
```bash
python -c "from app.config import Settings; print(Settings().db_url)"                  # 来自 .env
python -c "from app.config import Settings; s=Settings(db_url='X'); print(s.db_url)"   # X（构造参数优先）
DB_URL=Y python -c "from app.config import Settings; print(Settings().db_url)"          # Y（环境变量优先于 .env）
```

---

*本文件为本轮「编码 → 代码审查」产物；整改后可据此复评。*
