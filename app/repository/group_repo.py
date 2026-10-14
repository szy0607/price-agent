"""购物分组的数据访问层。

归属校验口径与全项目一致：user_id 只从 CurrentUser 取，任何按 id 的读写都先验
「这条记录是这个用户的」，别人的 id 一律回「分组不存在 / 物品不存在」，
不给出「存在但不属于你」这种可枚举的差别。
"""

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.models import CartItem, ItemGroup, ItemGroupRef, OwnedItem
from app.schemas.group_sche import ItemGroupInSchema, ItemGroupUpdateSchema, GroupRefInSchema

# item_type 只存这两个值，与 ItemGroupRef 模型注释同口径
CART = "cart"
OWNED = "owned"


def _round_money(value) -> float:
    """金额统一 2 位：Float 列直接 sum 会累加出 1699.9999999999 这种尾巴。"""
    return round(float(value or 0), 2)


def _zone_stats(items: list) -> tuple[int, int, float]:
    """一区（已购买/未购买）的统计：(数量, 未填价数量, 金额合计)。"""
    priced = [i.price for i in items if i.price is not None]
    return len(items), sum(1 for i in items if i.price is None), _round_money(sum(priced))


async def _load_group(group_id: int, user_id: int, session: AsyncSession) -> ItemGroup:
    group = await session.scalar(
        select(ItemGroup).where(ItemGroup.id == group_id, ItemGroup.user_id == user_id)
    )
    if group is None:
        raise BizError(ErrorCode.PARAM_INVALID, "分组不存在")
    return group


async def _load_item(item_type: str, item_id: int, user_id: int, session: AsyncSession):
    model = CartItem if item_type == CART else OwnedItem
    item = await session.scalar(
        select(model).where(model.id == item_id, model.user_id == user_id)
    )
    if item is None:
        raise BizError(ErrorCode.PARAM_INVALID, "物品不存在")
    return item


async def create_group(group_in: ItemGroupInSchema, user_id: int, session: AsyncSession) -> ItemGroup:
    group = ItemGroup(**group_in.model_dump(), user_id=user_id)
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def update_group(update_in: ItemGroupUpdateSchema, group_id: int, user_id: int,
                       session: AsyncSession) -> ItemGroup:
    group = await _load_group(group_id, user_id, session)
    for key, value in update_in.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    await session.commit()
    await session.refresh(group)
    return group


async def delete_group(group_id: int, user_id: int, session: AsyncSession) -> None:
    """删分组只删分组本身和成员关系，物品始终不动。"""
    await _load_group(group_id, user_id, session)
    await session.execute(delete(ItemGroupRef).where(ItemGroupRef.group_id == group_id))
    await session.execute(delete(ItemGroup).where(ItemGroup.id == group_id))
    await session.commit()


async def list_groups(user_id: int, session: AsyncSession) -> list[dict]:
    """分组列表 + 每组的价格统计。

    价格按物品表 JOIN 聚合（每条分组两段 SUM），不按分组循环查物品——
    否则 20 个分组就是 40 次查询。JOIN 上带 user_id 条件，双保险。
    """
    groups = list((await session.scalars(
        select(ItemGroup)
        .where(ItemGroup.user_id == user_id)
        .order_by(ItemGroup.update_time.desc())
    )).all())
    if not groups:
        return []

    group_ids = [g.id for g in groups]
    agg: dict[int, dict] = {gid: {} for gid in group_ids}
    for item_type, model in ((CART, CartItem), (OWNED, OwnedItem)):
        rows = await session.execute(
            select(
                ItemGroupRef.group_id,
                func.count(),
                func.coalesce(func.sum(model.price), 0),
                func.sum(case((model.price.is_(None), 1), else_=0)),
            )
            .join(model, model.id == ItemGroupRef.item_id)
            .where(
                ItemGroupRef.item_type == item_type,
                ItemGroupRef.group_id.in_(group_ids),
                model.user_id == user_id,
            )
            .group_by(ItemGroupRef.group_id)
        )
        for group_id, count, total, unpriced in rows:
            agg[group_id][item_type] = (count, unpriced or 0, _round_money(total))

    result = []
    for g in groups:
        cart = agg[g.id].get(CART, (0, 0, 0.0))
        owned = agg[g.id].get(OWNED, (0, 0, 0.0))
        result.append({
            "id": g.id,
            "user_id": g.user_id,
            "name": g.name,
            "note": g.note,
            "create_time": g.create_time,
            "update_time": g.update_time,
            "unpurchased_count": cart[0],
            "purchased_count": owned[0],
            "unpriced_count": cart[1] + owned[1],
            "unpurchased_total": cart[2],
            "purchased_total": owned[2],
            "total": _round_money(cart[2] + owned[2]),
        })
    return result


