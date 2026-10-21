# 智能导购 Agent（购物决策助手）

个人定制购物助手：通过对话理解用户需求（预算、平台偏好、学生身份、性价比 / 品质取向），维护个人购物车与物品库参数档案，AI 联网补全商品参数，并记录个人消费流水。**AI 是顾问，不是代购——下单与支付 100% 由用户自己完成。**

> 版本口径：设计方案 v0.8（2026-10-02 消费记录拍板）。价格情报线已按 v0.8 决策删除：不做联盟 API 比价、不承诺实时最低价；价格只来自用户自记与 AI 补全的网络参考价（带提示、可修改）。

---

## 在线体验（比赛 / 评委入口）

完整生产环境已部署（后端 + 数据库 + RAG 索引链路 + 前端，Docker Compose 七容器）：

> **http://47.93.117.76/price-agent/**

**请使用演示账号登录**（已预置完整演示数据与模型 Key，开箱即用，无需注册、无需配置）：

| 账号 | 密码 | 预置数据 |
|---|---|---|
| `demo@example.com` | `Demo2026` | 购物车 20 件（带商品图）+ 物品库 / 消费记录各 20 条 + 用户画像 + 默认对话 / 向量模型 Key |
| `demo2@example.com` | `Demo2026` | 同上（独立数据，供两人同时演示） |

> 演示商品图（40 张 AI 生成白底电商图）经 nginx 静态目录公开伺服，绑定 demo / demo2 账号商品数据；新注册账号无演示数据（真实产品行为）。模型 Key 由部署环境自动注入并加密落库，评委登录即可直接聊天 / AI 联网补全 / RAG 语义检索，无需进设置页。

**纯前端演示版**（GitHub Pages，无后端）：https://szy0607.github.io/price-agent/

> 在线版为纯前端演示：注册 / 登录 / 验证码、购物车 / 物品库 / 消费记录等业务功能均需搭配本地后端（`127.0.0.1:8000`）联调；业务页进入需先登录（在线演示页登录态暂存 localStorage）。

---

## 功能特性

| 模块 | 说明 | 状态 |
|------|------|------|
| 智能咨询 `/chat` | 多会话对话（懒创建 / 列表 / 历史 / 改标题）；右侧商品引用面板勾选购物车与物品库商品随消息发给模型；每轮结束后台异步跑 A6 画像；模型使用「设置」中的默认 API Key | ✅ 已落地 |
| **多智能体 A1（LangGraph）** | `app/agents/a1_graph.py` 5 节点编排图：`decide` 自主路由 → `search`（RAG 检索）/ `compare`（A4 参数对比）/ `recommend`（A5 画像推荐，博查联网）/ `card`（商品卡片） | ✅ 已落地 |
| **RAG 语义检索（M3）** | PostgreSQL 16 + pgvector 向量副本库 + arq worker 索引链路 + reaper 补偿；按用户问题选维度、分维度对比检索 | ✅ 已落地 |
| 购物车 `/cart` | 已确认参数档案清单：增删改查、AI 联网补全草稿（`ai-draft`，不入库、确认后落库）、标记已购转入物品库 | ✅ 已落地 |
| 物品库 `/items` | 已购物品参数档案：增删改查；支持直接建档（不经过购物车，双入口） | ✅ 已落地 |
| 购物分组 `/groups` | 把购物车（未购买）和物品库（已购买）的物品归成一组：组内分已购买 / 未购买两区展示，统计各区与总计价格（无价格物品提示「未填价」不计入合计）；一个物品可进多个分组；删分组不动物品 | ✅ 已落地 |
| 消费记录 `/spending` | 用户自记消费流水：商品名 / 链接 / 平台 / 价格 / 规格；贴链接可抓取页面生成草稿（待用户确认后落库）；消费记录可勾选注入对话上下文 | ✅ 已落地 |
| 用户画像 | `user_profile` 表一行一用户（`preferences` 自由键值）；A6 画像 Agent 每轮对话结束后台异步提炼长期偏好（同会话近期对话 + 行为证据摘要，全量覆盖，防抖动三层）；chat 同步注入偏好与行为证据 | ✅ 已落地 |
| 账号系统（后端） | 注册 / 登录 + 图形验证码（人机验证）、bcrypt 密码哈希、Cookie 会话（`user_sessions`，token 哈希落库）、登出、`/auth/me` | ✅ 已落地 |
| 设置 `/settings` | 用户自定义模型供应商（`provider` / `base_url` / `model_name`）、默认 Key 管理；API Key 以 AES-256-GCM 加密存储、脱敏展示 | ✅ 已落地 |
| 图片上传 | 商品展示图上传（2MB 上限 + 限流）、访问统一收口鉴权（登录 + 归属校验）、生命周期自动清理（后台定时任务，幂等） | ✅ 已落地 |
| **演示商品图** | 40 张 AI 生成白底电商图绑定 demo / demo2 账号（购物车 01–20、物品库 21–40），nginx 静态公开伺服 | ✅ 已落地 |

