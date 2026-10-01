# 第三方 API Key 加密存储

本模块用于存储用户提供、后端需要再次调用的第三方 API Key。自签发的访问凭证仍应只存哈希。设置页通过服务端 Session Cookie 确认当前用户；内部调用方也必须先验证用户身份，再传入 `user_id`。

## 配置与迁移

在服务进程的环境变量或未入库的 `.env` 中配置：

```dotenv
API_KEY_KEKS='{"v1":"<32-byte-random-KEK-in-Base64>"}'
API_KEY_ACTIVE_KEK_VERSION=v1
COOKIE_SECURE=false
```

每个版本的 KEK 是独立的 32 字节随机值，经 Base64 编码后放入 JSON 对象。可在受控主机上用 `python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"` 生成。不要将值写入 Git、命令行参数、日志或数据库。生产环境应限制进程及主机访问权限，测试环境须使用不同密钥，并将 `COOKIE_SECURE` 设为 `true`、通过 HTTPS 同源部署前后端。未配置 KEK 时原有注册登录可启动，但 Key 设置接口会返回通用内部错误。

仅在本机开发环境、`.env` 已存在且两项 KEK 配置都未设置时，可以运行 `python -m scripts.init_local_kek`。命令生成随机 KEK，追加到被 Git 忽略的 `.env`，不输出密钥值；完成后重启后端。不要在已有加密数据的环境删除或替换旧 KEK，应按下文轮换流程处理，并备份生产 KEK。

首次使用前，在各自的 `price_agent` 数据库执行 `alembic upgrade head`，再确认 `alembic current` 与唯一的 `alembic heads` 一致。新迁移建立 `user_key_envelopes` 和 `user_api_keys` 两张表，不写入任何用户数据。库内只保存 Base64 编码的 AES-256-GCM 密文、独立随机 nonce、认证标签和密钥版本。数据库备份也要加密；TDE 不替代应用层加密。

设置页还需要 `user_sessions` 表。登录成功后浏览器获得 HttpOnly、SameSite=Lax 的会话 Cookie；数据库只保存 token 的 SHA-256。`GET /auth/me` 恢复当前用户，`POST /auth/logout` 撤销会话。会话有效期 7 天，剩余不足 3 天时续期。前端不再以本地邮箱标记判断登录状态。开发期 Vite 同时代理 `/auth` 和 `/settings`；GitHub Pages 上的纯静态部署不能直接提供同源后端，正式上线须配合同源后端入口。

## 设置接口

| 请求 | 用途 |
|---|---|
| `GET /settings/api-keys` | 只返回当前用户的服务商、`****` 加后四位、已选模型名、状态与时间 |
| `PUT /settings/api-keys/{provider}` | 提交 `{ "api_key": "…" }`，新增或替换当前用户的 Key |
| `DELETE /settings/api-keys/{provider}` | 删除当前用户对应服务商的 Key |
| `GET /settings/model` | 当前服务商、生效模型名，以及四个服务商的默认模型与各自已记住的模型 |
| `PUT /settings/model` | 提交 `{ "provider": "…", "model_name": "…" }`，同时设定服务商与该服务商的模型；不传 `model_name` 即清空该厂商的选择，回落默认 |
| `GET /settings/models/{provider}` | 用该用户此服务商的 Key 向厂商拉一次模型列表 |

三处写入接口与这条列表读取都要求 `X-Requested-With: price-agent`（`GET /settings/models/{provider}` 会解密用户 Key，因而按写操作同等对待）。所有接口都依赖有效 Session Cookie。所有者 ID 来自会话，不接收客户端提供的用户 ID。响应使用现有 `{code,msg,data}` 信封，不返回完整 Key。设置页可查看账号、保存/替换/移除 Key 与退出登录；当前没有第三方连接测试能力，状态仅表示本地保存情况。

## 使用用户自己的模型 API

保存 Key 后，在设置页“咨询使用的模型”选择服务商与模型。服务商存于 `users.model_provider`，模型名存于对应的 `user_api_keys.model_name`，因此每个服务商各记一个，切走再切回仍然保留；删除正在使用的 Key 会连同该服务商的模型选择一起删除（Key 被判 `invalid` 不会清除模型选择）。模型名可留空，留空即使用服务商默认：OpenAI (`gpt-4o-mini`)、Anthropic (`claude-haiku-4-5`)、DeepSeek (`deepseek-chat`)、通义千问 (`qwen-plus`)。可选模型列表由 `GET /settings/models/{provider}` 用该用户自己的 Key 向厂商官方 `models` 端点实时拉取，不缓存；Anthropic 只取一页（`limit=100`，忽略游标），列表里会按命名剔除明显不能对话的模型（embedding、音频、图像、审核等），这是 best-effort——后端不会拿这份列表校验用户保存的模型名，填错的代价是调用时失败。其他服务商的 Key 仍可加密保存，但端点白名单只认上述四家，不能选为咨询模型。

