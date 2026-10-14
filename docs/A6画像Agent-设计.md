# A6 画像 Agent — 设计

> 拍板沿革：2026-10-06 深夜两轮修正定「A6 总结判断制 + user_profile 结构化落库」；
> 2026-10-14 上午补「长期画像」方向（大宋：「这个画像应该更偏向于用户长期画像」），
> 输入构成随之从「跨会话最近 20 条原始消息」改为「同会话近期消息 + 行为证据摘要」。
> 本文是后者的施工依据。

## 1. 定位：读写两侧，经表解耦

| 侧 | 时机 | 职责 |
|---|---|---|
| 写（A6） | 每轮对话结束后台异步 | 提炼偏好 → 全量覆盖写 `user_profile.preferences` |
| 读（chat） | 每条消息同步 | 读 `preferences` + 行为证据摘要 → 拼进 system prompt |

两侧隔着 `user_profile` 表：A6 挂了（key 失效/欠费/模型返回垃圾）不影响读取，chat 永远不等 A6。
回复与画像更新有一轮的时滞——A6 在响应发出后才跑，用户这轮看到的回答基于更新前的画像。可接受：异步画像本来就是最终一致。

## 2. A6 输入构成（长期画像语义）

| 证据源 | 取数 | 角色 |
|---|---|---|
| 当前 `preferences` | 全量 | 基底，全量覆盖写在它上面 |
| 近期对话 | **同会话**最近 12 条（复用 `chat_repo.recent_messages`，与 chat 的 `_HISTORY_LIMIT` 同口径） | 捕捉「这轮有没有新信号」 |
| 行为证据摘要 | 消费记录（扫描上限 200）+ 物品库全量的**聚合特征**，现算不落库 | 判断「新信号是否稳定、值得收」 |

三个已拍板的边界：

1. **不跨会话回读历史**。旧会话的提炼成果已在 `preferences` 里，回读原始消息是重复付费；且多会话并行时「最近 N 条」横跨不相关话题，是噪声。长期性不来自「读更长历史」，来自「行为证据 + 累积式覆盖」。
2. **购物车不进证据源**。购物车是「想买还没买」——当前意图，短期信号。行为证据只认已发生的事实：消费记录（买过）+ 物品库（持有）。购物车是 chat 引用面板的料，不是画像的料。
3. **行为摘要是视图不是事实**。`summarize_purchases` / `summarize_owned` 每次现算（cap 1500 字符），不落库——落库就是造第二份事实源，迟早漂移。

### 稳定判据（prompt 里落成三条，满足其一才收）

- 用户明确声明且带稳定语态（「一般」「总是」「通常」）；
- 或在近期对话里出现 ≥2 次；
- 或有行为证据支撑（同类已购/已持有 ≥2 件）。

单次声明 + 无行为支撑 → 不收。一次性语境（「这次想买个便宜的」）不收。拿不准就不收。

## 3. 选型：FastAPI BackgroundTasks

`asyncio.create_task` 在 handler 里 fire-and-forget：异常吞没、请求结束即失联、测试要手动 drain；Celery/arq 要新依赖新进程——项目原则是按里程碑演进不堆技术。BackgroundTasks：响应发出后在同 worker 执行、异常可捕获、TestClient 里同步跑可测、零新依赖。多 worker 时任务在受理请求的 worker 里跑，upsert 幂等，无跨 worker 协调问题。

A6 用**自建 session**（`async_session_local()`）——BackgroundTasks 在响应后执行，请求 session 已随 `get_db_session` 的 `async with` 关闭。

## 4. upsert：update-first + insert 兜底

`update ... where user_id=?` → `rowcount>0` 即完成；为 0 才 insert，insert 撞主键（同一用户两轮几乎同时结束的竞态）时捕 `IntegrityError` → rollback → 转 update。全量覆盖语义下，竞态最坏是一次 A6 结果被另一次覆盖，记日志即可。

## 5. 防抖动三层

