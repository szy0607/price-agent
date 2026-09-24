# M0 基座 — `trace_id` 中间件与 `/health`（设计）

> 日期：2026-09-24 ｜ 归属：`开发流程.md` §3 第②步「设计先行」
> 定位：**基础设施**，与业务契约正交（不属于注册/登录那一轮），但属 M0 退出条件
> 实测环境：`E:\conda\envs\fast`（Python 3.10.20）+ **_真实 uvicorn 起服务**（不是 TestClient）
>
> ⚠️ 本文不含业务代码，给的是形状 / 顺序 / 理由。**代码由大宋实现。**

---

## 0. 为什么现在做这件事

三个地方都在要求它，但不是同一件事：

| 来源 | 要求 | 性质 |
|---|---|---|
| `开发流程.md` §2 | M0 退出条件：「**后端可启动返回健康检查**」；关键产出含「配置 / 日志 / **trace_id**」 | 里程碑门槛 |
| 契约 §7.2 | 审计口径：「每次请求带 `trace_id`，**响应头回传 `X-Trace-Id`**」 | 接口契约 |
| `开发流程.md` §7 红线⑧ | 「**审计可回放**：每次查询带 trace_id，输入/输出全量记录」 | 合规红线（M2 全量落地，但 trace_id 的贯通必须现在建） |

**一句话**：`/health` 是"你的服务还活着吗"，`trace_id` 是"出问题了我怎么把它对上号"。
后者晚做不会返工，但**一旦上线，早期那些没有 trace_id 的日志就永久无法回溯**。

---

## 1. 先说三条实测结论（都推翻了我原本的直觉）

> 探针：`pa_mw_probe.py` / `pa_mw_probe2.py` / `pa_mw_probe3.py`（真实 uvicorn）/ `pa_mw_probe4.py`

### 🔴 结论 1：**500 响应上加不上 `X-Trace-Id`——哪怕中间件写得完全正确**

实测（真实 uvicorn，`@app.middleware("http")` 里 `resp.headers["X-Trace-Id"] = tid`）：

| 请求 | 状态 | `X-Trace-Id` |
|---|---|---|
| `/ok`（正常） | 200 | ✅ 有 |
| `/biz`（`BizError` → 400） | 400 | ✅ 有 |
| **`/boom`（未捕获异常 → 500）** | **500** | **❌ `None`** |

**根因**：Starlette 的中间件栈是这么套的（`build_middleware_stack`）：

```
┌─ ServerErrorMiddleware        ← @app.exception_handler(Exception) 挂在这里
│  ┌─ 用户中间件（我们的 trace）  ← add_middleware / @app.middleware 都加在它内层
│  │  ┌─ ExceptionMiddleware     ← BizError / HTTPException / RequestValidationError
│  │  │  └─ router
```

`Exception` 的处理器挂在**最外层** `ServerErrorMiddleware` 上。它捕获异常后**当场生成响应返回，不再往下流经任何用户中间件** → 中间件那行 `resp.headers["X-Trace-Id"] = tid` 根本没机会执行。

**不修的影响**：**最需要 trace_id 的 500，恰恰拿不到 trace_id。** 用户报"页面 500"，你让他截图响应头——没有；你翻日志，看到一条"未处理异常"却对不上是哪个请求。
→ 直接违反契约 §7.2 的「**每次**请求…响应头回传」，也架空红线⑧的"可回放"。

> 📌 注意：这不只影响加头。**任何"想在中间件里对 500 响应做点什么"的写法都会同样失效**（补日志、改写错误页……）。

### 🔴 结论 2：中间件 `reset` 与「500 处理器读得到 trace_id」**不可兼得**

实测（真实 uvicorn，`/boom` 的处理器里读 `contextvars`）：

| 中间件 `finally: reset` | 500 处理器读到的 trace_id |
|---|---|
| **reset**（教科书式正确写法） | **`None`** ❌ |
| 不 reset | `'6e6d9775dad747c7a8c95ccf0f4aa152'` ✅ |

**为什么**：异常从路由冒泡上来时，**我们中间件的 `finally: reset` 先执行**，把 contextvar 恢复成默认值；然后才轮到外层 `ServerErrorMiddleware` 调处理器 → 此时已经是 `None`。

**不修的影响**：如果照着"reset 是正确卫生习惯"去写，500 那条日志里的 trace_id 会**永远是 None** —— 而且不报错、静默失效，最难发现。

### ✅ 结论 3：`contextvars` 在真实 uvicorn 下**天然按请求隔离**（但 TestClient 下会串号）

