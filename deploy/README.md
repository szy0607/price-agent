# price-agent 服务器部署指南（Docker Compose）

> 适用：任意装有 Docker Engine + Compose v2 的 Linux 服务器（Ubuntu 22.04/24.04、Debian 12、CentOS Stream 9 均可）。
> 一次拉起 7 个容器：MySQL8 / PostgreSQL16+pgvector / Redis7 / FastAPI 后端 / arq worker / reaper / nginx。

---

## 1. 服务器准备（一次性）

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker

# 或 Docker 官方源（推荐，版本较新）
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
```

防火墙放行 `80/tcp`（HTTPS 时再放 `443/tcp`）：

```bash
sudo ufw allow 80/tcp
```

## 2. 把项目代码传到服务器

在服务器任意目录（示例 `~/app`）：

```bash
mkdir -p ~/app && cd ~/app
git clone https://github.com/szy0607/price-agent.git   # 或 scp/rsync 整包上传
cd price-agent
```

## 3. 配置生产密钥

```bash
cd deploy
cp .env.example .env
nano .env     # 逐项填真实值，必填项缺失会导致 compose 启动报错
```

需要从本地 `.env` 复用的值（**不要公开贴出来**）：

| 变量 | 来源 |
|---|---|
| `CAPTCHA_KEY` | 本地 `F:\price-agent\.env` 同名值，或重新生成 |
| `BOCHA_API_KEY` | 本地同名值（付费 key，按次计费） |
| `API_KEY_KEK` | 本地同名值（**必须复用**：库里已存的用户 key 用它加密，换掉就解不开） |

> 数据库/Redis 密码建议用新生成的强随机值：
> `openssl rand -base64 24`

## 4. 启动

```bash
cd ~/app/price-agent/deploy
docker compose up -d --build
docker compose ps          # 全部 healthy / Up 即正常
```

首次启动后端容器会先自动执行 `alembic upgrade head`（建全量表结构），
PostgreSQL 首次建库会自动执行 `scripts/pg_init.sql`（建 vector 扩展 + 副本表，幂等）。

## 5. 验证

```bash
# 后端健康检查（含 MySQL 探活）
curl -s http://127.0.0.1/health

# 前端
浏览器打开 http://<服务器IP>/price-agent/   （注册/登录/图形验证码都走通即 OK）

# 索引链路三个进程都在跑
docker compose ps    # backend / worker / reaper 都在

# 查看 RAG 索引状态（对话页右上角有提示；或直查库）
docker exec pa-mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" price_agent \
  -e "SELECT index_status, COUNT(*) FROM cart_item GROUP BY index_status;"
```

> 商品索引状态：`PENDING`=等索引（正常）、`SYNCED`=已入库、`RUNNING`=处理中、`FAILED`=失败。
> worker 或 PG 没起来时商品会一直卡 PENDING 且**不报错**——这是设计如此，先查 `docker compose ps`。

## 6. HTTPS（有域名时）

以 `your.domain.com` 为例（有公网 IP + 域名解析到该 IP）：

```bash
# 1. 装 certbot（或云厂商 DNS 面板直接申请免费证书）
sudo apt install -y certbot

# 2. 先停 nginx 容器，用 certbot standalone 拿证书
docker compose stop frontend
sudo certbot certonly --standalone -d your.domain.com
docker compose start frontend

# 3. 修改 docker-compose.yml：
#    - frontend 服务放开 443 端口映射与 certs 挂载（文件里已留注释位）
#    - deploy/.env 里 COOKIE_SECURE=true（Cookie 加 Secure 标记，必须 HTTPS 才能发）
# 4. 改 nginx.conf：listen 443 ssl + 证书路径 + 80 跳转 443
# 5. docker compose up -d --build
```

## 7. 日常更新

```bash
cd ~/app/price-agent && git pull
cd deploy && docker compose up -d --build
```

> 代码改到 `app/models/` 后：backend 容器重启时会自动 `alembic upgrade head`，
> 但新迁移文件必须随代码一起上服务器。改了模型后**先本地生成迁移文件并提交**，再 `git pull`。

## 8. 备份与恢复

数据都在命名卷里（`mysql_data` / `pg_data` / `redis_data` / `uploads_data`），备份 = 卷导出：

```bash
# MySQL（业务数据事实源，最重要）
docker exec pa-mysql sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --databases price_agent' > backup_mysql_$(date +%F).sql

# PG（向量副本，可幂等重建，非必须但顺手）
docker exec pa-postgres pg_dump -U postgres price_agent_pg > backup_pg_$(date +%F).sql