> 📌 **心愿单**：2026-10-18 大宋拍板**不做** —— v0.7 的「购物分组 + 物品库」已经覆盖了「想买 vs 已买」的区分。占位路由与 `ComingSoonView.vue` 已删除。

---

## 系统架构

### 生产部署（Docker Compose，7 容器）

```mermaid
flowchart LR
    U[浏览器<br/>评委 / 用户] -->|HTTP :80| N[nginx<br/>pa-nginx]
    N -->|/price-agent/ 静态文件| SPA[前端 Vue3 构建产物<br/>含 40 张商品图]
    N -->|其余 API 反向代理| B[FastAPI 后端<br/>pa-backend :8000<br/>--workers 1]
    B -->|业务数据唯一事实源| M[(MySQL 8<br/>price_agent)]
    B -->|embedding 向量副本| P[(PostgreSQL 16<br/>+ pgvector)]
    B -->|任务队列| R[(Redis 7<br/>arq)]
    W[arq worker<br/>pa-worker] -->|消费索引任务| R
    W -->|写入向量| P
    RP[reaper 补偿<br/>pa-reaper] -->|每 5 分钟扫僵死任务| R
```

**关键设计**：

| 点 | 说明 |
|---|---|
| 单一对外入口 | 仅 nginx 暴露 `80:80`；后端 8000、MySQL/PG/Redis 全部内网隔离，外部不可达 |
| MySQL 是唯一事实源 | 业务数据（用户 / 购物车 / 物品库 / 消费 / 会话 / 图片登记）全在 MySQL；PG 只是 embedding 副本，可幂等重建 |
| 索引链路三进程 | Web 把商品写进 Redis 队列 → arq worker 消费并写向量到 PG → reaper 每 5 分钟补偿僵死 / 失败任务；缺任一进程商品会卡 `PENDING` 且不报错 |
| 前端固定 `/price-agent/` | Vite `base=/price-agent/`，nginx 按路径分流：`/price-agent/` 走静态 SPA（history 路由兜底），其余全部反代后端；SSE 流式对话关缓冲（`proxy_buffering off`） |
| 后端单 worker | 限流与 A5 日限次是**进程内计数**，多 worker 会稀释配额 N 倍（刻意 `--workers 1`） |
| 图片双通道 | 演示商品图 → nginx 静态目录（公开，绑定 demo 账号数据）；用户上传图 → 后端 `/uploads/`（登录 + 归属鉴权，仅本人可见） |

---

## 技术栈

