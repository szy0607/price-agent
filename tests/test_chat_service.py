"""chat_service 纯函数单测。

编排主流程（懒创建/归属校验/落库顺序/模型失败留痕）与路由三件套
（登录/origin/限流）走 DB 探针实测，路线同 chat_repo 第三件验收；
提交级测试随后补（可改造同事那版的 shopper fixture 模式，
原文：git show bc188ce:tests/test_chat_service.py）。
"""
from app.services.chat_service import _fallback_title, _format_item


def test_fallback_title_folds_whitespace_and_strips_punctuation():
    assert _fallback_title("  键盘   选购  ") == "键盘 选购"
    assert _fallback_title("。。。买什么好。。。") == "买什么好"
    assert _fallback_title("，。！？") == "新咨询"
    assert _fallback_title("") == "新咨询"
    assert _fallback_title("长" * 200) == "长" * 100


def test_format_item_folds_name_and_renders_specs():
    line = _format_item("cart", 3, "联想  拯救者\nY9000P", {"品牌": "联想", "型号": "Y9000P"})
    assert line == "cart#3 联想 拯救者 Y9000P｜品牌: 联想；型号: Y9000P"
    assert _format_item("owned", 7, "iPhone 15", {}) == "owned#7 iPhone 15"
    assert _format_item("owned", 7, "iPhone 15", None) == "owned#7 iPhone 15"