浏览器向 `POST /chat/message` 提交最近最多 12 条文本消息；后端根据 Session 确认用户，只解密该用户选定服务商的 Key，在固定官方 HTTPS 端点调用模型，并只将回复文本与实际使用的模型名返回浏览器。浏览器从不接收 Key。服务商返回 401/403 时，后端用调用前的修订标识将该 Key 标为 `invalid`；替换 Key 后可重新选择。两条模型调用（对话与模型列表）都以 `follow_redirects=False` 发出，3xx 一律视为失败，不会跟随重定向。没有选择、Key 缺失或配置错误时明确报错，不回退到前端 Mock 回复，也没有任何服务端全局模型 Key 可作兜底。聊天目前仅支持文本，图片、商品搜索、实时价格、库存和优惠券接口尚未接入；模型系统提示禁止声称已查询这些数据。

新增迁移 `e4a6b8c0d2f1` 为 `users` 增加可空的默认服务商字段；`a1c9f4e7b208` 为 `user_api_keys` 增加可空的 `model_name`。后者可空且无 `server_default`，存量行全部为 NULL（含义是“未选择，使用服务商默认”），对已有数据是纯 no-op。部署时先执行 `alembic upgrade head`，再重启后端。必须先配置本页上方的 KEK 环境变量；用户自己的模型 Key 不能代替服务端 KEK。正式部署还需让 `/auth`、`/settings`、`/chat` 与前端保持同源。

## 内部调用

```python
from app.core.api_key_crypto import KeyRing
from app.core.config import settings
from app.database.session import async_session_local
from app.services.api_key_service import ApiKeyService

service = ApiKeyService(async_session_local, KeyRing.from_settings(settings))
await service.save_key(authenticated_user_id, "openai", user_supplied_key, actor=f"user:{authenticated_user_id}")
metadata = await service.list_key_metadata(authenticated_user_id, actor=f"user:{authenticated_user_id}")

async with service.key_for_call(authenticated_user_id, "openai", actor="service:model") as borrowed:
    # Only the third-party call site should turn the buffer into a header string.
    authorization = "Bearer " + borrowed.value.decode("utf-8")
    # Call the provider here; do not retain or log authorization.
    await call_provider(authorization)
```

`key_for_call` 返回可清零的 `bytearray`、修订标识，以及同一行上的 `model_name`。模型名是明文列：它不是凭据，用户在设置页要能看见，加密它只会把它拖进 DEK 轮换与 AAD 绑定而毫无收益——本模块“不存明文机密”的规则不适用于它，改动时不要顺手加密。上下文退出时缓冲区被覆盖；Python 的字符串和加密库内部副本无法保证彻底擦除，因而应尽量缩短其生存期。不要把明文放进 Redis、ORM、审计日志或返回前端。`list_key_metadata` 仅返回服务商、`****` 加后四位、已选模型名、状态及时间。`key_for_call(..., purpose=...)` 决定审计日志里的用途字段（`model_call` 或 `model_list`），别让它对新用途说谎。

服务商标识统一小写，每用户每服务商最多一条记录。重复保存会替换旧 Key、产生新修订标识并恢复 `active`。厂商报告凭证失效时，用借用时取得的修订标识调用 `mark_invalid`，避免旧请求把刚换的新 Key 标为失效。`active` 只表示本地允许取用，不代表厂商已验证。

调用审计使用现有带 trace ID 的应用日志，只记录操作者、用户、服务商、动作、结果和版本或固定用途。运行环境必须收集并保护这些日志。解密失败只抛出通用错误，不返回 nonce、tag 或密钥配置细节。

## 轮换

添加新 KEK 版本到 `API_KEY_KEKS`，把 `API_KEY_ACTIVE_KEK_VERSION` 切到新版本，部署后执行：

```bash
python -m scripts.rotate_api_keys kek
python -m scripts.rotate_api_keys dek --user-id 123
```

KEK 命令按用户事务重包装 DEK，可重复运行；输出尚未采用目标版本的用户数量。完成后还需检查数据库备份是否需要旧 KEK，确认不再需要时才移除旧版本。DEK 命令在一个事务中重加密指定用户所有 Key，包括 `invalid` 记录；失败自动回滚。进程需要同时持有读取旧版本和写入新版本的 KEK，不能先删除旧版本。命令行只传版本名和用户 ID，绝不传密钥值。轮换期间的新保存操作使用活动 KEK 版本。

## 验证

`python -m unittest discover -s tests -p test_api_key_crypto.py -v` 验证密码学边界。迁移后的可清理本机 MySQL 上设置 `RUN_MYSQL_KEY_TESTS=1`，再运行 `pytest tests/test_api_key_service.py -v`；测试会创建并删除自己的随机用户及会话。覆盖首次并发写入、保存与轮换并发、失效状态、解密、篡改、事务回滚和设置接口的登录隔离。前端运行 `npm run build`。执行前确认该库允许创建和删除测试用户。

2026-09-29 本机验证：加密、KEK 初始化和 MySQL/HTTP 集成测试共 12 项通过，含用户密钥隔离和两种上游协议的模拟响应；`npm run build` 通过；`alembic current` 与唯一的 `alembic heads` 均为 `e4a6b8c0d2f1`。未向真实模型服务商发起收费请求。本机开发 `.env` 已通过初始化命令生成 KEK 并重启服务；生产环境仍需独立生成、保管和备份密钥。