| 环境 | `/leak`（处理器里写 `DIRTY`）之后，下一个请求读到 |
|---|---|
| **真实 uvicorn** | 读到的是**新的正常 tid**，不是 `DIRTY` → ✅ 隔离 |
| **TestClient** | **读到 `DIRTY`** → ❌ 串号（实测：连中间件都不挂，`/boom` 处理器都能读到上一次的值） |

**原因**：uvicorn 每个 HTTP 请求起**独立 asyncio task**（`loop.create_task(run_asgi())`），contextvar 是 task 局部的；而 `TestClient` 走 `ASGITransport`，是**在同一个 task 里直接 await app**，所以写进去的值会留着。

→ ⚠️ **又一条"测试假象"**（同 `fastapi-async-probe` 记的那类）：**用 TestClient 验证 contextvar 隔离，结论一定是错的。** 这类行为必须用真实 uvicorn 测。

---

## 2. 设计：`trace_id` 怎么走

### 2.1 两个通道，各司其职（这是结论 1+2 的解法）

```
                    ┌─────────────────────────────────────────┐
请求进来 →  中间件   │ ① trace_id_var.set(tid)   → 给「日志」用   │
                    │ ② request.state.trace_id = tid → 给「异常处理器」用 │
                    └─────────────────────────────────────────┘
                                     ↓
                              路由 / 业务代码
                                     ↓
            正常 ──→ 中间件给响应加 X-Trace-Id          ✅ 实测通过
            异常 ──→ ServerErrorMiddleware 的处理器
                      └─ 自己从 request.state 取，塞进响应头   ✅ 实测通过
```

**为什么必须两个通道，而不是只留 contextvar**：

| 通道 | 服务对象 | 为什么不能用另一个 |
|---|---|---|
| **`contextvars`** | **日志**（`logging.Filter` / `logger.info(...)`） | 日志格式化器**拿不到 `request` 对象**（它只有 `record`），只能用 contextvar |
| **`request.state`** | **异常处理器 / 路由** | 结论 2：处理器能拿到 `request` 参数，而 contextvar 若被中间件 `reset` 就是 `None`；`request.state` 绕开整个 reset 时序问题 |

> `request.state` 之所以能跨到最外层的处理器，是因为它**存在 `scope["state"]` 这个字典里**，
> 而所有包同一个 `scope` 的 `Request` 对象共享它。**已实测确认**（见 §3 的验证结果）。

### 2.2 所以中间件的职责定成

```
① 取/生成 trace_id
② contextvar.set(tid)            ← 日志通道
③ request.state.trace_id = tid   ← 异常处理器通道
④ resp = await call_next(request)
⑤ resp.headers["X-Trace-Id"] = tid   ← 正常路径（400 及以下也走这条，实测有效）
finally: contextvar.reset(token)     ← 可以放心 reset 了
```
⑥ 异常处理器里**自己补头**（这是**结论 1 的唯一出路**）：
```
_h_exc: tid = getattr(request.state, "trace_id", None)
        return JSONResponse(..., 500, headers={"X-Trace-Id": tid} if tid else None)
```

### 2.3 trace_id 的来源：本轮**总是自己生成**，不透传上游

| | 生成（推荐） | 透传上游 `X-Trace-Id` |
|---|---|---|
| 收益 | 简单、零攻击面 | 跨网关/Nginx/前端链路能串起来 |
| 代价 | —— | **必须清洗**：长度 ≤64 + 字符集 `[A-Za-z0-9-]`，**否则是日志注入**（CWE-117）—— 攻击者传 `"abc\nINFO 用户登录成功"`，你的日志里就凭空多一行假的 |

**本轮选生成**：现在没有上游（前端直连 Vite 代理），透传**零收益**；而透传入口 = 必须写清洗 = 多一个可被攻击的面。
→ 等真接了网关/Nginx 再做，那时**清洗逻辑必须先写**。

生成建议：`uuid4().hex`（32 位 hex）。将来接 OpenTelemetry 再换 W3C `traceparent` 格式。

### 2.4 中间件写法：**纯 ASGI，不用 `@app.middleware("http")`**

实测两者在 contextvar 可见性上**完全等价**（变体 A/B 结果一致），所以选纯 ASGI **不付任何代价**，却避开 `BaseHTTPMiddleware` 已知的两个坑：

1. **流式响应**：`BaseHTTPMiddleware` 会把响应包成 `StreamingResponse` 处理 —— 而 **M4 明确要做流式**（`开发流程.md` §2 M4「前端联调…流式」）。提前避开。
2. **后台任务（`BackgroundTasks`）**：它用独立的 anyio task group 跑下游，与 `background` 的执行时机有已知干扰。

