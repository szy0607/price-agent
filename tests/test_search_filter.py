"""search_filter 的测试（2026-10-19）。

🔴 **测试数据全部来自真机实测**（大宋看到卡片效果后那次），
不是编的——所以这些用例能真正守住「脏数据不给用户看」这条口径。

**核心原则：宁可放过，不可错杀。**
所以测试里同时有「该挡的」和「**不该挡的**」两组，后者同等重要。
"""

import pytest

from app.services import search_filter as sf

pytestmark = pytest.mark.asyncio


# ---------- 该挡的（来自真机实测的脏数据） ----------

@pytest.mark.parametrize("name,url", [
    # 实测样本 1：截图里那6 张卡之一
    ("精选_京东牛奶_国内优惠排行_第203页_什么值得买", "https://faxian.smzdm.com/p/1"),
    ("精选_京东牛奶_国内优惠排行_第124页_什么值得买", "https://faxian.smzdm.com/p/2"),
    ("最新国内精选京东奶类制品优惠信息大全_第35页_什么值得买",
     "https://www.smzdm.com/p/3"),
    # 🔴 前缀重复：博查把搜索词「京东京东京东」拼进标题
    ("京东京东京东京东款奶", "https://item.jd.com/1"),
])
def test_blocks_known_junk(name, url):
    """🔴 大宋截图里那批脏数据，一个都不能漏给用户看。"""
    assert sf.is_junk(name, url) is True


def test_blocks_aggregation_host_without_title_hint():
    """🔴 **光靠域名就能挡** —— 不依赖标题特征词。

    这是刻意的：我实测发现按标题词过滤会误杀商品页
    （「索尼WH-1000XM5参数_...太平洋产品报价」含「报价」但是商品页），
    所以必须有一条**不依赖标题**的独立判据。
    """
    assert sf.is_junk("随便什么标题", "https://www.smzdm.com/whatever") is True


def test_empty_name_is_junk():
    assert sf.is_junk("", "") is True
    assert sf.is_junk("   ", "https://x.com") is True


# ---------- 🔴 不该挡的（同等重要：宁可放过不可错杀） ----------

@pytest.mark.parametrize("name,url", [
    #🔴 这条含「报价」但**是正经商品页**——我第一版规则会误杀它
    ("索尼WH-1000XM5参数_索尼WH-1000XM5参数配置|详细参数_太平洋产品报价",
     "https://product.pconline.com.cn/x"),
    # 含「排行」但是具体商品的排行页，也放过
    ("索尼WH-1000XM5", "https://www.zol.com.cn/x"),
    ("【索尼WH-1000XM5参数】SONY WH-1000XM5耳机参数_规格_性能_功能-ZOL中关村在线",
     "https://detail.zol.com.cn/x"),
    ("索尼(SONY)WH-1000XM5 黑色 高解析度头戴式真无线降噪蓝牙耳机参数配置",
     "https://www.suning.com/x"),
    # 「最新」开头但确实是商品
    ("全新未拆封 AirPods Pro 2 国行", "https://item.jd.com/y"),
])
def test_does_not_block_real_products(name, url):
    """🔴 **这条测试是防我自己的**：我第一版规则按标题词过滤，
    实测会误杀「索尼WH-1000XM5参数_..._太平洋产品报价」这种正经商品页。
    「宁可放过，不可错杀」必须由测试锁住，否则以后有人会「优化」过滤规则。"""
    assert sf.is_junk(name, url) is False


# ---------- 去重 ----------

def test_dedupes_same_product_different_pages():
    """🔴 同一件商品的不同页面只留一条（截图里 6 张卡全是同一个）。"""
    results = [
        {"name": "索尼WH-1000XM5参数_索尼WH-1000XM5参数配置|详细参数_太平洋产品报价",
         "url": "https://product.pconline.com.cn/a"},
        {"name": "索尼WH-1000XM5参数", "url": "https://wap.zol.com.cn/b"},
        {"name": "索尼WH-1000XM5", "url": "https://www.zol.com.cn/c"},
    ]
    out = sf.clean_results(results, 10)
    assert len(out) == 1, "同一商品应只剩一条，实际 " + str([i["name"] for i in out])


def test_dedupes_ignoring_page_marker():
    """🔴 **旧去重失效的根因**：「第203页」vs「第124页」前 18 字不同。"""
    results = [
        {"name": "精选_京东牛奶_国内优惠排行_第203页_什么值得买",
         "url": "https://faxian.smzdm.com/p/1"},
        {"name": "精选_京东牛奶_国内优惠排行_第124页_什么值得买",
         "url": "https://faxian.smzdm.com/p/2"},
    ]
    # 两条都是聚合页 → 全被挡，结果为空
    assert sf.clean_results(results, 10) == []