1. prompt 判据（§2 三条）；
2. 输出 `{"updated": false}` 时**完全不写库**——否则每轮空写，`update_time` 失去「画像何时真变过」的意义；
3. `_parse_verdict` 解析失败一律 `(False, {})`——模型发回垃圾等于没发。fence 包裹、`updated` 非 true、`preferences` 非 dict 或为空，全部按不更新处理。

## 6. 完整参考代码（2026-10-14 定稿，与对话中列出的版本一致）

### 6.1 `app/services/profile_service.py`（新建，全文）

```python
"""A6 画像 Agent：每轮对话结束后台异步提炼长期偏好，全量覆盖写 user_profile。

读写两侧经 user_profile 表解耦——本模块负责「写」（refresh_profile，BackgroundTasks
入口）和「证据视图」（build_profile_context / load_profile_context，chat 读取侧共用）；
chat 只读表，永远不等 A6。设计依据 docs/A6画像Agent-设计.md。
"""
import json
import logging
from collections import Counter

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import async_session_local
from app.models import PurchaseRecord, UserProfile
from app.repository import chat_repo, owned_repo
from app.services import model_call

logger = logging.getLogger(__name__)

_PROFILE_HISTORY = 12       # 同会话最近 N 条，与 chat _HISTORY_LIMIT 同口径
_PROFILE_SCAN = 200         # 消费记录扫描上限，与 GET /purchase-records 同宽
_PROFILE_RECENT = 8         # 摘要里列最近几条
_EVIDENCE_CAP = 1500        # 行为证据摘要字符上限
_MESSAGE_CAP = 6000         # A6 单条 user 消息字符上限
_NAME_CAP = 60              # 摘要里商品名截断

PROFILE_SYSTEM_PROMPT = """你是用户画像提炼员。根据对话和当前画像，判断是否出现新的稳定偏好。
规则：
1. 只收「明确且稳定」的偏好，满足其一才收：用户明确声明且带稳定语态（一般/总是/通常）；或在近期对话里出现两次以上；或有行为证据支撑（同类已购/已持有两件以上）；
2. 一次性语境（如「这次想买个便宜的」）不收；拿不准就不收；
3. 输出只能是且必须是一个 JSON 对象：{"updated": false} 或 {"updated": true, "preferences": {完整新画像}}；
4. updated 为 true 时给全量画像（在【当前画像】基础上增删改），不是增量；
5. preferences 键用简短中文（如 预算区间/品牌倾向/用途场景/在意参数），值用一句话说清。"""


# ---------- 纯函数：证据视图（chat 读取侧与 A6 共用） ----------

def _one_line(value: str | None, cap: int) -> str:
    """折叠空白再截断。名称来自用户自填或页面标题，都可能带换行。"""
    return " ".join((value or "").split())[:cap]


def _brand(row) -> str:
    """品牌从 specs 聚合，不从自由文本 name 里抽——name 是用户自填/页面标题，不可靠。"""
    return str((row.specs or {}).get("品牌") or "").strip()


def _fmt_value(value) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _price_range(priced: list[float]) -> str:
    lo, hi = min(priced), max(priced)
    return f"{lo:g}~{hi:g} 元" if lo != hi else f"{lo:g} 元"


def format_preferences(prefs: dict) -> str:
    """画像 → 一行行「键：值」；空字典返回空串，调用方据此不加块。"""
    if not prefs:
        return ""
    return "\n".join(f"{_one_line(str(k), 32)}：{_one_line(_fmt_value(v), 200)}"
                     for k, v in prefs.items())


def summarize_purchases(rows: list[PurchaseRecord]) -> str:
    """纯函数：条数/价位区间/Top 平台/品牌 Top3/最近买过。

    价格均为用户自行记录的历史价，非实时价——文案里必须带这句，
    防止模型把历史价当现价引用（合规红线：价格透明）。
    """
    if not rows:
        return ""
    parts = [f"消费记录共 {len(rows)} 条。"]
    priced = [row.price for row in rows if row.price is not None]
    if priced:
        parts.append(
            f"其中 {len(priced)} 条填了价格（用户自记历史价，非实时价）：价位 {_price_range(priced)}。")
    platforms = Counter(row.platform for row in rows if row.platform)
    if platforms:
        parts.append("常记录的购买平台：" + "、".join(
            f"{name} {count} 件" for name, count in platforms.most_common(3)) + "。")
    brands = Counter(b for b in (_brand(row) for row in rows) if b)
    if brands:
        parts.append("买过的品牌：" + "、".join(
            f"{name} {count} 件" for name, count in brands.most_common(3)) + "。")
    recent = [row for row in rows if row.name][:_PROFILE_RECENT]
    if recent:
        parts.append("最近买过：" + "；".join(
            f"{_one_line(row.name, _NAME_CAP)}"
            f"（{row.purchased_at.strftime('%Y-%m') if row.purchased_at else '日期未记'}）"
            for row in recent) + "。")
    return " ".join(parts)


def summarize_owned(rows: list) -> str:
    """纯函数：持有件数/品类 Top3/品牌 Top3/价位区间。全量聚合，物品库规模天然小。"""
    if not rows:
        return ""
    parts = [f"物品库共 {len(rows)} 件。"]
    categories = Counter(row.category for row in rows if row.category)
    if categories:
        parts.append("持有的品类：" + "、".join(
            f"{name} {count} 件" for name, count in categories.most_common(3)) + "。")
    brands = Counter(b for b in (_brand(row) for row in rows) if b)
    if brands:
        parts.append("持有的品牌：" + "、".join(
            f"{name} {count} 件" for name, count in brands.most_common(3)) + "。")
    priced = [row.price for row in rows if row.price is not None]
    if priced:
        parts.append(f"持有物价位：{_price_range(priced)}（自记历史价）。")
    return " ".join(parts)


def build_profile_context(prefs: dict, purchase_rows, owned_rows) -> str:
    """读取侧与 A6 共用的一份证据视图：偏好块 + 行为证据块，空则不加。"""
    blocks = []
    pref_text = format_preferences(prefs)
    if pref_text:
        blocks.append(f"【用户偏好】\n{pref_text}")
    purchase_text = summarize_purchases(purchase_rows)
    if purchase_text:
        blocks.append(f"【消费行为】\n{purchase_text}")
    owned_text = summarize_owned(owned_rows)
    if owned_text:
        blocks.append(f"【持有物品】\n{owned_text}")
    return "\n\n".join(blocks)


# ---------- 纯函数：A6 输出解析（防抖动第三层） ----------

def _parse_verdict(text: str) -> tuple[bool, dict]:
    """模型输出 → (是否更新, 全量画像)。任何解析失败 = 不更新。"""
    raw = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return False, {}
    if not isinstance(data, dict) or data.get("updated") is not True:
        return False, {}
    prefs = data.get("preferences")
    if not isinstance(prefs, dict) or not prefs:
        return False, {}
    return True, {str(k): v for k, v in prefs.items()}


# ---------- 写：upsert（Agent 不碰库，这是 service 层干的事） ----------

async def upsert_preferences(user_id: int, preferences: dict, session: AsyncSession) -> None:
    """全量覆盖。update-first：rowcount>0 即完成；为 0 才 insert。

    rowcount 是「匹配行」不是「变更行」——SQLAlchemy 给 MySQL 驱动开了
    CLIENT.FOUND_ROWS（2026-10-14 实测：同值更新 rowcount=1），所以同值重写
    不会误走 insert。insert 撞主键只可能是真竞态（同一用户两轮几乎同时结束），
    捕 IntegrityError 兜底转 update。与 conversation_repo.update_title 的
    rowcount 判据同一口径。
    """
    result = await session.execute(
        update(UserProfile).where(UserProfile.user_id == user_id).values(preferences=preferences)
    )
    if result.rowcount:
        await session.commit()
        return
    session.add(UserProfile(user_id=user_id, preferences=preferences))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await session.execute(
            update(UserProfile).where(UserProfile.user_id == user_id).values(preferences=preferences)
        )
        await session.commit()


# ---------- 读：chat 注入用的证据视图（与 A6 输入同一份材料） ----------

async def load_profile_context(user_id: int, session: AsyncSession) -> str:
    """读 preferences + 两份行为证据，拼成注入块。全空返回空串（调用方不加块）。

    与 A6 的输入共用 build_profile_context——「回答为什么这么贴人」和
    「画像基于什么更新」从此是同一套材料。
    """
    current = await session.get(UserProfile, user_id)
    prefs = dict(current.preferences) if current else {}
    purchases = list((await session.scalars(
        select(PurchaseRecord).where(PurchaseRecord.user_id == user_id)
        .order_by(PurchaseRecord.create_time.desc(), PurchaseRecord.id.desc())
        .limit(_PROFILE_SCAN))).all())
    owned = await owned_repo.get_owned_by_user_id(user_id, session)
    return build_profile_context(prefs, purchases, owned)


# ---------- 后台入口：每轮对话结束异步刷新 ----------

async def refresh_profile(user_id: int, conversation_id: int) -> None:
    """BackgroundTasks 入口。全异常自吞只记日志——画像失败绝不能影响已发出的回复。"""
    try:
        # session ①：只取数，且关门前把 ORM 行压成纯数据——session 关闭后实例变
        # detached，那时再访问 row.price / current.preferences 会踩
        # DetachedInstanceError（本项目 MissingGreenlet 一族的老坑）
        async with async_session_local() as session:
            history = await chat_repo.recent_messages(user_id, conversation_id,
                                                      _PROFILE_HISTORY, session)
            if not history:
                return
            current = await session.get(UserProfile, user_id)
            purchases = list((await session.scalars(
                select(PurchaseRecord).where(PurchaseRecord.user_id == user_id)
                .order_by(PurchaseRecord.create_time.desc(), PurchaseRecord.id.desc())
                .limit(_PROFILE_SCAN))).all())
            owned = await owned_repo.get_owned_by_user_id(user_id, session)
            prefs_json = json.dumps(dict(current.preferences) if current else {}, ensure_ascii=False)
            evidence = build_profile_context(dict(current.preferences) if current else {},
                                             purchases, owned)
            history_text = "".join(
                f"{'用户' if m.role == 'user' else '助手'}：{m.content[:_MESSAGE_CAP]}\n"
                for m in history)
        # session ②：调模型（call_model 内部要用 session 查 user_api_key，别空手调）
        async with async_session_local() as session:
            verdict, _ = await model_call.call_model(user_id, [
                {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"【当前画像】\n{prefs_json}\n\n"
                    f"【行为证据】\n{evidence[:_EVIDENCE_CAP]}\n\n"
                    f"【近期对话】\n{history_text}"
                )[:_MESSAGE_CAP]},
            ], session)
        updated, preferences = _parse_verdict(verdict)
        if not updated:
            return  # 防抖动：无变化不写库，update_time 不动
        # session ③：落库
        async with async_session_local() as session:
            await upsert_preferences(user_id, preferences, session)
    except Exception:
        logger.exception("A6 画像刷新失败 user_id=%s conversation_id=%s（不影响主对话）",
                         user_id, conversation_id)
```

