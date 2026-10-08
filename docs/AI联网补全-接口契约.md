# AI 联网补全 · 接口契约

> ⚠️ **权威顺序提示（同 AGENTS.md §0）**：本契约是 2026-10-05/06 已拍板决策的**固化**，不是需求来源。
> 权威 = 大宋当次指令 > 已拍板决策 > 本文档正文。实现与本文档冲突时，先报差异，不按文档"补实现"。

## 0. 决策依据（已拍板，2026-10-05 / 10-06 修正）

| # | 决策 | 内容 |
|---|---|---|
| 1 | 搜索通道 | 博查 Bocha Web Search API（`https://api.bocha.cn/v1/web-search`），**项目级 key 放 `.env`**，成本归项目方 |
| 2 | 模型档位 | 轻量档 = **用户已配 key 那家的默认小模型**（即 `MODEL_PROVIDERS` 各家默认值）；补全调用**不读用户保存的 `model_name`**，强制默认档。**不做自动兜底**——失败即报错，用户手填参数（10-06 拍板：不绑死 qwen） |
| 3 | 来源标记 | specs **键名带 `(AI)` 后缀**（提示词层面解决，零迁移，入库自然保留；前端按后缀渲染「来源：网络」徽标） |
| 4 | 接口形态 | 独立草稿端点 `POST /cart/items/ai-draft`，**只产草稿不入库**；用户确认后走现有 `POST /cart/items`（现有 CRUD 零改动） |
| 5 | 封装层级（10-06） | 只封装成 **services 层独立模块**，不做 LangGraph tool 封装——补全是确定性管线，没有「模型自主决定是否搜索」的决策点；将来 A2′ 上 LangGraph 时把底层函数包 `@tool` 即可 |
| 6 | price 参与（**10-07 大宋拍板，推翻决策 #31③**） | `price` 可以回填：模型只能输出搜索资料里**明确出现的公开标价**（单个数字），没有就 `null`，禁止估算；前端回填后在价格输入框旁**固定提示**「网络参考价，可能过时，以商品页实际价格为准；如有更低价请自行修改」——风险由「提示 + 用户可改」缓解，与 chat 红线句同一精神 |
| 7 | 供应商收缩（**10-07 大宋拍板**） | `MODEL_PROVIDERS` 只保留 **deepseek + qwen** 两家（均为 OpenAI 兼容协议），openai / anthropic 不做。收益：鉴权头只剩 Bearer、请求体只剩一种 shape、补全调用无需厂商分支。将来要加回 = 字典加一条 + （非 OpenAI 兼容时）补对应分支 |

## 1. 接口定义

### `POST /cart/items/ai-draft`

- 鉴权：同现有 cart 路由（`CurrentUser`）；写保护依赖跟随现状（`require_same_origin_write`）
- router **零 SQL、零 LLM 逻辑**，只做参数校验 + 调 service（决策 #33 口径）

**请求体**

```json
{ "name": "Sony WH-1000XM6", "category": "耳机" }
```

| 字段 | 类型 | 必填 | 校验 |
|---|---|---|---|
| `name` | string | ✅ | 去空格后非空；超长沿用 `CartItem.name` 的 256 上限口径 |
| `category` | string | ❌ | 可空；拼搜索 query 用，缺省不拼 |

**响应**（`code=0`）

```json
{
  "code": 0, "msg": "ok",
  "data": {
    "name": "索尼 WH-1000XM6 无线降噪耳机",
    "category": "耳机",
    "price": 2999.0,
    "specs": {
      "续航(AI)": "约 30 小时（开降噪）",
      "驱动单元(AI)": "30mm"
    },
    "model": "deepseek-chat",
    "sources": ["https://...", "https://..."]
  }
}
```

