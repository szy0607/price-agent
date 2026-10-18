"""compare_specs_service 的测试（2026-10-18 阶段 3）。

🔴 **本文件的第一职责是「保证不花钱」**：
`fetch_specs` 内部每件商品 1 次博查（0.036 元），3 件 = 0.108 元。
所以这里 **全部 mock `complete_specs`**，一个真实请求都不发。

这也意味着**这些测试验不到博查的真实行为**（比如搜索词写法对不对、
博查返回的网页能不能提准参数）。那部分只能手动真跑一次验。
"""

import pytest

from app.services import compare_specs_service as svc
from app.core.errors import BizError, ErrorCode

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_complete_specs(monkeypatch):
    """🔴 拦住唯一会花钱的调用。**没有这条 fixture 下面的测试就会真调博查。"""
    calls = {"n": 0}

    async def fake_complete(name, category, user_id, session):
        calls["n"] += 1
        return {"name": name, "category": category, "price": 100,
                "specs": {"品牌": "测试", "重量": "250g"},
                "model": "fake", "sources": ["https://example.invalid"]}

    monkeypatch.setattr(svc.spec_complete_service, "complete_specs",
                        fake_complete)
    return calls


class _Session:
    pass


# ---------- 1. 基本行为 ----------

async def test_fetch_specs_returns_all_items(mock_complete_specs):
    result = await svc.fetch_specs(["索尼", "AirPods"], 13, _Session())
    assert set(result) == {"索尼", "AirPods"}
    assert result["索尼"]["specs"]["重量"] == "250g"
    assert mock_complete_specs["n"] == 2, "每件商品应查一次"


# ---------- 2. 🔴 单件失败不能拖垮全部 ----------

async def test_one_failure_does_not_kill_all(monkeypatch):
    """🔴 **锁「逐件吞异常」**。

    一件查不到 → 那一件没有结果，**其他件照常返回**。
    如果一失败就整体抛，用户会「三件里查到两件也拿不到对比」。
    """
    async def flaky(name, category, user_id, session):
        if "查不到" in name:
            raise BizError(ErrorCode.INTERNAL, "搜索不到")
        return {"name": name, "price": 1, "specs": {"k": "v"}}

    monkeypatch.setattr(svc.spec_complete_service, "complete_specs", flaky)

    result = await svc.fetch_specs(["好的", "查不到那个", "另一个"], 13, _Session())
    assert set(result) == {"好的", "另一个"}, "只该丢掉失败那件"


async def test_bizerror_is_swallowed(monkeypatch):
    """BizError（博查没配 key / 搜索失败）要转成「查不到」而不是抛。"""
    async def boom(name, category, user_id, session):
        raise BizError(ErrorCode.PARAM_INVALID, "BOCHA_API_KEY 未配置")

    monkeypatch.setattr(svc.spec_complete_service, "complete_specs", boom)
    assert await svc.fetch_specs(["a", "b"], 13, _Session()) == {}


async def test_unexpected_exception_is_swallowed(monkeypatch):
    """非 BizError 的异常（httpx / json 解析）也要吞。"""
    async def boom(name, category, user_id, session):
        raise RuntimeError("json 炸了")

    monkeypatch.setattr(svc.spec_complete_service, "complete_specs", boom)
    assert await svc.fetch_specs(["a"], 13, _Session()) == {}


async def test_empty_items_costs_nothing(mock_complete_specs):
    """空列表不调任何东西 —— 省钱的基本常识，但要测。"""
    assert await svc.fetch_specs([], 13, _Session()) == {}
    assert mock_complete_specs["n"] == 0


# ---------- 3. 渲染成一行 ----------

def test_format_specs_line_keeps_it_short():
    """参数压成一行 —— 对比 prompt 里要放 3 件，太啰嗦会挤掉维度指令。"""
    line = svc.format_specs_line("索尼", {
        "price": 2299, "specs": {"品牌": "索尼", "续航": "30h"}})
    assert line.startswith("- 索尼")
    assert "2299" in line and "续航: 30h" in line
    assert "\n" not in line, "不能换行"


def test_format_specs_line_handles_missing_price_and_specs():
    """资料没查到时是空的 —— 不能抛。"""
    line = svc.format_specs_line("未知商品", {})
    assert line == "- 未知商品"
    line2 = svc.format_specs_line("只有价格", {"price": 50, "specs": {}})
    assert "50" in line2