三段式 session 的道理：取数、调模型、落库各自只在自己的 session 里干活。合并②③也行（模型调用只读 key 不写），但分开读起来是三条直线，debug 时一眼看出哪段挂的。

### 6.2 `app/services/chat_service.py`（改，共 4 处）

```python
# ① import 区加两行
from fastapi import BackgroundTasks
from app.services import model_call, profile_service

# ② send_message 签名加 background_tasks
async def send_message(user_id: int, payload: ChatSendInSchema, session: AsyncSession,
                       background_tasks: BackgroundTasks) -> ChatSendOutSchema:
    ...  # 前半段（懒创建/落 user 消息/取引用商品）不动

    # ③ system 组装：拼上画像块（同 session 现查，纯文本返回，不涉 ORM 跨 session）
    profile_context = await profile_service.load_profile_context(user_id, session)
    system = SYSTEM_PROMPT if not profile_context else f"{SYSTEM_PROMPT}\n\n{profile_context}"
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": m.role, "content": m.content} for m in history)
    ...  # 引用商品块、call_model、assistant 落库、touch 都不动

    # ④ 末尾加一行：后台刷新画像（响应发出后才跑，失败只记日志）
    background_tasks.add_task(profile_service.refresh_profile, user_id, conversation_id)
    return ChatSendOutSchema(conversation_id=conversation_id, reply=reply, model=model)
```

