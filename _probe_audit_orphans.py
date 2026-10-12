# -*- coding: utf-8 -*-
"""一次性审计探针：image 表 / item 表引用 / uploads/ 文件三方交叉。跑完即弃。"""
import asyncio
from pathlib import Path

from sqlalchemy import select, func

from app.database.session import async_session_local
from app.models import CartItem, Image, OwnedItem
from app.services import image_store

UPLOAD_DIR = image_store.UPLOAD_DIR


async def main() -> None:
    async with async_session_local() as db:
        images = list((await db.scalars(select(Image).order_by(Image.id))).all())
        cart_imgs = list((await db.scalars(
            select(CartItem).where(CartItem.image.is_not(None)))).all())
        owned_imgs = list((await db.scalars(
            select(OwnedItem).where(OwnedItem.image.is_not(None)))).all())

        # 路径 -> 引用它的 item（user_id, 表, id）
        refs: dict[str, list[str]] = {}
        for it in cart_imgs:
            refs.setdefault(it.image, []).append(f"cart#{it.id}(u{it.user_id})")
        for it in owned_imgs:
            refs.setdefault(it.image, []).append(f"owned#{it.id}(u{it.user_id})")

        print(f"=== image 表 {len(images)} 行 ===")
        for row in images:
            path = UPLOAD_DIR / Path(row.path).name
            file_ok = path.is_file()
            r = refs.get(row.path, [])
            print(f"  id={row.id} u={row.user_id} {row.status:10s} "
                  f"文件={'在' if file_ok else '不在'} 引用={r or '无'} {row.path}")

        print(f"\n=== item 表带 image 的行 {len(cart_imgs) + len(owned_imgs)} 条 ===")
        image_paths = {row.path for row in images}
        for it in cart_imgs + owned_imgs:
            registered = "已登记" if it.image in image_paths else "未登记"
            print(f"  {registered} {it.image}  <- {it.id} u{it.user_id}")

        print(f"\n=== uploads/ 文件 {len(list(UPLOAD_DIR.glob('*.jpg')))} 个 ===")
        on_disk = {f"/uploads/{p.name}" for p in UPLOAD_DIR.glob("*.jpg")}
        db_paths = {row.path for row in images}
        pure_orphans = on_disk - db_paths - set(refs.keys())
        print(f"  纯孤儿（盘上+无行+无引用）: {len(pure_orphans)} 个")
        for p in sorted(pure_orphans):
            print(f"    {p}")
        no_file = [row.path for row in images
                   if not (UPLOAD_DIR / Path(row.path).name).is_file()]
        print(f"  悬空登记（有行+无文件）: {len(no_file)} 个")


asyncio.run(main())
