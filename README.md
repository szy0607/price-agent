# 智能电商采购 Agent（智能导购 Agent）

个人定制购物助手：通过对话理解用户需求（预算、平台偏好、学生身份、性价比 / 品质取向），聚合淘宝 / 京东 / 拼多多三平台价格与优惠，输出比价、领券口令与购买建议。**AI 是顾问，不是代购——下单与支付 100% 由用户自己完成。**

## 在线访问

网页版已部署于 GitHub Pages：https://szy0607.github.io/price-agent/

## 功能特性

| 模块 | 说明 |
|------|------|
| 智能咨询 `/chat` | 粘贴商品链接 / 上传商品图片 / 直接提问，输出 Agent 协作过程 → 情报卡 → 对比摘要 → 推荐结论 → 复制口令；支持「无目标商品」场景：只提需求（如"3000 元以内降噪耳机"）即可获得跨平台 Top N 推荐 |
| 款式对比 `/compare` | 双价矩阵（公开价 A / 领券价 B）+ 规格表 + 券明细 + 对比结论，支持淘宝 / 京东 / 拼多多三平台 tab 切换 |
| 领券指引 `/coupon` | 券类型、分平台领券步骤、权益矩阵、复制口令跳转 App |
| 用户画像 | 从对话中解析预算 / 平台偏好 / 学生身份 / 价格敏感度 / 会员身份（PLUS、88VIP），本地持久化并生成个性化推荐附注 |
| 账号系统（后端） | 注册 / 登录接口，bcrypt 密码哈希，用户数据落库 MySQL |

## 项目结构

```text
price-agent/
├── frontend-web/               # 网页版前端（Vue 3 + Vite + Tailwind 4，GitHub Pages 部署目标）
├── frontend/                   # 移动版 Demo（Vue 3 + Vant 4，参考工程）
├── app/                        # 后端（FastAPI + 异步 SQLAlchemy）
│   ├── core/                   # 配置（.env）、安全（bcrypt）、错误处理、中间件、trace
│   ├── database/               # 异步数据库会话与模型基类
│   ├── models/                 # ORM 模型（User）
│   ├── repository/             # 数据访问层（auth_repo）
│   ├── router/                 # 路由定义（log_in：/auth 注册登录）
│   ├── schemas/                # Pydantic 请求模型（注册 / 登录）
│   ├── dependence.py           # 依赖注入（数据库会话）
│   └── main.py                 # FastAPI 应用入口
├── alembic/                    # 数据库迁移（versions/ 含 users 表迁移）
├── docs/                       # 接口契约与设计文档（登录契约、trace_id 基座等）
├── .github/workflows/deploy.yml # GitHub Pages 自动部署
├── 智能电商采购Agent-设计方案.md  # 设计方案（v0.5）
├── 开发流程.md                   # 开发流程与合规红线（v1.0）
├── requirements.txt             # 后端运行依赖
└── requirements-dev.txt         # 后端开发 / 测试依赖
```

## 技术栈

| 模块 | 技术栈 |
|------|--------|
| 网页版前端 | Vue 3.5 + Vite 5 + Tailwind 4 + Phosphor Icons + Vue Router 4 |
| 移动版 Demo | Vue 3 + Vite 5 + Vant 4 |
| 后端 | Python 3.10 + FastAPI + 异步 SQLAlchemy 2.0 + Pydantic v2 |
| 数据库 | MySQL 8（业务库）+ Redis（缓存 / 验证码） |
| 迁移 | Alembic（异步） |
| 部署 | GitHub Actions → GitHub Pages |

## 本地开发

### 网页版前端（frontend-web）

```bash
cd frontend-web
npm install
npm run dev      # 开发服务器 http://localhost:5174/price-agent/
npm run build    # 构建产物 dist/
```

> 开发服务器已配置代理：`/auth` 前缀请求转发到本地后端 `http://127.0.0.1:8000`，便于前后端联调。

### 后端服务（app）

后端运行环境为 conda 环境 `fast`（Python 3.10），在项目根目录执行：