| 模块 | 技术栈 |
|------|--------|
| 网页版前端 | Vue 3.5 + Vite 5 + Tailwind 4 + Phosphor Icons + Vue Router 4 |
| 移动版 Demo | Vue 3 + Vite 5 + Vant 4（参考工程） |
| 后端 | Python 3.10 + FastAPI + 异步 SQLAlchemy 2.0 + Pydantic v2 + bcrypt + Pillow（验证码） |
| 业务数据库 | MySQL 8（唯一事实源，库名 `price_agent`，utf8mb4 / UTC 时区口径） |
| 向量 / 队列 | PostgreSQL 16 + pgvector（embedding 副本）；Redis 7 + arq（索引任务队列） |
| 多智能体 | LangGraph（A1 编排图，5 节点自主路由） |
| 迁移 | Alembic（异步，时间默认值只用 `UTC_TIMESTAMP()`） |
| 密钥加密 | AES-256-GCM（`API_KEY_KEK` 主密钥） |
| AI 能力 | 用户自配 OpenAI 兼容供应商（`base_url` + `model_name`，取唯一默认 Key）；博查 Bocha Web Search API（联网补全） |
| 测试 | pytest + pytest-asyncio（后端）；`node --test`（前端） |
| 生产部署 | Docker Compose 七容器（nginx / FastAPI / MySQL8 / PG16+pgvector / Redis7 / arq worker / reaper），Ubuntu + 阿里云安全组 80 端口 |

---

## 项目结构

```text
price-agent/
├── frontend-web/               # 网页版前端（Vue 3 + Vite + Tailwind 4）
│   └── public/images/          # 静态图片（placeholder 占位图 + products/ 40 张演示商品图）
├── frontend/                   # 移动版 Demo（Vue 3 + Vant 4，参考工程）
├── app/                        # 后端（FastAPI + 异步 SQLAlchemy）
│   ├── agents/                 # 多智能体（a1_graph.py：A1 编排图，5 节点）
│   ├── core/                   # 配置（.env）、安全（bcrypt）、图形验证码、Cookie 会话、限流、日志、错误处理、中间件、trace、Key 加密、HTTP 客户端
│   ├── database/               # 异步数据库会话与模型基类
│   ├── models/                 # ORM 模型（users、user_sessions、cart_item、owned_item、item_group、item_group_ref、purchase_record、conversation、chat_message、user_profile、user_api_key、user_embedding_key、image）
│   ├── repository/             # 数据访问层（auth / cart / owned / group / conversation）
│   ├── router/                 # 路由（/auth、/health、/setting、/cart、/items、/groups、/purchase-records、/conversations、/upload、/uploads）
│   ├── schemas/                # Pydantic 请求 / 响应模型
│   ├── services/               # 业务服务（模型调用、AI 联网补全、联网搜索、图片存储、商品页抓取、API Key 管理）
│   ├── dependence.py           # 依赖注入（数据库会话、当前用户、同源写保护）
│   └── main.py                 # 应用入口（日志、统一异常、trace 中间件、lifespan 图片清理任务）
├── deploy/                     # 生产部署（Docker Compose 七容器）
│   ├── docker-compose.yml      # 编排（内存预算、健康检查、卷持久化）
│   ├── Dockerfile.backend      # 后端镜像（alembic 迁移后起 uvicorn）
│   ├── Dockerfile.frontend     # 前端镜像（vite build → nginx 托管）
│   ├── nginx.conf              # 静态伺服 + API 反代 + SSE 流式
│   ├── .env.example            # 生产密钥模板（cp 为 .env 后填真实值）
│   └── README.md               # 部署指南（服务器准备 / 启动 / HTTPS / 备份 / 2C2G 要点）
├── alembic/                    # 数据库迁移（versions/，17 个迁移文件）
├── docs/                       # 接口契约与设计文档
├── scripts/                    # 脚本（seed_user13_data.py 素材集、seed_demo.py 幂等演示数据）
├── tests/                      # 后端测试（pytest + pytest-asyncio）
├── postman/                    # Postman 环境 / 全局变量
├── static/                     # Swagger / ReDoc 静态资源
├── uploads/                    # 用户上传图片（运行时生成，不入 Git）
├── .github/workflows/deploy.yml # GitHub Pages 自动部署
├── 智能电商采购Agent-设计方案.md  # 设计方案底稿（v0.8）
├── 开发流程.md                   # 开发流程与合规红线
├── AGENTS.md                   # 数据库协作守则（AI 协作者必读）
├── requirements.txt            # 后端运行依赖
├── requirements-dev.txt        # 后端开发 / 测试依赖
└── .env.example                # 本地环境变量模板（复制为 .env）
```

