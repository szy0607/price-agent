# -*- coding: utf-8 -*-
"""比赛 / 部署演示数据脚本（幂等，可重复执行）。

用途：部署到服务器后跑一次，就有【能登录的演示账号 + 完整演示数据】，
比赛现场评委可直接登录体验（智能咨询 / 购物车 / 物品库 / 消费记录 / 购物分组 / 图片上传）。

幂等口径（先查后插，重复执行不产生重复数据、不报错）：
  1. 用户：按 user_email 查，已存在则跳过（不重置密码）
  2. 画像：user_profile 一行一用户（user_id 主键），不存在才建
  3. 演示数据：cart_item / owned_item / purchase_record 三张表中
     该 user_id 任一有数据 → 整组跳过（要重灌需先清掉该用户的数据）

素材复用：购物车 / 已购清单直接复用 scripts/seed_user13_data.py 的数据集
（同一份素材，演示口径与开发测试数据一致，避免两处维护）。

用法（项目根，conda fast 环境）：
    python scripts/seed_demo.py

服务器（Docker Compose 部署后）：
    docker exec -w /app pa-backend python scripts/seed_demo.py
"""
import asyncio
import os
import sys
from datetime import datetime, time
from pathlib import Path

# 无论从哪个目录执行，都能 import 到 app.* 与同目录的 seed_user13_data
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import func, select, update  # noqa: E402

from app.core.key_crypto import encrypt  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database.session import async_engine, async_session_local  # noqa: E402
from app.models import (  # noqa: E402
    CartItem,
    OwnedItem,
    PurchaseRecord,
    User,
    UserApiKey,
    UserEmbeddingKey,
    UserProfile,
)
from seed_user13_data import CART_ITEMS, PURCHASED_PRODUCTS  # noqa: E402

# ════════════════════════════════════════════════════════════════
# 演示账号的模型 key：从环境变量注入（可选，不配则跳过）
# 由部署环境（deploy/.env，经 docker compose env_file 注入容器）提供，
# 两个演示账号共用同一份本地 key，登录即用，无需进设置页配置。
# 注入实现与设置页「新增即默认」口径一致（先清空 is_default 再插新行）。
# ════════════════════════════════════════════════════════════════
MODEL_KEY_ENV = ("DEMO_MODEL_PROVIDER", "DEMO_MODEL_BASE_URL", "DEMO_MODEL_NAME", "DEMO_MODEL_KEY")
EMBEDDING_KEY_ENV = ("DEMO_EMBEDDING_PROVIDER", "DEMO_EMBEDDING_BASE_URL", "DEMO_EMBEDDING_NAME", "DEMO_EMBEDDING_KEY")


def _read_key_env(names: tuple[str, ...]) -> tuple[str, str, str, str] | None:
    """四个环境变量全配齐才生效；缺任何一个都跳过（宁缺毋滥，避免写半截配置）。"""
    vals = [os.getenv(n, "").strip() for n in names]
    if all(vals):
        return tuple(vals)  # type: ignore[return-value]
    return None


async def inject_keys(session, user_id: int) -> None:
    """给演示账号写入默认模型 key（幂等：该用户已有记录则跳过）。"""
    for env_names, model_cls, label in (
        (MODEL_KEY_ENV, UserApiKey, "对话模型"),
        (EMBEDDING_KEY_ENV, UserEmbeddingKey, "向量模型"),
    ):
        cfg = _read_key_env(env_names)
        if cfg is None:
            print(f"[skip] 未配置 {label} key 环境变量（DEMO_*），跳过注入（部署后需在设置页手动配）")
            continue
        existing = await session.scalar(select(model_cls).where(model_cls.user_id == user_id))
        if existing is not None:
            print(f"[skip] user_id={user_id} 已有 {label} key 记录（{existing.provider}/{existing.model_name}），不覆盖")
            continue
        provider, base_url, model_name, key = cfg
        # 与 api_key_service.add_api_key 口径一致：先清空默认，再插新行置默认
        await session.execute(
            update(model_cls).where(model_cls.user_id == user_id).values(is_default=False)
        )
        session.add(model_cls(
            user_id=user_id,
            provider=provider,
            base_url=base_url,
            encrypted_key=encrypt(key),
            key_suffix=key[-4:],
            status="active",
            model_name=model_name,
            is_default=True,
        ))
        print(f"[ok]   user_id={user_id} 写入{label} key：{provider} / {model_name}（后缀 ****{key[-4:]}，已设默认）")