```bash
conda activate fast
pip install -r requirements-dev.txt   # 开发（含测试依赖）
alembic upgrade head                   # 执行数据库迁移
uvicorn app.main:app --reload          # 启动 http://127.0.0.1:8000
```

### 移动版 Demo（frontend，可选）

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # 产物 dist/
```

## 环境变量（.env）

后端通过根目录 `.env` 读取配置（见 `app/core/config.py`）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `DB_URL` | 异步 MySQL 连接串 | `mysql+aiomysql://user:password@127.0.0.1:3306/price_agent?charset=utf8mb4` |
| `PW_MIN_LENGTH` | 密码最小长度 | `8` |
| `PW_MAX_LENGTH` | 密码最大长度 | `64` |

> `.env` 已加入 `.gitignore`，请勿提交真实凭据。

## 后端 API

| 接口 | 方法 | 请求体 | 说明 |
|------|------|--------|------|
| `/auth/register` | POST | `{user_email, username, password}` | 注册。密码须同时包含字母与数字，长度在 `PW_MIN_LENGTH` ~ `PW_MAX_LENGTH` 之间；bcrypt 哈希存储 |
| `/auth/login` | POST | `{user_email, password}` | 登录，校验密码并更新最近登录时间 |

## 部署

推送到 `main` 分支后，GitHub Actions（`.github/workflows/deploy.yml`）自动构建 `frontend-web` 并部署到 GitHub Pages：

- Node 20 + `npm ci`（禁用 npm 缓存，规避 EINTEGRITY）
- SPA 兜底：构建产物中复制 `index.html` 为 `404.html`，保证 history 路由刷新 / 直达子路由可用
- 首次启用需在仓库 Settings → Pages → Source 选择 "GitHub Actions"

## 项目文档

| 文档 | 说明 |
|------|------|
| `智能电商采购Agent-设计方案.md` | 设计方案底稿（v0.5）：多 Agent 架构、统一适配层、双价策略、合规红线 |
| `开发流程.md` | 开发流程规范（v1.0）：里程碑、数据契约、git 规范、合规自查清单 |
| `docs/用户注册与登录-接口契约.md` | 注册登录接口契约 |
| `docs/登录人机验证与登录态-设计.md` | 人机验证与登录态设计 |
| `docs/M0-基座-trace_id中间件与健康检查-设计.md` | M0 基座（trace_id、健康检查）设计 |
| `docs/代码审查-异步连接与Session规范.md` | 异步连接与 Session 规范审查 |
| `docs/注册登录-实现指引.md` | 注册登录实现指引 |

## 当前进度与路线图

| 里程碑 | 目标 | 状态 |
|--------|------|------|
| M0 开发基座 | 后端骨架、配置 / trace_id / CI | 🔵 进行中（已完成后端骨架与注册登录模块） |
| M1 后端核心链路 | FastAPI + LangGraph 五 Agent + Mock | ⬜ 未开始 |
| M2 契约与画像 | JSON Schema 契约 + A0 画像 Agent | ⬜ 未开始 |
| M3 数据与 RAG | MySQL + Milvus + Redis 缓存 | ⬜ 未开始（业务库与迁移已就绪） |
| M4 前端联调 | frontend-web 接后端 | ⬜ 未开始（已配 `/auth` 代理） |
| M5 真实联盟 API | 多多进宝 → 淘宝 → 京东 | ⬜ 未开始（当前 Mock） |
| M6 安全合规加固 | 沙箱、限流、隐私 | ⬜ 未开始 |
| M7 上线 | 部署、监控、验收 | ⬜ 未开始 |

## 合规说明

- **零交易动作**：不代下单、不代支付，交易 100% 由用户完成
- **不提供 CPS 推广链接**：只做查券信息聚合与领券指引，与推广解耦
- **双价透明**：渠道专享券同时展示「能领 / 领不到」两个价格，不误导
- **千人千面权益不承诺**：天降红包、限时折扣等账号维度权益只做指引，注明「以页面实时价为准」
- **官方数据源**：信息一律走官方联盟查券 API 查询，不使用评论区数据
- 价格与券信息以平台页面实时展示为准