---

## 本地开发

### 后端服务（app）

后端运行环境为 conda 环境 `fast`（Python 3.10），在项目根目录执行：

```cmd
conda activate fast
cd /d F:\price-agent
pip install -r requirements-dev.txt   # 开发（含测试依赖）
alembic upgrade head                   # 执行数据库迁移（见 AGENTS.md 开工三步）
python -m uvicorn app.main:app --port 8000 --reload --no-access-log   # http://127.0.0.1:8000
```

> `--no-access-log`：关闭 uvicorn 原生的状态码行（无时间戳 / trace_id），避免与 `app.access` 访问日志重复。备选 `fastapi run --port 8000`（功能正常，但控制台不显示 `app.access` 日志）。

### 网页版前端（frontend-web）

```cmd
cd /d F:\price-agent\frontend-web
npm install
npm run dev      # 开发服务器 http://localhost:5174/price-agent/
npm run build    # 构建产物 dist/
npm test         # node --test tests/*.test.mjs
```

> 开发服务器已配置代理，API 前缀全部转发到本地后端 `http://127.0.0.1:8000`（`/auth` `/setting` `/chat` `/conversations` `/purchase-records` `/cart` `/items` `/groups` `/upload`）——**本地用 Vite 当"前台"替代 nginx**，后端必须起在 **8000** 端口才通。生产则用 nginx 承担同一职责（见「系统架构」）。

### 移动版 Demo（frontend，可选）

```cmd
cd /d F:\price-agent\frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # 产物 dist/
```

### 后端测试

```cmd
pytest
```

> 无 pytest 配置文件（strict 模式），异步测试需显式挂 `@pytest.mark.asyncio`（见 `tests/test_purchase_record.py`）。前端测试见上。

### 演示数据（本地也可跑）

```cmd
python scripts/seed_demo.py
```

幂等脚本：先查后插，重复执行只打印 `[skip]`。预置 `demo@example.com` / `demo2@example.com`（密码 `Demo2026`）两个演示账号 + 购物车 / 物品库 / 消费记录 / 画像 / 默认模型 Key。

### 数据库迁移

改了 `app/models/` 之后：`alembic revision --autogenerate -m "英文短描述"` → 逐行读生成的迁移文件（autogenerate 盲区清单见 `AGENTS.md` §4）→ `alembic upgrade head`。完成判据：`alembic current` 与 `alembic heads` 打印同一个 revision id。**多人协作只同步表结构、不同步数据**，详见 `AGENTS.md`。

---

## 环境变量（.env）

后端通过根目录 `.env` 读取配置（见 `app/core/config.py`）。`DB_URL`、密码长度口径、`CAPTCHA_KEY` 为**必填**（缺失时应用 import 即报错）；其余为可选：

| 变量 | 说明 | 示例 |
|------|------|------|
| `DB_URL` | 异步 MySQL 连接串（**必填**） | `mysql+aiomysql://user:password@127.0.0.1:3306/price_agent?charset=utf8mb4` |
| `PW_MIN_LENGTH` / `PW_MAX_LENGTH` | 密码最小 / 最大长度（**必填**，两人口径需一致） | `6` / `18` |
| `CAPTCHA_KEY` | 图形验证码签名密钥，HMAC-SHA256（**必填**，`secrets.token_urlsafe(32)` 生成，不进日志 / Git） | 随机串 |
| `BOCHA_API_KEY` | 博查 Web Search API Key（可选，AI 联网补全用；`open.bochaai.com` 申请，按次计费） | 博查 key |
| `API_KEY_KEK` | 用户 API Key 加密主密钥（可选，AES-256-GCM；32 字节 base64 串，丢失后已存 key 无法解密） | base64 串 |

> `.env` 已加入 `.gitignore`，请勿提交真实凭据；模板见 `.env.example`。**生产部署另有一套密钥**，见 `deploy/.env.example`（含 MySQL/PG/Redis 密码、演示账号模型 Key 注入变量、`COOKIE_SECURE`）。

---

## 后端 API

### 账号与健康