写法形状（`app.add_middleware(...)` 传一个 ASGI callable 类）：
```
class TraceMiddleware:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":        # ← 别漏：还有 lifespan/websocket
            return await self.app(scope, receive, send)
        ...
```

> ⚠️ **`scope["type"] != "http"` 这个判断不能省**。uvicorn 启动时会用 `lifespan` 消息走同一个 ASGI 入口，
> 不判断的话 `scope["state"]` 那些字段可能不存在 → 启动即崩。

---

## 3. 验证：推荐方案在真实 uvicorn 下的结果

（探针 `pa_mw_probe4.py`，四种响应一次跑完）

```
/ok       -> 200  X-Trace-Id=a0e8d444c1c64d0496b8c4355f632e4d  体={"code":0,"msg":"success","data":"ok"}
/biz      -> 400  X-Trace-Id=83e8395775a141a48ab55db6253d2519  体={"code":40001,"msg":"参数错了","data":null}
/boom     -> 500  X-Trace-Id=4843dde99688471f812638ebdeb62c54  体={"code":50000,"msg":"内部服务器错误","data":null}
/health   -> 200  X-Trace-Id=2a6a64c0c3eb4b34bf7466d8a3f8d583  体={"code":0,"msg":"success","data":{"status":"ok"}}
```

**200 / 400 / 500 三条路径全部带上 `X-Trace-Id`** → 契约 §7.2 的「每次请求」才算真做到。

---

## 4. 设计：`/health`

### 4.1 返回体：**守住统一信封**，不发明新错误码

```json
健康: { "code": 0,     "msg": "success", "data": { "status": "ok" } }        HTTP 200
不健康: { "code": 50000, "msg": "内部服务器错误", "data": null }  HTTP 503
```

**为什么不返裸 `{"status":"ok"}`**：项目有一条不变量——「**所有响应都是 `{code,msg,data}`**」（契约 §2.0）。
前端、中间件、测试全都建立在这条上。为运维接口开一个例外，等于让这条不变量变成"大部分情况下成立"。

**为什么 `code` 用 `50000` 而不是新码**：`ErrorCode` 只有 7 个，**禁止发明第八个**（既定纪律）。
DB 连不上就是"服务器内部错误"，语义成立。

> ⚠️ **不能走 `HTTPException(503)`**：`errors.py` 的 `_h_http` 会把状态码映射成 `503*100+1 = 50301`——一个不存在的错误码。
> → `/health` **必须自己返回 `JSONResponse`**，不经过 `_h_http`。

### 4.2 状态码：健康 `200`，不健康**必须 `503`**

🔴 **这是本节最要紧的一条**：健康检查失败时若也返 `200`，**负载均衡 / k8s 永远不会把坏实例摘掉**——
流量继续打到已经连不上库的实例上，然后每个用户都看到 500。健康检查就变成了纯粹的装饰。

### 4.3 要真探 DB，但**不要抛异常**

- **探什么**：契约 §9.2 步骤 5 定的内部 `SELECT 1`。不探库的话，`/health` 只能证明"进程还在"，证明不了"能干活"。
- **怎么探**：**自己 `try/except` 包住**，不要用 `Depends(get_db_session)` 直接依赖。
  - 原因：`get_db_session` 连不上库时是**抛异常**的。异常一路冒到兜底处理器 → 返回 **500**（不是 503），
    而且日志里会刷一条"未处理异常"——**一个预期的运维状态被记成了程序 bug**。
- ⚠️ **必须加超时**（1–2s）。库卡住时 `/health` 不能陪着一起挂：探针超时会被判定为不健康 → 实例被反复重启 →
  雪上加霜。

### 4.4 两个"记账"项（现在不写，但必须留痕）

| 项 | 为什么 |
|---|---|
| `/health` **不记访问日志**（或降到 DEBUG） | 它会被探针每几秒调一次，会把日志刷爆、把真正有用的行淹掉 |
| 将来加限流时，`/health` **必须白名单豁免** | 否则 LB 自己会被限流打挂（`42901`），**故障会被放大成"所有实例同时下线"** |

---

## 5. 落地清单（文件 / 位置）