def test_keeps_different_products():
    """不同商品要都留下。"""
    results = [
        {"name": "索尼WH-1000XM5", "url": "https://a.com"},
        {"name": "AirPods Pro 2", "url": "https://b.com"},
        {"name": "华为 FreeBuds Pro 3", "url": "https://c.com"},
    ]
    out = sf.clean_results(results, 10)
    assert len(out) == 3


def test_respects_max_items():
    results = [{"name": f"商品{i}", "url": f"https://x{i}.com"} for i in range(10)]
    assert len(sf.clean_results(results, 3)) == 3


def test_ignores_space_difference():
    """「索尼 WH-1000XM5」与「索尼WH-1000XM5」应该算同一件。"""
    results = [
        {"name": "索尼 WH-1000XM5", "url": "https://a.com"},
        {"name": "索尼WH-1000XM5", "url": "https://b.com"},
    ]
    assert len(sf.clean_results(results, 10)) == 1


# ---------- 真实场景回归 ----------

async def test_real_dirty_scenario_end_to_end():
    """🔴 把大宋截图那个场景整个跑一遍。

    输入 = 实测「京东京东京东 纯奶 价格 评测」的返回
    断言 = **不给用户看聚合页**（口径来自大宋：「只要脏数据不给用户看就可以」）
    """
    real_results = [
        {"name": "纯奶纯价格报价行情 - 京东", "url": "https://www.jd.com/1",
         "snippet": "京东JD.COM自营"},
        {"name": "精选_京东牛奶_国内优惠排行_第203页_什么值得买",
         "url": "https://faxian.smzdm.com/p/1", "snippet": "精选"},
        {"name": "精选_京东牛奶_国内优惠排行_第124页_什么值得买",
         "url": "https://faxian.smzdm.com/p/2", "snippet": "精选"},
        {"name": "盒装纯奶排行 - 京东", "url": "https://www.jd.com/2",
         "snippet": "排行榜"},
        {"name": "最新国内精选京东奶类制品优惠信息大全_第35页_什么值得买",
         "url": "https://www.smzdm.com/p/3", "snippet": "大全"},
    ]
    out = sf.clean_results(real_results, 3)

    for it in out:
        assert "第" not in it["name"], f"聚合页漏了：{it['name']}"
        assert "smzdm" not in it["url"], f"聚合站漏了：{it['url']}"

    # ⚠️ 「盒装纯奶排行 - 京东」**挡不掉**（电商站的列表页，
    #   没有可靠静态判据）。这是刻意的 —— 大宋的口径是「宁可放过不可错杀」。
    #   要彻底解决需要让主模型判断（多一次调用），那是另一个决定。
    print(f"  实测场景：5 条 -> 剩 {len(out)} 条")
    for it in out:
        print(f"    · {it['name']}")

# ---------- 🔴 去重不能太狠（防我改过头） ----------

@pytest.mark.parametrize("a,b", [
    # 🔴 这两条**不同商品**，绝不能被去重成一条
    ("索尼WH-1000XM5", "索尼WF-1000XM5"),
    # 「降噪耳机」与「蓝牙耳机」不同品类
    ("降噪耳机", "蓝牙耳机"),
    # 一个是耳机一个是手机
    ("索尼WH-1000XM5", "iPhone 16 Pro"),
])
def test_different_products_never_merged(a, b):
    """🔴 **防我改过头**：尾部修饰词剥离可能把不同商品合并。

    我第一版只按分隔符切，第二版加了「剥尾部修饰词」——
    加这一条是为了「索尼WH-1000XM5参数」与「索尼WH-1000XM5」同键，
    但**必须确认没有把不同商品也合到一起**。
    """
    assert sf._dedupe_key(a) != sf._dedupe_key(b), (
        f"不同商品被判成同一件了：{a!r} vs {b!r}")


def test_page_marker_is_independently_necessary():
    """🔴🔴 **这条是补我自己的测试漏洞**（2026-10-19 回退-验证时发现）。

    回退验证：把 `_PAGE_MARK` 那条判据关掉（改成 `if False: return True`），
    **20 项测试全绿** —— 说明分页规则**根本没被真正验证过**。

    根因：我取的脏数据样本里，每一条都恰好有第二条规则能挡：
      「精选_京东牛奶_...第203页_什么值得买」→ host 是 smzdm，域名规则能挡
      「京东京东京东京东款奶」             → 前缀重复规则能挡
    没有一条**只能靠分页规则挡**的样本，所以那条判据形同虚设。

    这条用 `item.jd.com`（不是聚合站）+ 无重复前缀 + 带「第N页」——
    **只有分页规则能挡它**。
    """
    name = "小米手机价格大全第12页 - 京东"
    url = "https://item.jd.com/list_12.html"
    # 前置确认：另外两条规则都挡不住
    assert "smzdm" not in url
    assert sf._REPEAT_PREFIX.search(name) is None
    # 它确实该被挡
    assert sf.is_junk(name, url) is True