| 接口 | 方法 | 说明 |
|------|------|------|
| `/auth/captcha` | GET | 下发图形验证码 `{captcha_token, image_base64}`。自研无状态签名方案（HMAC-SHA256 + 随机 salt，120s 有效，答案不出后端、不写库、不依赖 Redis） |
| `/auth/register` | POST | 注册 `{user_email, username, password}`。密码须同时含字母与数字，长度在 `PW_MIN_LENGTH` ~ `PW_MAX_LENGTH`；bcrypt 哈希存储 |
| `/auth/login` | POST | 登录。验证码在**任何数据库操作之前**校验（契约 §2.2「顺序即安全边界」）；通过后校验密码、下发 Cookie 会话（`user_sessions` 存 token 哈希） |
| `/auth/me` | GET | 当前登录用户信息 |
| `/auth/logout` | POST | 登出（撤销会话、清 Cookie） |
| `/health` | GET | 健康检查（含 MySQL 探活，5s 超时） |

### 设置（用户模型供应商）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/setting/api-keys` | GET / POST | 列出（脱敏，仅 `key_suffix`）/ 新增（AES-256-GCM 加密落库；新增即默认） |
| `/setting/api-keys/{id}` | PUT / DELETE | 更新 / 删除（删除默认 Key 不转移默认） |
| `/setting/api-keys/{id}/default` | PUT | 设为默认 Key |

### 购物车 / 物品库 / 消费记录

| 接口 | 方法 | 说明 |
|------|------|------|
| `/cart/items` | GET / POST | 购物车列表 / 新增（已确认参数档案） |
| `/cart/items/{id}/update` | PATCH | 更新条目 |
| `/cart/items/{id}/delete` | DELETE | 删除条目 |
| `/cart/items/{id}/transform` | POST | 标记已购，转入物品库（可附带购买信息） |
| `/cart/items/ai-draft` | POST | AI 联网补全草稿 `{name, category}`：只产草稿不入库，规格键名带 `(AI)` 后缀，价格仅回填搜索资料中明确出现的公开标价，确认后走 `POST /cart/items` |
| `/items` | GET / POST | 物品库列表 / 直接建档 |
| `/items/latest` | GET | 最近新增物品 |
| `/items/{id}` | PATCH / DELETE | 更新 / 删除 |
| `/groups` | GET / POST | 分组列表（带每组价格统计）/ 新建分组 |
| `/groups/{id}` | GET / PATCH / DELETE | 分组详情（已购买 / 未购买两区 + 统计）/ 重命名 / 删除（只删分组与成员关系，不动物品） |
| `/groups/{id}/items` | POST | 把物品加入分组：`{item_type: "cart"｜"owned", item_id}` |
| `/groups/{id}/items/{item_type}/{item_id}` | DELETE | 移出分组 |
| `/purchase-records` | GET / POST | 消费记录列表（上限 200 条）/ 新增（价格 = 用户自记，不承诺实时价） |
| `/purchase-records/{id}` | PUT / DELETE | 更新 / 删除 |
| `/purchase-records/link-preview` | POST | 按商品链接抓取页面，生成待确认草稿（不入库；域名白名单防 SSRF，绝不回填价格） |

### 对话与图片

| 接口 | 方法 | 说明 |
|------|------|------|
| `/chat/message` | POST | 发送对话消息：`conversation_id` 懒创建（首条传 `null`，返回真实 id）+ `text` + `item_refs`（购物车/物品库商品引用，按登录用户反查展开，查不到即 40001）；user 消息先落库再调模型，失败也留痕 |
| `/conversations` | GET | 当前用户的会话列表（按最近更新排序，`limit` 1~100 默认 50） |
| `/conversations/{id}/messages` | GET | 会话历史消息（按时间正序，`limit` 1~500 默认 200；越权会话统一报「会话不存在」） |
| `/conversations/{id}/title` | PATCH | 修改会话标题（归属校验：必须同时匹配 id 与 user_id） |
| `/upload/image` | POST | 上传商品展示图（分块读 + 2MB 硬上限，每用户 60s 10 次限流；落盘即登记 `image` 表） |
| `/uploads/{name}` | GET | 图片访问唯一出口（登录 + 归属鉴权；未登记 / 非本人 / 文件不存在统一返回「图片不存在」） |

