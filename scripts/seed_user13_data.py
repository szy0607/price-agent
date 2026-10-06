# -*- coding: utf-8 -*-
"""一次性开发测试数据：向 cart_item / owned_item / purchase_record 各插入 20 条 user_id=13 的数据。

设计口径（与 app/repository/cart_repo.py 的 transfer_to_owned_item 保持一致）：
- owned_item 与 purchase_record 配套生成：同一件商品=一条购买流水（同 name/price/specs/platform/purchased_at）
- cart_item 为独立的购物车候选清单（未购买，无 platform/purchased_at）
- create_time / update_time 交给模型默认值（UTC），不手动指定
- 幂等保护：若三张表中 user_id=13 已有数据，脚本直接退出不插入
"""
import asyncio
from datetime import date, datetime, time

from sqlalchemy import select, func

from app.database.session import async_engine, async_session_local
from app.models import CartItem, OwnedItem, PurchaseRecord

USER_ID = 13

# ---------------- 已购商品（owned_item + purchase_record 共用） ----------------
# (name, category, price, specs, platform, purchased_at, note, product_url)
PURCHASED_PRODUCTS = [
    ("苹果 iPhone 15 Pro 256G 原色钛金属", "数码", 8999.0,
     {"颜色": "原色钛金属", "存储": "256GB", "版本": "国行全网通"},
     "京东", date(2026, 1, 12), "官网抢的首发，用到现在很满意", "https://example.com/products/iphone15pro"),
    ("联想拯救者 Y7000P 2026款 i7/16G/512G", "数码", 7999.0,
     {"处理器": "i7-14700H", "内存": "16GB", "硬盘": "512GB SSD"},
     "京东", date(2026, 1, 28), None, None),
    ("罗技 MX Master 3S 无线鼠标", "数码", 699.0,
     {"连接": "蓝牙/2.4G", "颜色": "石墨黑"},
     "京东", date(2026, 2, 14), "办公用，手感不错", None),
    ("华为手环 8 标准版", "数码", 269.0,
     {"颜色": "曜石黑", "表带": "硅胶"},
     "华为商城", date(2026, 2, 25), None, None),
    ("小米空气净化器 4 Pro", "家电", 1299.0,
     {"适用面积": "60㎡", "CADR": "500m³/h"},
     "小米商城", date(2026, 3, 8), "卧室用的，噪音控制不错", None),
    ("海尔 471升 十字四开门冰箱", "家电", 3999.0,
     {"容量": "471L", "能效": "一级", "颜色": "星蕴银"},
     "天猫", date(2026, 3, 19), None, None),
    ("美的 4L 电饭煲 MB-FB40E511", "家电", 299.0,
     {"容量": "4L", "内胆": "麦饭石", "功率": "860W"},
     "京东", date(2026, 4, 2), "蒸饭快，内胆好洗", None),
    ("安踏 氢跑鞋 5.0 男款", "运动户外", 399.0,
     {"尺码": "42", "颜色": "云白", "科技": "氢科技"},
     "淘宝", date(2026, 4, 18), None, None),
    ("斯伯丁 7号 标准篮球", "运动户外", 259.0,
     {"材质": "PU", "规格": "7号", "适用": "室内外通用"},
     "天猫", date(2026, 5, 1), "每周打两次球，耐磨度OK", None),
    ("迪卡侬 羽毛球拍对拍套装", "运动户外", 149.0,
     {"拍重": "85g", "类型": "对拍套装", "附": "2只装"},
     "迪卡侬官网", date(2026, 5, 16), None, None),
    ("《三体》全集（纪念版）", "图书", 96.0,
     {"作者": "刘慈欣", "出版社": "重庆出版社", "册数": "3册"},
     "当当", date(2026, 5, 30), None, "https://example.com/products/santi"),
    ("网易严选 人体工学椅 经典款", "家居", 1599.0,
     {"材质": "网布+铝合金", "调节": "头枕/腰托/扶手", "颜色": "曜黑"},
     "网易严选", date(2026, 6, 11), "久坐程序员必备", None),
    ("苏泊尔 不粘炒锅 32cm", "家居", 189.0,
     {"口径": "32cm", "材质": "铝合金", "涂层": "不粘"},
     "拼多多", date(2026, 6, 24), None, None),
    ("小米米家台灯 Pro", "家居", 249.0,
     {"色温": "2700-6500K", "亮度": "无级调光", "操控": "触控"},
     "小米商城", date(2026, 7, 7), "夜读用，护眼效果可以", None),
    ("优衣库 摇粒绒外套（男）", "服饰", 199.0,
     {"尺码": "L", "颜色": "深灰", "材质": "摇粒绒"},
     "优衣库官网", date(2026, 7, 21), None, None),
    ("兰蔻 小黑瓶精华肌底液 100ml", "美妆个护", 1180.0,
     {"规格": "100ml", "功效": "修护维稳", "适用": "所有肤质"},
     "天猫", date(2026, 8, 3), "送女朋友的生日礼物", None),
    ("飞利浦 电动牙刷 HX6730", "美妆个护", 329.0,
     {"模式": "清洁/敏感/美白", "刷头": "3支装", "续航": "21天"},
     "京东", date(2026, 8, 17), None, None),
    ("蒙牛 特仑苏 纯牛奶 250ml×24盒", "食品", 79.0,
     {"规格": "250ml×24", "蛋白质": "3.6g/100ml", "保质期": "6个月"},
     "天猫超市", date(2026, 8, 30), None, None),
    ("乐高 保时捷911 GT3 RS 积木", "其他", 899.0,
     {"颗粒数": "1580", "比例": "1:8", "适龄": "18+"},
     "天猫", date(2026, 9, 12), "拼了一周，细节很赞", None),
    ("星巴克 经典随行杯 473ml", "其他", 168.0,
     {"容量": "473ml", "材质": "Tritan", "颜色": "鎏金"},
     "京东", date(2026, 9, 25), None, None),
]