# ════════════════════════════════════════════════════════════════
# 演示账号配置
# 密码固定且符合项目强度规则（长度 6~18、含字母与数字），方便比赛现场登录
# ⚠️ 明文密码只在本脚本创建账号时打印一次；README 与部署文档会再次标注
# ════════════════════════════════════════════════════════════════
DEMO_USERS = [
    {
        "user_email": "demo@example.com",
        "username": "演示账号",
        "password": "Demo2026",
        # 预填画像：聊天每轮会同步注入偏好，演示效果更真实（A6 每轮对话后还会异步更新）
        "profile": {
            "预算偏好": "中高端，注重性价比",
            "常用平台": "京东、天猫",
            "关注品类": "数码、运动、家居",
            "决策风格": "对比参数后理性下单",
        },
    },
    {
        "user_email": "demo2@example.com",
        "username": "演示账号2",
        "password": "Demo2026",
        "profile": {
            "预算偏好": "高性价比为主",
            "常用平台": "拼多多、淘宝",
            "关注品类": "食品、美妆、图书",
            "决策风格": "参考 AI 建议后确认",
        },
    },
]


# 商品展示图：随前端构建产物打包（frontend-web/public/images/products/），
# nginx 直接伺服 /price-agent/images/products/xx.jpg，不依赖后端鉴权，评委可直达。
# 编号顺序 = seed_user13_data 中 CART_ITEMS(01-20) + PURCHASED_PRODUCTS(21-40)。
PRODUCT_IMAGES = {
    # ---- CART_ITEMS（01-20）----
    "苹果 iPhone 16 Pro Max 512G": "01.jpg",
    "索尼 WH-1000XM6 降噪耳机": "02.jpg",
    "佳能 EOS R50 微单套机": "03.jpg",
    "戴森 V12 Detect Slim 吸尘器": "04.jpg",
    "石头 P10 Pro 扫地机器人": "05.jpg",
    "格力 1.5匹 新一级能效空调 云佳": "06.jpg",
    "九阳 破壁机 L18-Y916": "07.jpg",
    "李宁 韦德之道11 篮球鞋": "08.jpg",
    "威尔胜 NBA 比赛用球": "09.jpg",
    "迪卡侬 公路自行车 RC100": "10.jpg",
    "《深入理解计算机系统》第3版": "11.jpg",
    "京东京造 泰国乳胶枕": "12.jpg",
    "顾家家居 布艺沙发 三人位": "13.jpg",
    "南极人 加绒保暖内衣套装": "14.jpg",
    "波司登 极寒系列羽绒服": "15.jpg",
    "雅诗兰黛 小棕瓶 第七代 75ml": "16.jpg",
    "欧乐B iO 电动牙刷": "17.jpg",
    "三只松鼠 坚果大礼包 30包": "18.jpg",
    "农夫山泉 东方树叶 500ml×15瓶": "19.jpg",
    "小米 米家照片打印机": "20.jpg",
    # ---- PURCHASED_PRODUCTS（21-40）----
    "苹果 iPhone 15 Pro 256G 原色钛金属": "21.jpg",
    "联想拯救者 Y7000P 2026款 i7/16G/512G": "22.jpg",
    "罗技 MX Master 3S 无线鼠标": "23.jpg",
    "华为手环 8 标准版": "24.jpg",
    "小米空气净化器 4 Pro": "25.jpg",
    "海尔 471升 十字四开门冰箱": "26.jpg",
    "美的 4L 电饭煲 MB-FB40E511": "27.jpg",
    "安踏 氢跑鞋 5.0 男款": "28.jpg",
    "斯伯丁 7号 标准篮球": "29.jpg",
    "迪卡侬 羽毛球拍对拍套装": "30.jpg",
    "《三体》全集（纪念版）": "31.jpg",
    "网易严选 人体工学椅 经典款": "32.jpg",
    "苏泊尔 不粘炒锅 32cm": "33.jpg",
    "小米米家台灯 Pro": "34.jpg",
    "优衣库 摇粒绒外套（男）": "35.jpg",
    "兰蔻 小黑瓶精华肌底液 100ml": "36.jpg",
    "飞利浦 电动牙刷 HX6730": "37.jpg",
    "蒙牛 特仑苏 纯牛奶 250ml×24盒": "38.jpg",
    "乐高 保时捷911 GT3 RS 积木": "39.jpg",
    "星巴克 经典随行杯 473ml": "40.jpg",
}