> Swagger / ReDoc 文档：`/docs`、`/redoc`（静态资源自托管于 `static/`）。

---

## 生产部署（Docker Compose）

完整部署指南见 **`deploy/README.md`**（服务器准备 / 密钥配置 / 启动验证 / HTTPS / 备份恢复 / 2C2G 小内存要点），这里给速览：

```bash
# 1. 服务器准备：装 Docker + Compose v2，放行 80/tcp
# 2. 代码上服务器
cd ~/app && git clone <仓库地址> price-agent && cd price-agent/deploy
# 3. 配置生产密钥（模板复制后逐项填真实值，必填项缺失 compose 启动即报错）
cp .env.example .env
# 4. 启动（backend 容器首次启动自动 alembic 迁移，PG 首次建库自动跑 pg_init.sql）
docker compose up -d --build
docker compose ps          # 7 个容器全部 Up / healthy 即正常
# 5. 灌演示数据（幂等，可重复执行；重复执行只 [skip]）
docker exec -w /app pa-backend python scripts/seed_demo.py
# 6. 验证
curl -s http://127.0.0.1/health      # {"code":0,...,"status":"ok"}
# 浏览器打开 http://<服务器IP>/price-agent/，用 demo 账号登录
```

**2C2G 小内存服务器注意**（本项目的实际部署环境）：

1. **加 swap（必做）**：2G 物理内存下不加 swap 会被 OOM 杀进程
2. **容器已限内存**：compose 内每个服务都设了 `mem_limit`（合计上限 ≈1.6GB，是上限不是预占）
3. **前端构建是最大瓶颈**：`vite build` 在 2G 机器上极慢（可能 10 分钟+）且并行构建会压爆内存。**务必串行构建**（`docker compose build backend` 和 `build frontend` 分开跑），构建期间可临时 `docker compose stop worker reaper postgres redis` 释放内存；若反复失败，改本地构建镜像后 `docker save` / 服务器 `docker load`
4. 磁盘建议 ≥20GB；别在这台机器上再跑其他重服务；监控内存用 `docker stats`

**日常更新**：

```bash
cd ~/app/price-agent && git pull
cd deploy && docker compose up -d --build
```

> 改了 `app/models/` 后：backend 容器重启时自动 `alembic upgrade head`，但**新迁移文件必须随代码一起上服务器**（先本地生成迁移并提交，再 git pull）。

**备份与恢复**：数据都在命名卷（`mysql_data` / `pg_data` / `redis_data` / `uploads_data`），备份 = 卷导出（mysqldump / pg_dump / tar），命令见 `deploy/README.md` §8。

---

## 项目文档

| 文档 | 说明 |
|------|------|
| `deploy/README.md` | 生产部署指南（服务器准备 / 密钥 / 启动 / HTTPS / 备份 / 2C2G 要点 / 演示账号） |
| `docs/用户注册与登录-接口契约.md` | 注册登录接口契约（含验证码 §2.5、错误码） |
| `docs/登录人机验证与登录态-设计.md` | 人机验证与登录态设计 |
| `docs/第三方API-Key加密存储.md` | 用户 API Key 加密、模型选择、咨询调用与轮换操作 |
| `docs/AI联网补全-接口契约.md` | AI 联网补全契约（博查通道、`ai-draft` 草稿形态、来源标记、价格回填口径） |
| `docs/图片上传服务-接口契约.md` | 图片上传契约（两阶段加固、归属模型、访问收口、生命周期清理） |
| `docs/启动命令.md` | 日常开发命令速查（后端 / 前端 / 迁移 / 测试 / 常见问题） |
| `docs/M0-基座-trace_id中间件与健康检查-设计.md` | M0 基座（trace_id、健康检查）设计 |
| `docs/代码审查-异步连接与Session规范.md` | 异步连接与 Session 规范审查 |
| `docs/注册登录-实现指引.md` | 注册登录实现指引（施工手册：按什么顺序动手、每步为什么） |
| `docs/架构契约审查-待商定.md` | 组件启用时机与数据归属（Redis 分阶段、双库边界、缓存语义） |
| `docs/参考-Yuxi存储层搭配与可借鉴清单.md` | 参考项目 `F:\Yuxi` 存储层调研 |
| `docs/Agent编号约定.md` | 多智能体编号约定（A1–A6）与编排图说明 |