# ---------------- 购物车候选清单（cart_item，未购买） ----------------
# (name, category, price, specs, note)
CART_ITEMS = [
    ("苹果 iPhone 16 Pro Max 512G", "数码", 11999.0,
     {"颜色": "沙漠色钛金属", "存储": "512GB", "版本": "国行全网通"},
     "等双11降价再入手"),
    ("索尼 WH-1000XM6 降噪耳机", "数码", 2899.0,
     {"颜色": "铂金银", "降噪": "主动降噪", "续航": "30小时"},
     "和XM5对比过，等评测"),
    ("佳能 EOS R50 微单套机", "数码", 5999.0,
     {"传感器": "APS-C 2420万", "套机镜头": "RF-S 18-45mm", "视频": "4K30P"},
     None),
    ("戴森 V12 Detect Slim 吸尘器", "家电", 3490.0,
     {"吸力": "150AW", "续航": "60分钟", "尘杯": "0.35L"},
     "吸力大，就是价格偏高"),
    ("石头 P10 Pro 扫地机器人", "家电", 3299.0,
     {"导航": "激光导航", "吸力": "7000Pa", "功能": "扫拖一体+自动集尘"},
     None),
    ("格力 1.5匹 新一级能效空调 云佳", "家电", 2999.0,
     {"匹数": "1.5匹", "能效": "新一级", "适用面积": "16-20㎡"},
     "卧室换新空调，等618"),
    ("九阳 破壁机 L18-Y916", "家电", 899.0,
     {"容量": "1.75L", "功率": "1200W", "功能": "豆浆/米糊/果汁"},
     None),
    ("李宁 韦德之道11 篮球鞋", "运动户外", 899.0,
     {"尺码": "43", "科技": "䨻+碳板", "颜色": "黑白"},
     "打球穿，颜值在线"),
    ("威尔胜 NBA 比赛用球", "运动户外", 399.0,
     {"规格": "7号", "材质": "复合皮革", "适用": "室内木地板"},
     None),
    ("迪卡侬 公路自行车 RC100", "运动户外", 1799.0,
     {"车架": "铝合金", "变速": "7速", "尺寸": "M码"},
     "周末骑行计划"),
    ("《深入理解计算机系统》第3版", "图书", 139.0,
     {"作者": "Randal E. Bryant", "出版社": "机械工业出版社", "语言": "中文版"},
     "经典必读，程序员补课"),
    ("京东京造 泰国乳胶枕", "家居", 169.0,
     {"材质": "天然乳胶", "高度": "10-12cm", "枕套": "可拆洗"},
     None),
    ("顾家家居 布艺沙发 三人位", "家居", 3999.0,
     {"规格": "三人位 2.1m", "面料": "科技布", "颜色": "浅灰"},
     "搬新家再买"),
    ("南极人 加绒保暖内衣套装", "服饰", 129.0,
     {"尺码": "L", "颜色": "黑色", "面料": "德绒加绒"},
     None),
    ("波司登 极寒系列羽绒服", "服饰", 1699.0,
     {"尺码": "L", "充绒量": "200g+", "颜色": "曜石黑"},
     "冬天去东北玩需要"),
    ("雅诗兰黛 小棕瓶 第七代 75ml", "美妆个护", 1080.0,
     {"规格": "75ml", "功效": "抗老修护", "适用": "所有肤质"},
     "回购款，等大促"),
    ("欧乐B iO 电动牙刷", "美妆个护", 899.0,
     {"技术": "iO微震科技", "模式": "7种", "刷头": "2支装"},
     None),
    ("三只松鼠 坚果大礼包 30包", "食品", 129.0,
     {"规格": "30包", "内容": "碧根果/夏威夷果/腰果等", "保质期": "9个月"},
     "囤着追剧吃"),
    ("农夫山泉 东方树叶 500ml×15瓶", "食品", 65.0,
     {"规格": "500ml×15", "口味": "茉莉花茶/乌龙茶/青柑普洱混合"},
     None),
    ("小米 米家照片打印机", "其他", 599.0,
     {"打印方式": "热升华", "尺寸": "6英寸", "连接": "WiFi+APP"},
     "旅游照片打印用"),
]