async def get_group_detail(group_id: int, user_id: int, session: AsyncSession) -> dict:
    """分组详情：已购买（owned）/ 未购买（cart）两区 + 统计。

    两区顺序按加入时间倒序（ref.create_time），最近加进来的排前面。
    """
    group = await _load_group(group_id, user_id, session)
    refs = list((await session.scalars(
        select(ItemGroupRef)
        .where(ItemGroupRef.group_id == group_id)
        .order_by(ItemGroupRef.create_time.desc(), ItemGroupRef.id.desc())
    )).all())

    cart_ids = [r.item_id for r in refs if r.item_type == CART]
    owned_ids = [r.item_id for r in refs if r.item_type == OWNED]
    cart_items: dict[int, CartItem] = {}
    owned_items: dict[int, OwnedItem] = {}
    if cart_ids:
        cart_items = {i.id: i for i in (await session.scalars(
            select(CartItem).where(CartItem.id.in_(cart_ids), CartItem.user_id == user_id)
        )).all()}
    if owned_ids:
        owned_items = {i.id: i for i in (await session.scalars(
            select(OwnedItem).where(OwnedItem.id.in_(owned_ids), OwnedItem.user_id == user_id)
        )).all()}

    # ref 指向的物品已被删（钩子漏网）时跳过，不在分组里展示幽灵
    unpurchased = [cart_items[r.item_id] for r in refs if r.item_type == CART and r.item_id in cart_items]
    purchased = [owned_items[r.item_id] for r in refs if r.item_type == OWNED and r.item_id in owned_items]

    cart_count, cart_unpriced, cart_total = _zone_stats(unpurchased)
    owned_count, owned_unpriced, owned_total = _zone_stats(purchased)
    return {
        "group": group,
        "unpurchased": unpurchased,
        "purchased": purchased,
        "stats": {
            "unpurchased_count": cart_count,
            "purchased_count": owned_count,
            "unpriced_count": cart_unpriced + owned_unpriced,
            "unpurchased_total": cart_total,
            "purchased_total": owned_total,
            "total": _round_money(cart_total + owned_total),
        },
    }


async def add_group_item(ref_in: GroupRefInSchema, group_id: int, user_id: int,
                         session: AsyncSession) -> ItemGroupRef:
    await _load_group(group_id, user_id, session)
    await _load_item(ref_in.item_type, ref_in.item_id, user_id, session)
    # 唯一约束兜底之前先查一遍：给用户一句人话，而不是 IntegrityError 变 500
    exists = await session.scalar(
        select(ItemGroupRef.id).where(
            ItemGroupRef.group_id == group_id,
            ItemGroupRef.item_type == ref_in.item_type,
            ItemGroupRef.item_id == ref_in.item_id,
        )
    )
    if exists is not None:
        raise BizError(ErrorCode.PARAM_INVALID, "该物品已在分组中")
    ref = ItemGroupRef(group_id=group_id, item_type=ref_in.item_type, item_id=ref_in.item_id)
    session.add(ref)
    await session.commit()
    await session.refresh(ref)
    return ref


async def remove_group_item(item_type: str, item_id: int, group_id: int, user_id: int,
                            session: AsyncSession) -> None:
    await _load_group(group_id, user_id, session)
    result = await session.execute(
        delete(ItemGroupRef).where(
            ItemGroupRef.group_id == group_id,
            ItemGroupRef.item_type == item_type,
            ItemGroupRef.item_id == item_id,
        )
    )
    if result.rowcount == 0:
        raise BizError(ErrorCode.PARAM_INVALID, "该物品不在分组中")
    await session.commit()


async def repoint_refs_on_transfer(old_item_id: int, new_item_id: int, session: AsyncSession) -> None:
    """标记购买时由 cart_repo.transfer_to_owned_item 在同一个事务里调用。

    把分组里指向旧 cart_item 的引用改指向新 owned_item，分组里该物品随之从
    「未购买」区翻到「已购买」区。物品不在任何分组时直接返回，不产生额外查询。

    先删再改，不能合成一条 DELETE ... WHERE group_id IN (SELECT ... FROM 同表)：
    MySQL 报 1093（不能对正在删的表在 FROM 子句里再选它）。拆成两步绕开。
    先删的是会撞唯一约束的既有 owned 引用（用户曾把同一物品以 owned 身份
    加进同组）——不删的话同一物品在组里出现两条，详情页重复展示。
    """
    group_ids = list((await session.scalars(
        select(ItemGroupRef.group_id).where(
            ItemGroupRef.item_type == CART, ItemGroupRef.item_id == old_item_id
        )
    )).all())
    if not group_ids:
        return
    await session.execute(
        delete(ItemGroupRef).where(
            ItemGroupRef.item_type == OWNED,
            ItemGroupRef.item_id == new_item_id,
            ItemGroupRef.group_id.in_(group_ids),
        )
    )
    await session.execute(
        update(ItemGroupRef)
        .where(ItemGroupRef.item_type == CART, ItemGroupRef.item_id == old_item_id)
        .values(item_type=OWNED, item_id=new_item_id)
    )


async def delete_refs_by_item(item_type: str, item_id: int, session: AsyncSession) -> None:
    """删物品时由 cart_repo / owned_repo 在同一个事务里调用：关系随物品一起走。"""
    await session.execute(
        delete(ItemGroupRef).where(
            ItemGroupRef.item_type == item_type, ItemGroupRef.item_id == item_id
        )
    )