### 6.3 `app/router/chat.py`（改，2 处）

```python
from fastapi import APIRouter, BackgroundTasks, Depends   # ① 加 BackgroundTasks

@chat_router.post("/message", dependencies=[Depends(require_same_origin_write)])
async def message(payload: ChatSendInSchema, user: CurrentUser,
                  background_tasks: BackgroundTasks,          # ② 声明即注入，无需 Depends
                  session: AsyncSession = Depends(get_db_session)):
    check_rate_limit(f"chat:{user.id}", limit=_CHAT_LIMIT, window=_CHAT_WINDOW)
    return success(await chat_service.send_message(user.id, payload, session, background_tasks))
```

### 6.4 P2 护栏（可选，建议同批做）

```python
# chat_service.py 内：history 之后加总字符截断，防长对话把模型上下文撑爆
# （12 条 × 4000 字无上限，中文约 5~9 万 token，会超部分模型上下文）
def _cap_history(messages: list, cap: int = 8000) -> list:
    total = 0
    kept = []
    for m in reversed(messages):          # 从最近的开始留
        total += len(m.content)
        if total > cap:
            break
        kept.append(m)
    return kept[::-1]
```

调用点：`history = _cap_history(chat_repo.trim_trailing_users(await chat_repo.recent_messages(...)))`

