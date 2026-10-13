"""智能咨询：把勾选的已购记录展开成上下文，拼成单个 prompt 交给用户的默认模型。

刻意不落库：前端 ChatView 的会话是本地状态，请求里没有 conversation_id，
落库到 chat_message / conversation 要等他那边把会话 id 的口径定下来才接
（见 app/models/chat_message.py 的用途说明）。本模块只负责「这一次问答」。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import PurchaseRecord
from app.schemas.chat_sche import ChatTurnSchema
from app.services import model_call

logger = logging.getLogger(__name__)

_TEMPLATE = """{context}{history}请针对【本轮提问】作答，要求：
1. 只依据以上提供的信息和常识，不要编造具体价格、优惠、库存；
2. 提到已购商品时使用以上给出的名称与价格；
3. 300 字以内，先给结论再给理由，不要复述问题。

【本轮提问】
{question}
"""


async def load_focus_records(user_id: int, record_ids: list[int],
                             session: AsyncSession) -> list[PurchaseRecord]:
    """按登录用户反查勾选的消费记录，保持用户勾选顺序。

    缺任意一条整条请求报错：静默少带一件商品，模型会在残缺上下文上照常作答，
    用户根本看不出少了什么——这个口径沿用被删掉的旧 chat 路由。
    """
    if not record_ids:
        return []
    rows = list((await session.scalars(
        select(PurchaseRecord)
        .where(PurchaseRecord.user_id == user_id, PurchaseRecord.id.in_(record_ids))
    )).all())
    if len(rows) != len(record_ids):
        missing = sorted(set(record_ids) - {row.id for row in rows})
        logger.info("咨询上下文缺记录: user_id=%s missing=%s", user_id, missing)
        raise BizError(ErrorCode.PARAM_INVALID, "勾选的消费记录不存在或不属于你")
    by_id = {row.id: row for row in rows}
    return [by_id[item] for item in record_ids]


def _format_line(row: PurchaseRecord) -> str:
    platform = (row.platform or "").strip() or "平台未记"
    price = "价格未记" if row.price is None else f"{row.price:g}元"
    day = "日期未记" if row.purchased_at is None else row.purchased_at.date().isoformat()
    return f"- {row.name}｜{platform}｜{price}｜购于 {day}"


def compose_prompt(messages: list[ChatTurnSchema], rows: list[PurchaseRecord]) -> str:
    context = ""
    if rows:
        lines = "\n".join(_format_line(row) for row in rows)
        context = f"【用户已购商品（本次咨询指定）】\n{lines}\n\n"

    # call_model 已支持 messages 列表；这里仍把多轮历史摊平进单个 user prompt
    # （改真多轮是后续优化，本次合并 gitee/main 只做签名适配）
    turns = messages[:-1]
    history = ""
    if turns:
        body = "".join(f"{'用户' if item.role == 'user' else '助手'}：{item.content}\n" for item in turns)
        history = f"【最近对话】\n{body}\n"

    return _TEMPLATE.format(context=context, history=history, question=messages[-1].content.strip())


async def answer(user_id: int, messages: list[ChatTurnSchema], record_ids: list[int],
                 session: AsyncSession) -> dict:
    rows = await load_focus_records(user_id, record_ids, session)
    try:
        content, model = await model_call.call_model(
            user_id, [{"role": "user", "content": compose_prompt(messages, rows)}], session)
    except model_call.ModelCallError as exc:
        raise BizError(ErrorCode.INTERNAL, str(exc)) from exc
    return {"content": content, "model": model}
