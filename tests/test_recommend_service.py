"""recommend_service 的测试（2026-10-18 阶段 4 / A5）。

🔴 **本文件的第一职责是「保证不花钱」**：
`search_candidates` 每条搜索 1 次博查（0.036 元），单次推荐 0.1-0.2 元。
所以这里 **全部 mock `web_search` 与 `complete_specs`**，一个真实请求都不发。

顺带锁三件容易出错的事：
1. **搜索词不能含用户隐私**（画像原文不能进搜索词）
2. **排序结果里编造的商品名要被过滤掉**（否则推荐一个不存在的商品）
3. **搜索失败要降级**（不能因为搜不到就让整轮对话失败）
"""

import json

import pytest

from app.services import recommend_service as svc
from app.core.errors import BizError, ErrorCode

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def no_paid_calls(monkeypatch):
    """🔴 拦住唯一会花钱的调用。**没这条 fixture 下面就是真调博查。**"""
    calls = {"search": 0, "specs": 0}

    async def fake_search(query, count=5):
        calls["search"] += 1
        return [{"name": f"候选商品{calls['search']}-{i}", "url": "u",
                 "snippet": "s", "datePublished": "", "summary": None}
                for i in range(2)]

    async def fake_specs(name, category, user_id, session):
        calls["specs"] += 1
        return {"name": name, "price": 999, "specs": {"品牌": "测试"}}

    async def fake_call_model(key, messages, **kw):
        # 搜词那步返回合法 JSON；其余返回排序结果
        if "搜索词" in messages[0]["content"]:
            return (json.dumps({"searches": ["降噪耳机 长续航", "蓝牙耳机 轻便"]},
                               ensure_ascii=False), "m", [])
        return (json.dumps({"items": [{"name": "候选商品1-0", "reason": "偏好续航"}]},
                           ensure_ascii=False), "m", [])

    monkeypatch.setattr(svc.web_search_service, "web_search", fake_search)
    # 🔴 complete_specs 在 `spec_complete_service` 里，**不是** compare_specs_service
    #   （后者只是调用它 + 做格式化）。第一次打桩打错模块，13 个测试全 error。
    monkeypatch.setattr(svc.compare_specs_service.spec_complete_service,
                        "complete_specs", fake_specs)
    monkeypatch.setattr(svc.model_call, "call_model", fake_call_model)
    return calls


class _Key:
    key_id = 1


# ---------- ① 画像 → 搜索词 ----------

async def test_build_searches_from_profile(no_paid_calls):
    searches = await svc.build_searches("偏好长续航降噪", "送人送什么好", _Key())
    assert searches == ["降噪耳机 长续航", "蓝牙耳机 轻便"]
    assert no_paid_calls["search"] == 0, "搜词这一步不该调博查"


async def test_prompt_forbids_leaking_user_history(monkeypatch):
    """🔴 **锁「隐私红线」**：搜索词生成时**必须**禁止把用户具体商品原样写出。

    这是整个 A5 最容易犯且不报错的错——把画像原文发给搜索服务 = 购物数据出境。
    """
    seen = {}

    async def spy(key, messages, **kw):
        seen["system"] = messages[0]["content"]
        return (json.dumps({"searches": ["降噪耳机"]}), "m", [])

    monkeypatch.setattr(svc.model_call, "call_model", spy)
    await svc.build_searches("买过3件索尼耳机，价格 2000 元", "推荐耳机", _Key())
    system = seen["system"]
    assert "原样" in system, "prompt 必须禁止原样转写用户商品"
    assert "隐私" in system, "prompt 必须点明隐私约束"


async def test_build_searches_degrades_on_bad_json(monkeypatch):
    """模型输出不合法 → 返回空列表（不是抛）。"""

    async def bad(key, messages, **kw):
        return ("这不是 JSON", "m", [])

    monkeypatch.setattr(svc.model_call, "call_model", bad)
    assert await svc.build_searches("画像", "问题", _Key()) == []


async def test_build_searches_degrades_on_model_error(monkeypatch):
    """模型报错 → 空列表，调用方自己决定降级（用 question 直接搜）。"""

    async def boom(key, messages, **kw):
        raise RuntimeError("模型挂了")

    monkeypatch.setattr(svc.model_call, "call_model", boom)
    assert await svc.build_searches("画像", "问题", _Key()) == []


# ---------- ② 搜候选 ----------

async def test_search_candidates_dedupes(no_paid_calls):
    """🔴 不同搜索词很容易搜到同一批商品 → 必须按前缀去重。"""
    names = await svc.search_candidates(["耳机", "蓝牙耳机"])
    assert len(names) == len(set(names)), "结果里有重复：" + str(names)


async def test_search_candidates_respects_max(no_paid_calls):
    names = await svc.search_candidates(["耳机"])
    assert len(names) <= svc.MAX_CANDIDATES


async def test_search_candidates_empty_input():
    """空搜索词不调博查（省钱）。"""
    assert await svc.search_candidates([]) == []


async def test_search_failure_returns_empty(monkeypatch):
    """博查报错 → 空列表，不是抛。"""

    async def boom(query, count=5):
        raise BizError(ErrorCode.INTERNAL, "联网搜索失败")

    monkeypatch.setattr(svc.web_search_service, "web_search", boom)
    assert await svc.search_candidates(["耳机"]) == []


async def test_search_skips_too_long_names(monkeypatch):
    """超长 name 多半是网页标题整段，不是商品名。"""

    async def long(query, count=5):
        return [{"name": "超长" * 40, "url": "", "snippet": "",
                 "datePublished": "", "summary": None},
                {"name": "正常商品名", "url": "", "snippet": "",
                 "datePublished": "", "summary": None}]

    monkeypatch.setattr(svc.web_search_service, "web_search", long)
    names = await svc.search_candidates(["q"])
    assert names == ["正常商品名"]


# ---------- ③ 排序 ----------

async def test_parse_ranking_filters_fabricated_names():
    """🔴 **锁「编造的商品名要被过滤」**。

    不过滤的话会给用户推荐一个**不存在的商品** —— 不报错，但推荐是假的。
    """
    raw = json.dumps({"items": [
        {"name": "真实商品A", "reason": "偏好续航"},
        {"name": "根本不存在的商品", "reason": "编的"},
    ]}, ensure_ascii=False)
    out = svc.parse_ranking(raw, ["真实商品A"])
    assert len(out) == 1
    assert out[0]["name"] == "真实商品A"


async def test_parse_ranking_tolerates_spacing():
    """模型可能把「索尼 WH-1000XM5」写成「索尼WH-1000XM5」→ 宽松匹配。"""
    raw = json.dumps({"items": [{"name": "索尼WH-1000XM5", "reason": "r"}]},
                     ensure_ascii=False)
    out = svc.parse_ranking(raw, ["索尼 WH-1000XM5"])
    assert len(out) == 1
    assert out[0]["name"] == "索尼 WH-1000XM5", "应该映射回候选里的规范名"


def test_format_recommendation_marks_source():
    """🔴 合规：推荐必须带「来源：网络」标记（同 ai-draft 的口径）。"""
    text = svc.format_recommendation(
        [{"name": "商品A", "reason": "偏好续航"}],
        {"商品A": {"price": 100, "specs": {}}})
    assert "来源：网络" in text
    assert "商品A" in text
    assert "偏好续航" in text


def test_format_recommendation_tells_model_not_to_fabricate():
    """没排序结果时要明确说「不要编造」。"""
    text = svc.format_recommendation([], {})
    assert "不要编造" in text