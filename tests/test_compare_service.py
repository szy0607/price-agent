"""compare_service 的纯逻辑测试（2026-10-18 阶段 3）。

🔴 **本文件不花钱**：compare_service 只拼 prompt / 解析 JSON / 渲染文本，
不联网。花钱的部分在 compare_specs_service（另有测试，同样全 mock）。
"""

import json

import pytest

from app.services import compare_service as cs

pytestmark = pytest.mark.asyncio


# ---------- 1. prompt：维度必须跟用户问题走 ----------

def test_prompt_focuses_on_user_question():
    """🔴 锁「维度按用户问题定」—— 核心（大宋 22:40 拍板）。

    用户问「戴久了耳朵不舒服」时，prompt 必须把这个说清楚，
    并且**明说不要对比降噪**（否则模型会按品类通用维度来）。
    """
    msgs = cs.build_messages(["索尼", "AirPods"],
                             ["- 索尼｜重量: 250g", "- AirPods｜重量: 61g"],
                             "戴久了耳朵不难受")
    user = msgs[-1]["content"]
    assert "戴久了耳朵不难受" in user
    assert "真正关心的问题" in user
    assert "重量: 250g" in user, "商品参数必须进 prompt"


def test_prompt_degrades_to_category_when_no_question():
    """question 为空 → 退到「按品类通用维度」（三道保险的第三道）。"""
    msgs = cs.build_messages(["索尼", "AirPods"], ["- 索尼｜重量: 250g"], "")
    user = msgs[-1]["content"]
    assert "品类" in user
    assert "真正关心的问题" not in user


def test_prompt_is_all_dicts_not_langchain_objects():
    """🔴 锁「全链路 dict」。

    我第一版用 `HumanMessage` / `SystemMessage`，实测那个会**原样混进**
    项目的 messages 列表（不转），破坏全链路 dict 约定。
    """
    msgs = cs.build_messages(["a", "b"], ["- a｜x: 1"], "q")
    assert all(isinstance(m, dict) for m in msgs), (
        "messages 里出现了非 dict 元素：" + str([type(m).__name__ for m in msgs]))
    assert [m["role"] for m in msgs] == ["system", "user"]


def test_prompt_forbids_total_score():
    """🔴 锁「不给总分」—— 这是选分维度的核心理由（大宋 18:20 拍板）。

    总分会掩盖真实差异：「一个降噪强一个佩戴好」用总分算可能是「打平」。
    """
    system = cs.build_messages(["a", "b"], ["- a"], "q")[0]["content"]
    assert "不要给出" in system
    assert "综合评分" in system or "总分" in system


# ---------- 2. 解析：模型输出不可解析时要降级 ----------

@pytest.mark.parametrize("bad", [
    "",
    "不是 JSON",
    "{断掉的 json",
    "[1,2,3]",              # 是数组不是对象
    None,
])
def test_parse_degrades_on_bad_json(bad):
    """🔴 模型输出不可解析 → **降级**而不是抛。

    抛出去会打断整个图；降级后 decide 还能把「没完成结构化对比」转述给用户。
    """
    result = cs.parse_comparison(bad, ["a", "b"])
    assert result["dimensions"] == []
    assert result["summary"]


def test_parse_handles_markdown_fenced_json():
    """模型有时会包 ```json ... ``` —— 要能剥掉。"""
    raw = '```json\n{"dimensions": [{"name": "重量", "values": {"a": "1g"}, "winner": "a"}], "summary": "a 轻"}\n```'
    result = cs.parse_comparison(raw, ["a"])
    assert len(result["dimensions"]) == 1
    assert result["dimensions"][0]["name"] == "重量"
    assert result["summary"] == "a 轻"


def test_parse_truncates_over_five_dimensions():
    """🔴 维度上限 5（2026-10-18 加）—— 7 个以上手机上要横向滚动。

    模型有时会无视指令给 8 个维度。
    """
    dims = [{"name": f"维度{i}", "values": {"a": "x"}, "winner": None}
            for i in range(8)]
    result = cs.parse_comparison(json.dumps({"dimensions": dims}, ensure_ascii=False), ["a"])
    assert len(result["dimensions"]) == cs.MAX_DIMENSIONS == 5
    assert result["truncated"] is True


# ---------- 3. 渲染：不能凭空造总分 ----------

def test_format_shows_winner_per_dimension():
    result = {
        "dimensions": [
            {"name": "单耳重量", "values": {"索尼": "250g", "AirPods": "61g"},
             "winner": "AirPods"},
            {"name": "续航", "values": {"索尼": "30h", "AirPods": "6h"},
             "winner": None},
        ],
        "summary": "AirPods 更轻",
    }
    text = cs.format_comparison(result)
    assert "单耳重量" in text and "AirPods 占优" in text
    assert "续航" in text and "持平" in text
    assert "参数来源：网络" in text, "必须带来源标记（合规要求）"
    assert "总分" not in text and "综合评分" not in text


def test_format_tells_model_when_degraded():
    """降级时要让 decide 知道「没完成」，别假装成功。"""
    text = cs.format_comparison({"dimensions": [], "summary": "", "raw": "乱七八糟"})
    assert "未能完成结构化对比" in text
    assert "乱七八糟" in text, "原始输出要带上，让 decide 能转述"