"""物品 → embedding 切片的纯函数。

口径（10-06 拍板）：name + specs 拼接 + note 压一段文本。
PG 副本的 content 列、将来存量回填脚本，都从这里出文本，保证
「写进去的」和「查的时候比的」永远是同一种拼法。
"""


def _flatten(value) -> str:
    """任意值压成单行文本：None → 空串；内部空白（含换行）全部折叠成单空格。"""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = str(value)
    return " ".join(str(value).split())


def build_item_text(name: str, specs: dict | None, note: str | None) -> str:
    """把一件物品压成一段用于向量化的文本。

    name 为主干，specs 按键拼成「k: v；k: v」，note 附在末尾；
    三段都可能为空，全空则返回空串（调用方应跳过向量化）。
    """
    parts: list[str] = []
    head = _flatten(name)
    if head:
        parts.append(head)
    if specs:
        pairs = [f"{_flatten(k)}: {_flatten(v)}" for k, v in specs.items()]
        pairs = [p for p in pairs if not p.endswith(": ")]  # 值为空的键整个丢掉
        if pairs:
            parts.append("；".join(pairs))
    tail = _flatten(note)
    if tail:
        parts.append(tail)
    return " ".join(parts)