- `name` / `category` / `price` / `specs` **直接回填添加表单的对应输入框**（2026-10-07 大宋拍板）：前端不另开面板，用户在表单里自行核对、修改，点「添加」才走现有 `POST /cart/items` 入库——AI 结果在用户确认前不碰数据库
- `specs`：键名**必须**带 `(AI)` 后缀（模型输出层面保证，见 §3 prompt）；value 为提取到的参数值
- `name`：规范化后的商品全名（AI 判断）；用户没让它改名字就不用——回填只是预填，决定权在用户
- `category`：从资料判断的分类；资料支撑不了就返回 `null`，前端留空
- `price`：**公开参考价**（决策 #6，10-07 拍板）。只在搜索资料明确出现时输出，无则 `null`；前端回填 + 价格输入框旁固定提示「网络参考价，可能过时，以商品页实际价格为准；如有更低价请自行修改」。`note` 不补（私人备注）；`image` 不补（博查标准 web-search 返回无图片 URL，探针实测确认，真要补将来另开通道）
- `model`：实际用的模型名（排查用）
- `sources`：本次搜索命中的网页 URL（来自博查返回，供前端展示/留档——price 的出处也在这里）

**错误码**（不新增第八个）

| 场景 | 错误码 |
|---|---|
| `name` 空 / 超长 | 走 schema 校验（`min_length=1` + strip 校验器），FastAPI 默认 **422**——与现有 cart 接口口径一致，不走 40001 |
| 搜索无结果（博查通了但 0 条） | 不报错：正常返回 `specs: {}`、`sources: []`，前端提示「没查到资料，请手动填写」 |
| 用户四家 key 都没配 | 沿用 `ApiKeyService.key_for_call` 现有未配 key 行为（`KeyRecordError` → router 转 `PARAM_INVALID`） |
| 博查 key 未配 / 搜索失败 / 模型失败 / JSON 解析失败 | `INTERNAL 50000`（服务端问题，提示用户稍后重试或手填） |
| （可选）进程内每用户限频，60 秒 3 次 | `RATE_LIMITED 42901` |

## 2. 服务层设计（两个新文件 + 一处既有改动）

**为什么拆两个文件**：搜索外呼与 LLM 外呼是两类依赖、两套失败模式；分开才能「探针单测博查、不拉模型陪跑」，也是将来 A2′ 提起搜索工具时的天然边界。

| 文件 | 职责 | 关键函数 |
|---|---|---|
| `app/services/web_search_service.py`（新建） | 博查客户端，只管搜 | `async def web_search(query: str, count: int = 5) -> list[dict]`，返回 `[{name, url, snippet, summary, datePublished}]` |
| `app/services/spec_complete_service.py`（新建） | 编排：拼 query → 搜索 → 摘要拼 prompt → 调轻量模型 → 解析 JSON | `async def complete_specs(user_id: int, ring: KeyRing, name: str, category: str | None) -> dict` |
| `app/services/model_call.py`（新建，2026-10-07 大宋拍板） | 补全**不复用** `answer_with_user_key`（那是面向 chat 语义的封装，往里塞补全专用开关是职责串味）。把恰好住在 `chat_service.py` 里的**公共底座**抽到独立模块：`MODEL_PROVIDERS`（收缩后 deepseek/qwen 两家）、`ModelCallError`、`validate_model_name` / `resolve_model_name`、`headers_for`（由 `_headers_for` 去私有化改名）。**另含 `ChatClient` 异步客户端类（10-07 晚大宋拍板，采纳「统一客户端」形态）**：OpenAI 兼容最小封装（AsyncClient + 超时 + 禁重定向），401/403 抛带 `status_code` 的 `ModelCallError`，`mark_invalid` 留在调用方；将来非兼容厂商（anthropic 协议等）的差异收在这一个类里 | — |
| `app/services/chat_service.py`（小改） | 移出上述底座、改从 `model_call` 导入；`answer_with_user_key` 内部 httpx 段改用 `ChatClient`（行为不变，现有测试背书，两步各自全绿）；`chat.py` / `settings.py` 里 `MODEL_PROVIDERS` 等导入行同步改源 | — |

**调用要点**：