async def main() -> None:
    async with async_session_local() as session:
        # 幂等保护：已有数据则退出
        for model in (CartItem, OwnedItem, PurchaseRecord):
            cnt = await session.scalar(
                select(func.count()).select_from(model).where(model.user_id == USER_ID)
            )
            if cnt:
                print(f"[skip] {model.__tablename__} 已有 user_id={USER_ID} 数据 {cnt} 条，不重复插入")
                return

        # 1) cart_item
        cart_rows = [
            CartItem(user_id=USER_ID, category=c, name=n, price=p, specs=s, note=note)
            for n, c, p, s, note in CART_ITEMS
        ]
        # 2) owned_item + purchase_record（配套生成）
        owned_rows, record_rows = [], []
        for name, category, price, specs, platform, purchased_at, note, product_url in PURCHASED_PRODUCTS:
            owned_rows.append(
                OwnedItem(
                    user_id=USER_ID, category=category, name=name, price=price, specs=specs,
                    platform=platform, purchased_at=purchased_at, note=note,
                )
            )
            record_rows.append(
                PurchaseRecord(
                    user_id=USER_ID, name=name, product_url=product_url, platform=platform,
                    price=price, specs=specs,
                    purchased_at=datetime.combine(purchased_at, time(12, 30)),
                    note=note,
                )
            )

        session.add_all(cart_rows + owned_rows + record_rows)
        await session.commit()

        for model, rows in ((CartItem, cart_rows), (OwnedItem, owned_rows), (PurchaseRecord, record_rows)):
            ids = [r.id for r in rows]
            print(f"[ok] {model.__tablename__}: 插入 {len(rows)} 条, id 范围 {min(ids)}~{max(ids)}")

    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