## 7. 文件清单与实现顺序（由大宋实现）

| 顺序 | 文件 | 动作 |
|---|---|---|
| 1 | `app/services/profile_service.py` | 新建：纯函数四个 + `_parse_verdict` + `upsert_preferences` + `refresh_profile` |
| 2 | `app/services/chat_service.py` | system 拼画像块；签名与末尾接 BackgroundTasks |
| 3 | `app/router/chat.py` | `background_tasks` 透传 |
| 4 | `tests/test_profile_service.py` | 纯函数 + DB 探针（见 §8） |
| 5 | `README.md` | 对话表补一句「每轮结束异步跑 A6 画像（烧用户 key，一轮两次模型调用）」 |

**无 repo 改动**——`chat_repo.recent_messages`、`owned_repo.get_owned_by_user_id` 已覆盖全部取数；消费记录 inline select（与 `purchase_record.py` router 同风格，旧 user_profile.py 也是 inline）。

## 8. 测试清单

纯函数（任何环境可跑）：
- `_parse_verdict`：fence 包裹 / `updated:false` / 垃圾文本 / `preferences` 空 → 全部不更新；正常 JSON → 更新且键转 str
- `summarize_purchases`：空列表 / 全缺价 / 有价有平台 / 品牌从 specs 聚合（name 里带品牌字样但不进 stats）
- `build_profile_context`：三项全空 → 空串（调用方不加块）

DB 探针（`RUN_MYSQL_KEY_TESTS=1`，monkeypatch `model_call.call_model`）：
- `refresh_profile` 正常路径落库：preferences 写入、`update_time` 推进
- `updated:false` 不写库：`update_time` 不变
- 模型抛 `ModelCallError`：`refresh_profile` 不 raise（自吞），主链路无感
- 历史为空（新会话首轮前的竞态）直接 return，不调模型

## 9. 成本账（每轮 A6，烧用户 key）

| 构成 | 字符量 |
|---|---|
| 同会话最近 12 条对话 | ~2400 |
| 行为证据摘要 | ≤1500（固定，与记录数无关） |
| 当前画像 | ~300 |
| **合计** | **~4200/轮** |

一轮对话 = 2 次模型调用（chat + A6），README 需明示。

## 10. 未决 / 待观察

- **P2 字符护栏未修**：chat 历史 12 条 × 4000 字无总字符上限，A6 注入后 system 侧更长。建议同批在 `send_message` 里按总字符截到 ~8000。由大宋定是否一起做。
- 触发频率维持拍板的「每轮」；若将来要改成「N 条新消息才跑」，属于改拍板，另议。
