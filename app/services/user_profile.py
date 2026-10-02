"""把用户的消费记录压成一段能进对话的文本。

两个用途，都在 system 侧，不改 `messages` 的结构：

- `build_purchase_profile`：全量画像摘要，每条消息都带，让模型知道「这人买过什么」；
- `build_record_focus`：用户本次勾选的那几条逐条展开，作为提问焦点。

上下文一律放在 system 而不是伪装成用户消息 —— `chat.py` 那两条长度限制
（单条 4000 / 总量 12000）管的是用户自己打的话，不该被系统注入的内容吃掉。
"""

import logging
from collections import Counter

from sqlalchemy import select

from app.core.errors import BizError, ErrorCode
from app.database.session import async_session_local
from app.models import PurchaseRecord

logger = logging.getLogger(__name__)

# 与 GET /purchase-records 的硬上限同宽：画像只看最近这些条，不随年份无限膨胀
_PROFILE_SCAN = 200
_PROFILE_RECENT = 8
_PROFILE_CAP = 1200
# 勾选带入：条数上限与 ChatInput.record_ids 的 max_length 一致
_FOCUS_NAME_CAP = 80
_FOCUS_SPECS_CAP = 300
_FOCUS_CAP = 3000

_TEXT_CAP = 4000


def _one_line(value: str, cap: int) -> str:
    """折叠空白再截断。

    名称来自用户自填或页面标题，两者都可能带换行；换行会顶破「一行一条」的排版，
    所以这里统一压成单行。这些内容只进这个人自己的对话，不构成对别人的注入面。
    """
    return " ".join((value or "").split())[:cap]


def _format_price(price: float | None) -> str:
    if price is None:
        return "未填价格"
    return f"{price:g} 元"


def summarize_profile(rows: list[PurchaseRecord]) -> str:
    """纯拼装，不碰数据库 —— 单测可以直接喂构造好的行。"""
    if not rows:
        return ""

    priced = [row.price for row in rows if row.price is not None]
    parts = [f"共 {len(rows)} 条消费记录。"]
    if priced:
        parts.append(
            f"其中 {len(priced)} 条填了价格（均为用户自行记录的历史价，非实时价）："
            f"均价 {round(sum(priced) / len(priced), 2):g} 元、"
            f"最高 {max(priced):g} 元、最低 {min(priced):g} 元。"
        )

    platforms = Counter(row.platform for row in rows if row.platform)
    if platforms:
        top = "、".join(f"{name} {count} 件" for name, count in platforms.most_common(3))
        parts.append(f"常记的购买平台：{top}。")

    recent = [row for row in rows if row.name][:_PROFILE_RECENT]
    if recent:
        listed = "；".join(
            f"{_one_line(row.name, _FOCUS_NAME_CAP)}"
            f"（{row.purchased_at.strftime('%Y-%m-%d') if row.purchased_at else '日期未记'}）"
            for row in recent
        )
        parts.append(f"最近记录：{listed}。")

    return " ".join(parts)[:_PROFILE_CAP]


def summarize_focus(rows: list[PurchaseRecord]) -> str:
    """勾选带入的逐条展开，规格压成 `键:值` 一行。"""
    lines = []
    for row in rows:
        pieces = [_one_line(row.name, _FOCUS_NAME_CAP), row.platform or "平台未记", _format_price(row.price)]
        if row.purchased_at:
            pieces.append(row.purchased_at.strftime("%Y-%m-%d"))
        specs = row.specs or {}
        if specs:
            flat = "、".join(
                f"{_one_line(str(key), 64)}:{_one_line(str(value), 64)}"
                for key, value in list(specs.items())[:10]
            )[:_FOCUS_SPECS_CAP]
            pieces.append(f"规格 {flat}")
        if row.note:
            pieces.append(f"备注 {_one_line(row.note, 80)}")
        lines.append("- " + "｜".join(pieces))
    return "\n".join(lines)[:_FOCUS_CAP]


async def build_purchase_profile(user_id: int) -> str:
    async with async_session_local() as db:
        rows = (
            await db.scalars(
                select(PurchaseRecord)
                .where(PurchaseRecord.user_id == user_id)
                .order_by(PurchaseRecord.create_time.desc(), PurchaseRecord.id.desc())
                .limit(_PROFILE_SCAN)
            )
        ).all()
    return summarize_profile(list(rows))


async def build_record_focus(user_id: int, record_ids: list[int]) -> str:
    """按 id + user_id 取勾选记录。

    数量对不上就报错，**不静默丢弃** —— 悄悄少带一件商品，模型会在残缺上下文上
    像没事一样作答，那比一次 40001 难查得多。
    """
    if not record_ids:
        return ""
    async with async_session_local() as db:
        rows = (
            await db.scalars(
                select(PurchaseRecord).where(
                    PurchaseRecord.user_id == user_id,
                    PurchaseRecord.id.in_(record_ids),
                )
            )
        ).all()
    if len(rows) != len(record_ids):
        found = {row.id for row in rows}
        missing = [record_id for record_id in record_ids if record_id not in found]
        logger.info("chat_record_scope_denied user=%s missing=%s", user_id, missing)
        raise BizError(ErrorCode.PARAM_INVALID, "所选消费记录不存在，请重新勾选")
    return summarize_focus(sorted(rows, key=lambda row: record_ids.index(row.id)))


def compose_context(profile: str, focus: str) -> str:
    """两段拼一块；都没有就返回空串，system 保持原样。"""
    blocks = []
    if focus:
        blocks.append(f"用户本次勾选的商品：\n{focus}")
    if profile:
        blocks.append(f"用户消费概况：\n{profile}")
    return "\n\n".join(blocks)[:_TEXT_CAP]
