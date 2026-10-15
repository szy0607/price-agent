# 智能导购 Agent（购物决策助手）

个人定制购物助手：通过对话理解用户需求（预算、平台偏好、学生身份、性价比 / 品质取向），维护个人购物车与物品库参数档案，AI 联网补全商品参数，并记录个人消费流水。**AI 是顾问，不是代购——下单与支付 100% 由用户自己完成。**

> 版本口径：设计方案 v0.8（2026-10-02 消费记录拍板）。价格情报线已按 v0.8 决策删除：不做联盟 API 比价、不承诺实时最低价；价格只来自用户自记与 AI 补全的网络参考价（带提示、可修改）。

## 在线访问

网页版已部署于 GitHub Pages：https://szy0607.github.io/price-agent/

> 在线版为纯前端演示：账号注册 / 登录 / 图形验证码、购物车 / 物品库 / 消费记录等业务功能均需搭配本地后端（`127.0.0.1:8000`）联调；业务页进入需先登录（登录态存于 Cookie，在线演示页暂存 localStorage）。

## 功能特性

| 模块 | 说明 | 状态 |
|------|------|------|
| 智能咨询 `/chat` | 多会话对话（懒创建 / 列表 / 历史 / 改标题）；右侧商品引用面板勾选购物车与物品库商品随消息发给模型；每轮结束后台异步跑 A6 画像；模型使用「设置」中的默认 API Key | ✅ 已落地 |
| 购物车 `/cart` | 已确认参数档案清单：增删改查、AI 联网补全草稿（`ai-draft`，不入库、确认后落库）、标记已购转入物品库 | ✅ 已落地 |
| 物品库 `/items` | 已购物品参数档案：增删改查；支持直接建档（不经过购物车，双入口） | ✅ 已落地 |
| 购物分组 `/groups` | 把购物车（未购买）和物品库（已购买）的物品归成一组：组内分已购买 / 未购买两区展示，统计各区与总计价格（无价格物品提示「未填价」不计入合计）；一个物品可进多个分组；删分组不动物品 | ✅ 已落地 |
| 消费记录 `/spending` | 用户自记消费流水：商品名 / 链接 / 平台 / 价格 / 规格；贴链接可抓取页面生成草稿（待用户确认后落库）；消费记录可勾选注入对话上下文 | ✅ 已落地 |
| 用户画像 | `user_profile` 表一行一用户（`preferences` 自由键值）；A6 画像 Agent 每轮对话结束后台异步提炼长期偏好（同会话近期对话 + 行为证据摘要，全量覆盖，防抖动三层）；chat 同步注入偏好与行为证据 | ✅ 已落地 |
| 账号系统（后端） | 注册 / 登录 + 图形验证码（人机验证）、bcrypt 密码哈希、Cookie 会话（`user_sessions`，token 哈希落库）、登出、`/auth/me` | ✅ 已落地 |
| 设置 `/settings` | 用户自定义模型供应商（`provider` / `base_url` / `model_name`）、默认 Key 管理；API Key 以 AES-256-GCM 加密存储、脱敏展示 | ✅ 已落地 |
| 图片上传 | 商品展示图上传（2MB 上限 + 限流）、访问统一收口鉴权（登录 + 归属校验）、生命周期自动清理（后台定时任务，幂等） | ✅ 已落地 |
| 心愿单 `/wishlist` | 占位路由（ComingSoonView，需登录） | ⬜ 规划 |

## 项目结构

```text
price-agent/
├── frontend-web/               # 网页版前端（Vue 3 + Vite + Tailwind 4，GitHub Pages 部署目标）
├── frontend/                   # 移动版 Demo（Vue 3 + Vant 4，参考工程）
├── app/                        # 后端（FastAPI + 异步 SQLAlchemy）
│   ├── core/                   # 配置（.env）、安全（bcrypt）、图形验证码、Cookie 会话、限流、日志、错误处理、中间件、trace、Key 加密、HTTP 客户端
│   ├── database/               # 异步数据库会话与模型基类
│   ├── models/                 # ORM 模型（users、user_sessions、cart_item、owned_item、item_group、item_group_ref、purchase_record、conversation、chat_message、user_profile、user_api_key、image）
│   ├── repository/             # 数据访问层（auth / cart / owned / group / conversation）
│   ├── router/                 # 路由（/auth、/health、/setting、/cart、/items、/groups、/purchase-records、/conversations、/upload、/uploads）
│   ├── schemas/                # Pydantic 请求 / 响应模型
│   ├── services/               # 业务服务（模型调用、AI 联网补全、联网搜索、图片存储、商品页抓取、API Key 管理）
│   ├── dependence.py           # 依赖注入（数据库会话、当前用户、同源写保护）
│   └── main.py                 # 应用入口（日志、统一异常、trace 中间件、lifespan 图片清理任务）
├── alembic/                    # 数据库迁移（versions/，17 个迁移文件）
├── docs/                       # 接口契约与设计文档
├── scripts/                    # 一次性脚本（seed_user13_data.py：开发测试数据，幂等）
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
└── .env.example                # 环境变量模板（复制为 .env）
```

## 技术栈