# 上传图片
docker run --rm -v price-agent_uploads_data:/data -v "$PWD":/backup alpine tar czf /backup/uploads_$(date +%F).tar.gz -C /data .
```

恢复：导入 SQL / 解包 tar 后 `docker compose up -d` 即可。

## 9. 已知取舍（沿用项目 README）

- 后端 `--workers 1`：限流与 A5 日限次是**进程内计数**，多 worker 会稀释配额。
- 前端固定挂在 `/price-agent/` 路径（与 GitHub Pages 行为一致）。
  想用根路径需另改 `vite.config.js` 的 base 并重写 nginx 的 SPA/API 分流，不建议。
- RAG 链路三进程缺一不可：Web / arq worker / reaper 都在本 compose 里，无需手工起。

## 10. 2C2G 小内存服务器部署要点

2 核 2G 能带动本项目（个人使用量级），但属于「刚好够用」，务必按下面做：

1. **加 swap（必做，防 OOM 杀进程）**：
   ```bash
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
2. **容器已限内存**：compose 里已为每个服务设置 `mem_limit`（mysql 384m / pg 256m / redis 128m / backend 384m / worker 256m / reaper 128m / nginx 64m，合计上限 ≈1.6GB）。
   注意 `mem_limit` 是**上限不是预占**，平时不会真用满。
3. **前端构建放本地或先确认 swap 已生效**：`npm run build`（rollup/esbuild）在 2G 机器上可能顶到内存上限。compose 里 `docker compose up -d --build` 首次构建 frontend 时，
   如果构建失败/被杀，先确认 swap 已生效（`free -h` 看 Swap 列），或改在本地构建镜像后 `docker save/load` 传到服务器。
4. **磁盘**：镜像 + 构建缓存 + 数据库数据，建议系统盘 ≥ 20GB（云厂商 2C2G 通常自带 40GB，够用）。
5. **别在这台机器上再跑其他重服务**（Java 后端、桌面环境等）；监控内存：`docker stats`。
6. 如果以后要开多 worker 或上真实并发，再升到 2C4G —— 目前单 worker + 个人使用完全够。

## 11. 演示账号（比赛 / 评委用）

部署完成后，执行一次幂等 seed 脚本，服务器上就有能直接登录的演示账号和完整演示数据：

```bash
docker exec -w /app pa-backend python scripts/seed_demo.py
```

> 脚本幂等：先查后插，重复执行只会打印 `[skip]`，不会产生重复数据或报错。
> 本地开发环境同样可跑：`python scripts/seed_demo.py`（conda fast，项目根）。
> 本仓库的 `deploy/.env` 已预填好模型 key 注入变量（见下），服务器上直接用即可。

| 账号 | 密码 | 预置数据 |
|---|---|---|
| `demo@example.com`（演示账号） | `Demo2026` | 购物车 20 条 + 物品库/消费记录 20 条 + 用户画像 + 默认模型 key |
| `demo2@example.com`（演示账号2） | `Demo2026` | 同上（独立数据，供两人同时演示） |

**模型 key 自动注入（开箱即用）**：`deploy/.env` 里已填好下面两组变量，
seed 执行时会自动给两个演示账号写入【默认】对话模型 key 与向量模型 key（加密落库），
评委登录即可直接聊天 / AI 补全 / RAG 检索，无需进设置页：

```env
DEMO_MODEL_PROVIDER / DEMO_MODEL_BASE_URL / DEMO_MODEL_NAME / DEMO_MODEL_KEY      # 对话模型（复用本地 deepseek-flash）
DEMO_EMBEDDING_PROVIDER / DEMO_EMBEDDING_BASE_URL / DEMO_EMBEDDING_NAME / DEMO_EMBEDDING_KEY  # 向量模型（复用本地千问）
```

> 每组四个变量【全部】填写才生效，缺任一整组跳过（宁缺毋滥，避免写半截配置）。
> 不想要自动注入时，把对应变量删掉即可，改为登录后设置页手动配置。

**比赛演示前检查**（其余依赖）：
1. 三个进程都在跑：`docker compose ps`（backend / worker / reaper）
2. 登录任一演示账号 → 聊天页发一条消息验证模型连通（key 无效会被标记失效，需在设置页重配）

清掉演示账号重来（可选）：先删该用户关联数据再删用户，然后重跑 seed：
```bash
docker exec -w /app pa-backend python -c "
import asyncio
from sqlalchemy import delete, select
from app.database.session import async_session_local
from app.models import CartItem, OwnedItem, PurchaseRecord, UserProfile, User
async def m():
    async with async_session_local() as s:
        for em in ('demo@example.com', 'demo2@example.com'):
            u = (await s.execute(select(User).where(User.user_email == em))).scalar_one_or_none()
            if not u:
                continue
            for M in (CartItem, OwnedItem, PurchaseRecord, UserProfile):
                await s.execute(delete(M).where(M.user_id == u.id))
            await s.execute(delete(User).where(User.id == u.id))
        await s.commit()
asyncio.run(m())
"
```