- `spec_complete_service` **自写调用函数**（`_call_model`）：Anthropic shape（`system` 独立字段）/ OpenAI 兼容 shape（system 进 messages）分支照抄 `answer_with_user_key` 的请求体形状，但 system prompt 用补全专用 PROMPT、模型名直接取 `MODEL_PROVIDERS[provider]["model"]`（强制默认档，不读用户保存的 `model_name`）、401/403 走 `mark_invalid` + `ModelCallError`（router 侧错误映射与 chat 相同口径）
- 搜索 query：`f"{name} 参数 规格"`（`category` 有值则前缀 `{category} {name} 参数 规格`）
- 摘要拼上下文时保留 `datePublished`，让模型能判断信息新旧
- 模型输出解析：`json.loads` 失败按模型失败处理 → `INTERNAL`；`specs` 里不带 `(AI)` 后缀的键，代码侧补后缀兜底（防模型漏加）；`name` / `category` 做限长裁剪（256 / 64，与表列同口径）并 strip，空值或 null 用请求原值回落（`category` 回落 `None`）；`price` 校验为正数且 ≤ 9,999,999，非法（含 bool、字符串、负数、超限）一律置 `null`——模型嘴里的数字不可信
- 复用 `chat_service` 现成的 key 借还 / 401-403 `mark_invalid` / 超时口径，不另造一套

**配置**：`app/core/config.py` 加 `bocha_api_key: str`（读 `.env`）；`.env.example` 加 `BOCHA_API_KEY=` 占位。

## 3. Prompt 全文（补全专用，独立于 chat 的 SYSTEM_PROMPT）

```text
你是商品资料补全助手。以下是搜索到的公开网页资料，请从中提取「{name}」的信息。

要求：
1. 只提取搜索资料能支撑的内容，资料里没有的不要编造；
2. 输出 JSON 对象，格式：
   {"name": "规范的商品全名", "category": "商品分类", "price": 公开参考价数字或 null, "specs": {"参数名(AI)": "参数值"}}
   其中 name 是规范全名，category 是简短分类（如 耳机、手机、键盘），资料判断不出就填 null；
   price 只能是搜索资料里明确出现的公开标价（单个数字，单位元），资料里没有明确价格就填 null，不要估算；
   specs 里每个键名必须以 (AI) 结尾；
3. 不要输出任何优惠、库存、购买链接；
4. 只输出 JSON 本身，不要解释。
```

> chat 的 `SYSTEM_PROMPT` 红线句（「你没有实时数据，不得声称查询过」）与本 prompt **互不影响**：chat 是闲聊咨询场景，补全是「明确有搜索动作」的场景，二者 prompt 分离是刻意的。

## 4. 实现顺序（由大宋实现）与自测判据

1. `.env` + `config.py` 加 `bocha_api_key`
2. `web_search_service.py` + 探针脚本（临时目录，跑完即弃）：单跑博查，**确认真实返回结构**（公开资料口径为 `data.webPages.value[]`，以你实测为准），字段名对不上以实测为准回写本契约
3. 新建 `app/services/model_call.py` 抽公共底座 + `chat_service` / `chat.py` / `settings.py` 改导入行（`_headers_for` 顺势去私有化为 `headers_for`；现有 chat 测试须全绿）
4. `spec_complete_service.py` + prompt
5. schema（`cart_sche.py` 加 `AiDraftInSchema`）+ router 端点
6. `with TestClient(app) as c:` 走通：未配 key 报错 / name 空报 40001 / 正常返回草稿
7. 前端 CartView：name 非空才亮「AI 补全」按钮；返回后把 `name` / `category` / `price` / `specs` **直接回填进添加表单对应输入框**（用户自行核对修改），price 输入框旁固定提示「网络参考价，可能过时，以商品页实际价格为准；如有更低价请自行修改」，键名含 `(AI)` 的项渲染「来源：网络」徽标；用户点「添加」走现有 `POST /cart/items`

**完成判据**：添加商品勾选 AI 补全 → 草稿带 `(AI)` 键填入表单并带来源徽标 → 用户确认入库后 `GET /cart/items` 里 specs 原样含 `(AI)` 键。

## 5. 红线自查

- ✅ 零交易动作：不产出任何购买链接；price 仅回填公开参考价，带前端提示、用户可改，不构成报价行为（2026-10-07 修订）
- ✅ 未确认数据不入库：draft 只产草稿，入库走用户确认后的现有端点
- ✅ 来源可辨：`(AI)` 后缀随 specs 入库，档案里永久可辨
- ✅ 领域命名：全文用「联网搜索/补全/查询」，无「爬取」