| # | 文件 | 放什么 | 现在建吗 |
|---|---|---|---|
| 1 | `app/core/trace.py` | `trace_id_var`（ContextVar）+ `get_trace_id()` 取用函数 | ✅ 建 |
| 2 | `app/core/middleware.py` | `TraceMiddleware`（纯 ASGI） | ✅ 建 |
| 3 | `app/core/logging.py` | `setup_logging()`：日志格式里带 trace_id（`logging.Filter` 读 contextvar） | ✅ 建议建（M0 要求的"日志"） |
| 4 | `app/router/health.py` | `GET /health` | ✅ 建 |
| 5 | `app/core/errors.py` | **改 `_h_exc`**：从 `request.state` 取 tid，补 `X-Trace-Id` 头 | 🟡 **改现有代码** |
| 6 | `app/main.py` | `add_middleware(TraceMiddleware)` + `include_router(health_router)` + `setup_logging()` | 🟡 **改现有代码** |
| 7 | `requirements.txt` | **无新增依赖**（纯标准库） | — |

> **位置理由**：`core` 按契约 §4.1 是"全层可用、自身不依赖业务模块"——这三样（trace / 中间件 / 日志）刚好符合。
> `/health` 放 `router/` 因为它是**接口**（契约 §4 把接口都放 `router/`），虽然它不属于任何业务域。

**顺序**：①② → ③ → ⑤（改 errors）→ ④ → ⑥。**`errors.py` 的改动在中间**，因为 `_h_exc` 要读 `request.state`，
而那个字段是 ② 写进去的——顺序反了会写出"读不到的代码"。

---

## 6. 验收标准

- [ ] `GET /health` → `200`，体是信封，`data.status == "ok"`
- [ ] **故意把 DB 停掉**（或改错密码）→ `/health` → **`503`**（不是 200，不是 500）
- [ ] 正常请求 → 响应头有 `X-Trace-Id`，且与日志里打的 trace_id **一致**
- [ ] **故意触发 500** → 响应头**也有** `X-Trace-Id`（这条是本文的核心产出）
- [ ] 连打两次请求 → 两次的 trace_id **不同**
- [ ] `/docs` 能打开（中间件没把非 http scope 弄崩）

---

## 7. 待大宋拍板

| # | 项 | 小宋建议 |
|---|---|---|
| 1 | `/health` 是否守统一信封 | **守**（理由见 §4.1） |
| 2 | trace_id 是否透传上游 | **本轮不透传**（理由见 §2.3） |
| 3 | 本轮是否连 `core/logging.py` 一起做 | **建议一起做**——M0 原话是"配置/日志/trace_id"，做一半等于没建立可回放能力 |

---

## 8. 附录：负载均衡实验（实测 · 2026-09-24）

> 目的：**亲眼验证"`/health` 返 503 会被摘掉、返 200 会被继续打流量"** —— 这是 §4.2 那条 🔴 规则的实证。
> 环境实测：本机**没有 nginx、没有 docker**（`where nginx` / `docker --version` 均无）。
> 所以实验用**自己写的 ~60 行 asyncio 负载均衡**——好处是黑盒被打开：轮询表、健康标记、摘除动作全在明面上。
> **Nginx / 云 LB 就是这套逻辑的工程化版本**，看完这个再看 `nginx.conf` 的 `upstream` 段就是一眼的事。

### 8.1 实验设计（三阶段对照）

三个进程：**后端 A `:8101`** / **后端 B `:8102`** / **负载均衡 `:8100`**。

关键：两个后端的 `/health` **真去连 MySQL**（用项目 `.env` 里的真实连接串），不是假的。
B 上挂一个开关，能让它的 `/health` 去连一个**没人监听的端口**（`:3399`）→ **真的连接失败 → 真的 503**。

| 阶段 | 自变量（改什么） | 因变量（看什么） |
|---|---|---|
| ① 基线 | 两个后端都健康 | 请求是否**交替**落到 A / B |
| ② 摘除 | B 的库**真的连不上** | 多久后被摘掉？中间有没有**窗口期**？ |
| ③ 恢复 | B 的库恢复 | 多久**重新接纳**？还是有窗口？ |

### 8.2 实测结果（LB 探针间隔 2s）