---

## 当前进度

| 里程碑 / 模块 | 状态 |
|--------|------|
| M0 开发基座 | ✅ 骨架、配置、trace_id、`/health`、统一错误处理、日志、注册登录、图形验证码、Cookie 会话鉴权、限流均已落地 |
| M4 前端联调 | ✅ 账号、API Key 设置、购物车、物品库、消费记录、购物分组、图片上传、AI 补全、流式对话（含 agent 过程提示）均已接后端；Mock 演示页已清除 |
| 消费记录与画像 | ✅ 消费记录已落地（`purchase_record` + 链接采集草稿 + 对话上下文）；`user_profile` 表已建，A6 画像每轮对话后异步更新 |
| **M1 多 Agent（LangGraph）** | 🟢 **A1 编排图已落地**（`app/agents/a1_graph.py`，5 节点）：`decide` 自主路由到 `search`（RAG 检索）/ `compare`（A4 参数对比）/ `recommend`（A5 画像推荐，走博查联网）/ `card`（商品卡片）。详见 `docs/Agent编号约定.md` §4 |
| **M3 数据与 RAG** | 🟢 **已落地**（PostgreSQL 16 + pgvector、Redis）：向量索引链路（arq worker + reaper 补偿）+ 语义检索（按用户问题选维度、分维度对比） |
| M5 真实联盟 API | ✅ 已按 v0.8 拍板删除价格情报线（不做联盟 API 比价；价格 = 用户自记 + AI 网络参考价） |
| **生产部署上线** | ✅ Docker Compose 七容器部署于阿里云 2C2G（公网 http://47.93.117.76/price-agent/）；演示账号 + 40 张商品图 + 模型 Key 注入已就位 |
| M6 安全合规加固 / M7 上线 | ⬜ 未开始 |

### 已知问题与取舍（2026-10-19 真机联调后）

| 项 | 说明 |
|---|---|
| 对比耗时 18 秒 | 博查 1.1s + 取参 7.5s + 维度对比 9.5s。**大宋拍板接受**，靠 agent 过程提示兜住体验 |
| 商品卡片已停用 | `web_search` 返回的是**网页**不是商品，同一商品的多个页面被渲染成多张卡片。取数问题另修（`search_filter`），卡片代码保留，`can_card = False` 一行可恢复 |
| A5 日限次未做 | 大宋拍板暂不做。⚠️ **上多 worker 前必须补**（`rate_limit` 是进程内的，多 worker 会稀释 N倍） |
| `rag_min_score` 是初值 | 0.4 是语料只有 1 条时定的，等向量灌满后重新校准 |
| 2C2G 构建慢 | `vite build` 在 2G 内存下极慢，前端镜像**必须串行构建**（见「生产部署」注意点 3） |

---

## 合规说明

- **零交易动作**：不代下单、不代支付，交易 100% 由用户完成
- **不提供 CPS 推广链接**：只做商品参数聚合与领券指引，与推广解耦
- **价格透明**：消费记录价格由用户自记自确认；AI 联网补全回填的是搜索资料中明确出现的公开标价，前端固定提示「网络参考价，可能过时，以商品页实际价格为准」且用户可改
- **补全来源标记**：AI 联网补全的规格键带 `(AI)` 后缀与「来源：网络」徽标，结果必须用户确认后生效
- **链接抓取白名单**：服务端按链接抓页面只出草稿、绝不回填价格，域名白名单防 SSRF
- **千人千面权益不承诺**：天降红包、限时折扣等账号维度权益只做指引，注明「以页面实时价为准」
- 价格与券信息以平台页面实时展示为准
