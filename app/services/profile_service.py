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
            # 近期对话从最新往旧装，超预算就停。切忌整体左截断（composed[:cap]）：
            # 那会留下最旧的几轮、把「本轮新信号」扔掉——而「这轮有没有新偏好」
            # 正是 A6 的核心职责（2026-10-14 验收实测，左截断下最新提问整段消失）
            lines, budget = [], _MESSAGE_CAP
            for m in reversed(history):
                piece = f"{'用户' if m.role == 'user' else '助手'}：{m.content[:_MESSAGE_CAP]}\n"
                if budget - len(piece) < 0:
                    break
                lines.append(piece)
                budget -= len(piece)
            history_text = "".join(reversed(lines))
        # session ②：调模型（call_model 内部要用 session 查 user_api_key，别空手调）
        async with async_session_local() as session:
            verdict, _ = await model_call.call_model(user_id, [
                {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"【当前画像】\n{prefs_json[:_EVIDENCE_CAP]}\n\n"
                    f"【行为证据】\n{evidence[:_EVIDENCE_CAP]}\n\n"
                    f"【近期对话】\n{history_text}"
                )},
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