def _product_image(name: str) -> str | None:
    """商品展示图相对 URL（随前端静态伺服），未配图返回 None（前端用占位图兜底）。"""
    fname = PRODUCT_IMAGES.get(name)
    return f"/price-agent/images/products/{fname}" if fname else None


async def seed_user(session, spec: dict) -> None:
    """单个演示账号：建用户（幂等）→ 建画像（幂等）→ 灌演示数据（幂等）。"""
    email = spec["user_email"]

    # ── 1) 用户（先查后插）──
    user = await session.scalar(select(User).where(User.user_email == email))
    if user is None:
        user = User(
            user_email=email,
            username=spec["username"],
            password_hash=hash_password(spec["password"]),
        )
        session.add(user)
        await session.flush()  # 拿自增 id
        print(f"[ok]   创建用户：{email}（username={spec['username']}，id={user.id}）")
        print(f"[info] 密码：{spec['password']}（比赛现场登录用）")
    else:
        print(f"[skip] 用户已存在：{email}（id={user.id}，不重置密码）")

    # ── 2) 用户画像（user_id 主键，不存在才建）──
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        session.add(UserProfile(user_id=user.id, preferences=spec["profile"]))
        print(f"[ok]   创建画像：user_id={user.id}")
    else:
        print(f"[skip] 画像已存在：user_id={user.id}")

    # ── 3) 模型 key 注入（演示账号直接可用本地 key；幂等，已有则跳过）──
    await inject_keys(session, user.id)

    # ── 4) 演示数据（三张表任一有数据 → 整组跳过，防重复）──
    for model in (CartItem, OwnedItem, PurchaseRecord):
        cnt = await session.scalar(
            select(func.count()).select_from(model).where(model.user_id == user.id)
        )
        if cnt:
            print(f"[skip] user_id={user.id} 的 {model.__tablename__} 已有 {cnt} 条，跳过数据插入")
            return

    # 3.1) 购物车候选清单（未购买，无 platform / purchased_at）
    cart_rows = [
        CartItem(user_id=user.id, category=c, name=n, price=p, specs=s, note=note, image=_product_image(n))
        for n, c, p, s, note in CART_ITEMS
    ]
    # 3.2) 物品库 + 消费记录（同一件商品配套生成，口径与 transfer_to_owned_item 一致）
    owned_rows, record_rows = [], []
    for name, category, price, specs, platform, purchased_at, note, product_url in PURCHASED_PRODUCTS:
        owned_rows.append(
            OwnedItem(
                user_id=user.id, category=category, name=name, price=price, specs=specs,
                platform=platform, purchased_at=purchased_at, note=note, image=_product_image(name),
            )
        )
        record_rows.append(
            PurchaseRecord(
                user_id=user.id, name=name, product_url=product_url, platform=platform,
                price=price, specs=specs,
                purchased_at=datetime.combine(purchased_at, time(12, 30)),
                note=note,
            )
        )

    session.add_all(cart_rows + owned_rows + record_rows)
    await session.flush()
    print(
        f"[ok]   user_id={user.id} 演示数据："
        f"cart {len(cart_rows)} 条 / owned {len(owned_rows)} 条 / purchase {len(record_rows)} 条"
    )


async def main() -> None:
    async with async_session_local() as session:
        for spec in DEMO_USERS:
            await seed_user(session, spec)
        await session.commit()
        print("----")
        print("演示账号就绪（幂等脚本，重复执行只会 skip，不会产生重复数据）")
        print("提示：DEMO_MODEL_* / DEMO_EMBEDDING_* 环境变量已注入时，演示账号登录即可直接聊天/RAG 检索")
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