| 模块 | 技术栈 |
|------|--------|
| 网页版前端 | Vue 3.5 + Vite 5 + Tailwind 4 + Phosphor Icons + Vue Router 4 |
| 移动版 Demo | Vue 3 + Vite 5 + Vant 4 |
| 后端 | Python 3.10（conda `fast`）+ FastAPI + 异步 SQLAlchemy 2.0 + Pydantic v2 + bcrypt + Pillow（验证码） |
| 数据库 | MySQL 8（唯一事实源，库名 `price_agent`，UTC 时区口径）；PostgreSQL 16/pgvector、Redis 为 M3 规划 |
| 迁移 | Alembic（异步，时间默认值只用 `UTC_TIMESTAMP()`） |
| 密钥加密 | AES-256-GCM（`API_KEY_KEK` 主密钥） |
| AI 能力 | 用户自配 OpenAI 兼容供应商（`base_url` + `model_name`，取唯一默认 Key）；博查 Bocha Web Search API（联网补全） |
| 测试 | pytest + pytest-asyncio（后端）；`node --test`（前端） |
| 部署 | GitHub Actions → GitHub Pages |

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

> 开发服务器已配置代理，8 个前缀全部转发到本地后端 `http://127.0.0.1:8000`：`/auth` `/setting` `/chat` `/purchase-records` `/cart` `/items` `/groups` `/uploads`。后端必须起在 **8000** 端口，前端才通。

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

### 数据库迁移

改了 `app/models/` 之后：`alembic revision --autogenerate -m "英文短描述"` → 逐行读生成的迁移文件（autogenerate 盲区清单见 `AGENTS.md` §4）→ `alembic upgrade head`。完成判据：`alembic current` 与 `alembic heads` 打印同一个 revision id。**多人协作只同步表结构、不同步数据**，详见 `AGENTS.md`。

## 环境变量（.env）

后端通过根目录 `.env` 读取配置（见 `app/core/config.py`）。`DB_URL`、密码长度口径、`CAPTCHA_KEY` 为**必填**（缺失时应用 import 即报错）；其余为可选：

| 变量 | 说明 | 示例 |
|------|------|------|
| `DB_URL` | 异步 MySQL 连接串（**必填**） | `mysql+aiomysql://user:password@127.0.0.1:3306/price_agent?charset=utf8mb4` |
| `PW_MIN_LENGTH` / `PW_MAX_LENGTH` | 密码最小 / 最大长度（**必填**，两人口径需一致） | `6` / `18` |
| `CAPTCHA_KEY` | 图形验证码签名密钥，HMAC-SHA256（**必填**，`secrets.token_urlsafe(32)` 生成，不进日志 / Git） | 随机串 |
| `BOCHA_API_KEY` | 博查 Web Search API Key（可选，AI 联网补全用；`open.bochaai.com` 申请，按次计费） | 博查 key |
| `API_KEY_KEK` | 用户 API Key 加密主密钥（可选，AES-256-GCM；32 字节 base64 串，丢失后已存 key 无法解密） | base64 串 |

> `.env` 已加入 `.gitignore`，请勿提交真实凭据；模板见 `.env.example`。

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

## 部署

推送到 `main` 分支后，GitHub Actions（`.github/workflows/deploy.yml`）自动构建 `frontend-web` 并部署到 GitHub Pages：

- Node 20 + `npm ci`（禁用 npm 缓存，规避 EINTEGRITY）
- SPA 兜底：构建产物中复制 `index.html` 为 `404.html`，保证 history 路由刷新 / 直达子路由可用
- 首次启用需在仓库 Settings → Pages → Source 选择 "GitHub Actions"

## 项目文档

| 文档 | 说明 |
|------|------|
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

## 当前进度

| 里程碑 / 模块 | 状态 |
|--------|------|
| M0 开发基座 | ✅ 骨架、配置、trace_id、`/health`、统一错误处理、日志、注册登录、图形验证码、Cookie 会话鉴权、限流均已落地 |
| M4 前端联调 | 🔵 进行中（账号、API Key 设置、购物车、物品库、消费记录、图片上传、AI 补全、对话真会话已接后端；Mock 演示页已清除，`/compare`（等 A4）、`/coupon`（领券指引）待功能实现后重建） |
| 消费记录与画像 | 🔵 消费记录已落地（`purchase_record` + 链接抓取草稿 + 对话上下文）；`user_profile` 表已建，A6 画像 Agent 规划中 |
| M1 多 Agent（LangGraph） | ⬜ 未开始（当前为确定性管线：模型直调 + 联网补全；LangGraph 依赖未引入） |
| M3 数据与 RAG | ⬜ 未开始（PostgreSQL 16 + pgvector、Redis 规划中） |
| M5 真实联盟 API | ⬜ 已按 v0.8 拍板删除价格情报线（不做联盟 API 比价；价格 = 用户自记 + AI 网络参考价） |
| M6 安全合规加固 / M7 上线 | ⬜ 未开始 |

## 合规说明

- **零交易动作**：不代下单、不代支付，交易 100% 由用户完成
- **不提供 CPS 推广链接**：只做商品参数聚合与领券指引，与推广解耦
- **价格透明**：消费记录价格由用户自记自确认；AI 联网补全回填的是搜索资料中明确出现的公开标价，前端固定提示「网络参考价，可能过时，以商品页实际价格为准」且用户可改
- **补全来源标记**：AI 联网补全的规格键带 `(AI)` 后缀与「来源：网络」徽标，结果必须用户确认后生效
- **链接抓取白名单**：服务端按链接抓页面只出草稿、绝不回填价格，域名白名单防 SSRF
- **千人千面权益不承诺**：天降红包、限时折扣等账号维度权益只做指引，注明「以页面实时价为准」
- 价格与券信息以平台页面实时展示为准
