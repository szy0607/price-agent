# AGENTS.md — 数据库协作守则（AI 协作者必读）

本项目由两人协作开发，**各自使用自己电脑上的 MySQL**。
本文件是数据库与迁移的权威约定。任何 AI 助手在改动模型、写迁移、或拉取代码后开工前，先读完本文件。

---

## 0. 文档权威顺序（AI 协作者开工前先读这条，2026-09-29 加）

**不要以任何文档（含契约、含本文件）为需求依据。**

| 权威级别 | 来源 | 说明 |
|---|---|---|
| 1（最高） | **项目主人（大宋）的当次指令** | 有疑问直接问，不要猜 |
| 2 | **已拍板的决策** | 散见契约 §0 / §7、各设计文档的「拍板」标注 |
| 3（最低） | 各文档正文 | 是「设计意图 + 历史记录」，**会落后于代码** |

**实时事实源 = `app/` 代码 + git log。** 代码与文档冲突时，默认以代码为准；发现不一致**先报告差异和影响、等项目主人裁决**，不要自行按文档"补实现"。

**禁止**：
- 从文档倒推需求——文档里躺着的字段 / 配置 / 接口，**不代表项目主人拍板过**；
- 发现代码"缺"文档里的东西就擅自建表 / 加列 / 加接口；
- 拿文档质问代码。

🩸 **已发生的事故（本节因它而写）**：2026-09-29，一位协作者的 AI 读了契约旧版里的 `ip` / `user_agent` 两列（项目主人从未确认过、且已拍板删除），据此自行重建了 `user_sessions` 并把两列加回数据库。文档不是需求，需求在项目主人那里。

---

## 1. 项目与关联文档

- 后端 `app/`：FastAPI + SQLAlchemy 2.x（异步）+ MySQL 8 + Alembic
- 前端 `frontend-web/`（网页版，Vue3 + Vite + Tailwind4）、`frontend/`（移动版 Demo，参考工程）
- 接口 / 表结构 / 错误码参考：`docs/用户注册与登录-接口契约.md`（⚠️ **参考，不是权威**，权威顺序见 §0）
- 开发流程参考：`开发流程.md`

## 2. 开工三步（每次拉完代码都做）

1. `git pull`
2. `alembic upgrade head` —— 把本机库升到最新结构
3. `alembic heads` —— 输出**只能有一行**。出现两行说明迁移分叉了，见 §5

## 3. 总则：只同步「表结构」，不同步「数据」

两个人各连自己电脑的 MySQL，彼此通过 **Alembic 迁移文件** 对齐表结构：

| 层 | 例子 | 处理方式 |
|---|---|---|
| 表结构 | `users` 有哪些列、什么类型 | **唯一通道 = Alembic 迁移文件**（进 Git） |
| 初始数据 | 字典表、预置测试账号 | 写成**幂等**脚本 `scripts/seed.py`（先查后插），进 Git；**规划中（尚未创建）**——项目根目前无 `scripts/` 目录 |
| 开发测试数据 | 各自注册的账号、造的订单 | 各造各的，不同步 |
| 真实业务数据 | 真实用户、知识库切片 | 不同步 |

连接隔离靠 `.env`：`.env` 不进 Git，模板 `.env.example` 进 Git。
**库名统一 `price_agent`** —— 库名不一致，迁移对象就不是同一个库，同步无从谈起。

### 为什么数据不做同步

用 `mysqldump` 导出 `.sql` 互相传会同时踩三件事：结构互相覆盖（后导入的赢）、
`uq_users_user_email` 唯一约束撞车、`password_hash` 跟着文件外流。
需要让对方看到某份数据时，**写 seed 脚本或直接描述数据**，不要传库文件。

## 4. 表结构改动的标准动作

1. 改 `app/models/` 下的模型
2. `alembic revision --autogenerate -m "英文短描述"`
3. **逐行读一遍生成的迁移文件** —— autogenerate 有几类固定盲区（见下表）
4. `alembic upgrade head`
5. `git add alembic/versions/<新文件>.py` 并提交

**完成判据**：`alembic current` 与 `alembic heads` 打印出**同一个 revision id**，
且这次生成的 `.py` 文件已包含在本次提交里。

### autogenerate 的固定盲区（每次都人工核对）

| 盲区 | 它生成的错误操作 |
|---|---|
| 列改名 | 删旧列 + 加新列 → **该列数据全丢** |
| 约束 / 索引改名 | 删掉再建 |
| CHECK 约束 | MySQL 下经常整条漏掉 |
| 列类型微调 | `compare_type=True` 已开，多数能认，仍要核对 |

### 迁移脚本里的时间函数

`alembic/env.py` 用的是**裸 `create_async_engine`**，不带 `app/database/session.py` 里的
`connect_args={"init_command": "SET time_zone='+00:00'"}`。
也就是说：**应用连接是 UTC，迁移连接是服务器本地时区（中国 +08:00）**。

所以迁移脚本里写时间默认值时，只用**与时区无关**的函数：

- ✅ `sa.text('(UTC_TIMESTAMP())')` —— 参考已有写法 `alembic/versions/f7fa5f121d6e_create_users.py`
- ❌ `NOW()` / `CURRENT_TIMESTAMP()` —— 随 session 时区变化，两人可能建出不同的默认值

## 5. 并行冲突：两人同时建了迁移

**现象**：`alembic heads` 输出两行；或 `upgrade head` 报
`Multiple head revisions are present for given argument 'head'`。

**原因**：两个迁移文件的 `down_revision` 指向了同一个父节点，形成两条链。

**处理**：

```bash
alembic heads                                   # 确认两个 head 的 revision id
alembic merge -m "merge heads" <rev1> <rev2>    # 生成一个空的合并迁移
alembic upgrade head
git add alembic/versions/<merge文件>.py && git commit -m "merge alembic heads"
```

**预防**：建新迁移**之前**先 `git pull` + `alembic upgrade head`。

**已经共享出去的迁移文件不要再改** —— 对方的库已经执行过它了，改它两边就对不上。
需要修正就新建一个迁移。

## 6. 本机环境必须对齐

这类差异**不会报错**，是"你那边对、我这边错"的幽灵 bug，比结构冲突更难查。

| 项 | 要求 | 不一致的后果 |
|---|---|---|
| MySQL | 8.0.x | autogenerate 产出的 DDL 一边能跑一边不能 |
| 库名 | 统一 `price_agent` | 迁移作用在不同库上 |
| 字符集 / 排序规则 | `utf8mb4` / `utf8mb4_0900_ai_ci` | **唯一索引判定不同**：同一邮箱一边算重复、一边不算 |
| SQL mode | 保持 MySQL 8 默认（含 `STRICT_TRANS_TABLES`） | 超长值、空值一边报错、一边静默截断 |
| 时区 | **无需自行配置**，`app/database/session.py` 已固定 `+00:00` | — |
| Python | 3.10+（本项目开发环境为 conda `fast`，3.10.20） | 语法 / 类型行为差异 |

## 7. 新人首次建库

```sql
CREATE DATABASE price_agent DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

然后：

```bash
cp .env.example .env    # 改 DB_URL 指向本机 MySQL
alembic upgrade head    # 建表（不建表的话应用一启动就连表都找不到）
```

> 注：`alembic upgrade head` 只建表结构，**不会自动创建数据库**，所以 `CREATE DATABASE` 必须手跑一次。