```
阶段① 基线（都健康）
  LB 视角: {'A': {'healthy': True, 'probes': 2}, 'B': {'healthy': True, 'probes': 2}}
  6 次请求落到            -> 8101 8102 8101 8102 8101 8102        ← 轮询生效

阶段② 让 B 的库真的连不上
  B 的 /health 直接返回: 503
  切换后立刻打 4 次        -> 8101 8102 8101 8102                 ← 🔴 窗口期！还在往坏实例打
  >> LB 摘掉 B 实际耗时: 0.9s
  摘掉之后 6 次           -> 8101 8101 8101 8101 8101 8101        ← 全去 A
  LB 视角: {'A': {'healthy': True, ...}, 'B': {'healthy': False, ...}}

阶段③ 让 B 的库恢复
  B 的 /health 直接返回: 200
  恢复后立刻打 4 次        -> 8101 8101 8101 8101                 ← 窗口期同样存在
  >> LB 重新接纳 B 实际耗时: 1.8s
  恢复之后 6 次           -> 8102 8101 8102 8101 8102 8101        ← 恢复交替
```

### 8.3 三条结论（这才是跑这一趟的价值）

1. 🔴 **摘除有窗口期，那段时间用户是真实受损的。**
   B 挂掉后立刻打的 4 次里，**仍有 2 次落到了已经不健康的 B** —— 也就是说，**这 2 个用户会看到 500**。
   健康检查**不能**保证"坏实例立刻不接流量"，它只能把窗口**缩短**。

2. **窗口长度不是固定值**：实测摘除 **0.9s**、恢复 **1.8s**。
   差别来自"切换恰好落在探针周期的哪个位置" → **真实范围是 `0 ~ 1 个探针周期`（随机）**。
   📌 **所以设计时要看的是最坏值，不是平均值。**

3. **探针周期 ≠ 固定间隔**。某轮实测里 B 用 3 秒还没被探完，因为 **B 不健康时探测本身要等超时**。
   → **一轮的真实耗时 = 探测耗时 + 间隔**。实例挂掉的时候，周期会被**拉长**——而这恰恰是你最需要它快的时候。

> 📌 顺带一条认知：这三条合起来解释了**为什么生产上不满足于"只有健康检查"**——
> 才有"连续失败 N 次才摘"、"慢启动"、"连接池排空"这些机制。它们都在同一个权衡上：
> **摘太快会误杀（抖动），摘太慢用户受损。**

### 8.4 LB 的核心逻辑（就这么点代码）

```python
UPSTREAMS = [{"name": "A", "url": "http://127.0.0.1:8101", "healthy": None},
             {"name": "B", "url": "http://127.0.0.1:8102", "healthy": None}]
rr = itertools.cycle(range(len(UPSTREAMS)))

async def prober():                                  # ← 后台探活：所谓"健康检查"就是这段
    while True:
        for u in UPSTREAMS:
            try:
                r = await client.get(u["url"] + "/health", timeout=3)
                u["healthy"] = (r.status_code == 200)   # ← 503 在这里被判死
            except Exception:
                u["healthy"] = False
        await asyncio.sleep(PROBE_INTERVAL)

def pick():                                          # ← 选一个健康的（轮询）
    healthy = [u for u in UPSTREAMS if u["healthy"]]
    if not healthy:
        return None                                  # 全挂 → LB 自己返 503
    for _ in range(len(UPSTREAMS)):
        u = UPSTREAMS[next(rr) % len(UPSTREAMS)]
        if u["healthy"]:
            return u
    return healthy[0]
```

> **看加粗那一句**：`u["healthy"] = (r.status_code == 200)`。
> **这就是「`/health` 不健康必须返 503」的全部理由。** LB 就是拿状态码做的判断——
> 你返 200，它就把这台标成健康，然后继续往这儿打流量，直到每个用户都看到 500。

### 8.5 怎么自己复现

1. 临时目录建两个文件：`backend.py`（FastAPI + `/health` 探库 + `/whoami` 返回端口 + `/admin/db-toggle`）
   与 `lb.py`（上面 §8.4 的逻辑 + catch-all 转发）
2. 起三个 uvicorn：`PORT=8101 backend:app`、`PORT=8102 backend:app`、`PROBE_INTERVAL=2 lb:app`（8100）
3. 三阶段按 §8.1 打请求，用 `/lb/status` 观察 LB 视角的 `healthy` 标记
4. **想调参就改 `PROBE_INTERVAL`**——你会直接看到"窗口期变长/变短"

> ⚠️ 三个坑：① `PYTHONPATH` 要指项目根，否则 `import app.core.config` 失败
> ② 端口别撞项目在用的 8000 ③ 探针 app 文件放临时目录，**别留在项目里**

### 8.6 对本项目的直接指导

- 将来上线配探针时，**`interval` / `timeout` / `threshold` 三个旋钮拧的都是"窗口期多长"**——不是"安不安全"
- M7 若要把 `/health` 拆成 `liveness` + `readiness`，本节的实测数字就是依据（readiness 的窗口直接等于用户受损时长）
