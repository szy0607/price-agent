"""【一次性任务脚本 · 2026-10-12 已执行】为历史购物车商品补齐展示图。

性质与背景
----------
- 图片上传链路上线前，cart_item.image 全为空；本脚本为当时存在的
  cart_item（id 3~22，user 13）从公开商品页下载产品图并补齐。
- 一次性任务：已执行完毕，保留作为操作留痕，可随时删除。
- 未纳入 Git 提交；涉及的数据（uploads/ 文件 + 本地库记录）按
  AGENTS.md §3 约定不同步，另一台电脑不会自动获得这些图片。

流程
----
从公开商品页下载图片 → 走 image_store.save_upload_image 重编码
（剥 EXIF、缩最长边 1280、JPEG）落盘 uploads/ → 输出 item_id 映射。
图片落盘后由人工逐张核验，再回写 cart_item.image。

注意事项
--------
- ITEMS 里的图片地址是当时搜索结果，可能随时间失效；换图需重新检索。
- 换机器/换库跑：先确认目标库有对应 cart_item；跑完后需人工核验，
  且**新链路要求图片在 image 表登记**（否则 GET /uploads/{name} 鉴权
  会判「图片不存在」）——补登记请跑 scripts/fix_orphan_images.py。
- 依赖：conda fast 环境 + 本机 MySQL（.env 的 DB_URL）+ 外网。

运行：python scripts/backfill_cart_images.py
"""
import json
import sys

import httpx

sys.path.insert(0, r"F:\price-agent")
from app.services import image_store

# cart_item.id -> 公开商品页图片地址（搜索结果，见对话记录）
ITEMS = {
    3: "https://aka.doubaocdn.com/s/Eof6hOWU8s",    # 苹果 iPhone 16 Pro Max 512G
    4: "https://aka.doubaocdn.com/s/QVIvwBbEVs",    # 索尼 WH-1000XM6 降噪耳机
    5: "https://aka.doubaocdn.com/s/4FzBFU499p",    # 佳能 EOS R50 微单套机
    6: "https://aka.doubaocdn.com/s/d3pWbKXIMf",    # 戴森 V12 Detect Slim 吸尘器
    7: "https://aka.doubaocdn.com/s/cs3uIUKvCY",    # 石头 P10 Pro 扫地机器人
    8: "https://aka.doubaocdn.com/s/QS9VJbUML7",    # 格力 1.5匹 云佳 空调
    9: "https://aka.doubaocdn.com/s/Ue4H9BulWu",    # 九阳 破壁机 L18-Y916
    10: "https://aka.doubaocdn.com/s/YTDT2EHEPo",   # 李宁 韦德之道11 篮球鞋
    11: "https://aka.doubaocdn.com/s/vV1UG2YzlW",   # 威尔胜 NBA 比赛用球
    12: "https://aka.doubaocdn.com/s/2TNxbNg6mh",   # 迪卡侬 公路自行车 RC100
    13: "https://aka.doubaocdn.com/s/432SG5WR6b",   # 《深入理解计算机系统》第3版
    14: "https://aka.doubaocdn.com/s/d7Op5S94Hm",   # 京东京造 泰国乳胶枕
    15: "https://aka.doubaocdn.com/s/NSiJFodHP7",   # 顾家家居 布艺沙发 三人位
    16: "https://aka.doubaocdn.com/s/VSa1zqDCKH",   # 南极人 加绒保暖内衣套装
    17: "https://aka.doubaocdn.com/s/OwlKp4Judj",   # 波司登 极寒系列羽绒服
    18: "https://aka.doubaocdn.com/s/8c0rEvN83V",   # 雅诗兰黛 小棕瓶 第七代 75ml
    19: "https://aka.doubaocdn.com/s/xxqwFiVteQ",   # 欧乐B iO 电动牙刷
    20: "https://aka.doubaocdn.com/s/nwecVnqKhm",   # 三只松鼠 坚果大礼包 30包
    21: "https://aka.doubaocdn.com/s/Zthh4c4PVa",   # 农夫山泉 东方树叶 500ml×15瓶
    22: "https://aka.doubaocdn.com/s/SGN7v3WAgr",   # 小米 米家照片打印机
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}
OUT_MAP = r"F:\price-agent\scripts\_backfill_map.json"


def main() -> None:
    result: dict[str, str] = {}
    with httpx.Client(
        timeout=httpx.Timeout(40.0, connect=10.0),
        follow_redirects=True,
        headers=HEADERS,
    ) as client:
        for item_id, url in ITEMS.items():
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    print(f"FAIL {item_id}: HTTP {resp.status_code} {url}")
                    continue
                rel = image_store.save_upload_image(resp.content, "item.jpg")
            except Exception as exc:  # 网络失败 / 非图片内容都会被这里拦住
                print(f"FAIL {item_id}: {type(exc).__name__}: {exc}")
                continue
            result[str(item_id)] = rel
            print(f"OK {item_id}: {rel} (src {len(resp.content)} bytes)")
    with open(OUT_MAP, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(f"done: {len(result)}/20 saved -> {OUT_MAP}")


if __name__ == "__main__":
    main()
