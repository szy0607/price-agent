"""【一次性修复脚本 · 2026-10-12 已执行】清理图片链路改造后的孤儿数据。

性质与背景
----------
- 图片上传链路上线（image 表 + GET /uploads/{name} 鉴权）后，历史图
  未登记导致「有引用但访问被挡、不受生命周期管理」。本脚本做一次性修复。
- 已执行完毕，且已验证幂等（重跑全 0，不重复插入/不误删）；保留留痕，
  可随时删除。未纳入 Git 提交。

四个动作
--------
1. 补登记历史购物车图片：item 表引用 + 文件在 + image 表无行
   -> INSERT image(status='referenced')，归属取引用方商品的 user_id
   （曾误取商品 id，已修；同一图被多 user 引用会抛错留人工处理）。
2. 清理测试残留：image 行无任何 item 引用 -> 删行 + 删对应文件（存在才删）。
3. 清理纯孤儿文件：磁盘文件无 image 行且无 item 引用 -> 删文件。
4. 删除穿越测试数据 cart_item id=23（user 45，「测试穿越」）。

⚠️ 风险提示
-----------
- 动作 2/3/4 是删除操作（数据库行 + 磁盘文件），不可逆；运行前确认
  目标库状态，建议先手动核对一遍。仅对本地库生效，不跨机器。
- 幂等依据：步骤 1 按「无登记行」判断、步骤 2 按「无引用」判断，
  已执行过的库重跑无副作用。

依赖：conda fast 环境 + 本机 MySQL（.env 的 DB_URL）。

运行：python scripts/fix_orphan_images.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, r"F:\price-agent")
from sqlalchemy import delete, select
from app.database.session import async_session_local
from app.models import CartItem, Image, OwnedItem
from app.services import image_store


async def main() -> None:
    async with async_session_local() as s:
        files = {p.name: p for p in image_store.UPLOAD_DIR.glob("*.jpg")}
        img_rows = (await s.execute(select(Image))).scalars().all()
        img_by_path = {r.path: r for r in img_rows}

        cart = (await s.execute(select(CartItem))).scalars().all()
        owned = (await s.execute(select(OwnedItem))).scalars().all()
        item_refs: dict[str, list[tuple[str, int]]] = {}
        for r in cart:
            if r.image:
                item_refs.setdefault(r.image, []).append(("cart", r.user_id))
        for r in owned:
            if r.image:
                item_refs.setdefault(r.image, []).append(("owned", r.user_id))

        # 1) 补登记：有 item 引用 + 文件在 + image 表无行
        inserted = 0
        for path, refs in item_refs.items():
            fname = path.rsplit("/", 1)[-1]
            if path in img_by_path or fname not in files:
                continue
            # 归属取引用方商品所属的 user_id（曾误取商品 id，已修）。
            # 同一张图被多个 user 引用时归属不明，拒绝静默乱写，留人工处理。
            owner_ids = {uid for _, uid in refs}
            if len(owner_ids) != 1:
                raise RuntimeError(
                    f"图片 {path} 被多个 user 的商品引用，归属不明，需人工处理: {owner_ids}")
            user_id = owner_ids.pop()
            s.add(Image(user_id=user_id, path=path, status="referenced"))
            inserted += 1
            print(f"REGISTER {path} -> user_id={user_id} referenced")

        # 2) 清理测试残留：image 行无 item 引用 -> 删行删文件
        removed_rows, removed_files_b = 0, 0
        for row in img_rows:
            if row.path in item_refs:
                continue
            fname = row.path.rsplit("/", 1)[-1]
            if fname in files:
                files[fname].unlink(missing_ok=True)
                removed_files_b += 1
            await s.delete(row)
            removed_rows += 1
            print(f"RELEASE ROW {row.path} (status={row.status})")

        # 3) 纯孤儿文件：磁盘文件无行无引用 -> 删文件
        removed_files_c = 0
        for fname, p in list(files.items()):
            rel = "/uploads/" + fname
            if rel in img_by_path or rel in item_refs:
                continue
            p.unlink(missing_ok=True)
            removed_files_c += 1
            print(f"REMOVE ORPHAN FILE {rel}")

        # 4) 删除穿越测试数据
        result = await s.execute(
            delete(CartItem).where(CartItem.id == 23)
        )
        removed_test = result.rowcount

        await s.commit()
        print()
        print(f"registered={inserted} rows_released={removed_rows} "
              f"files_from_rows={removed_files_b} orphan_files={removed_files_c} "
              f"test_row_deleted={removed_test}")


if __name__ == "__main__":
    asyncio.run(main())
