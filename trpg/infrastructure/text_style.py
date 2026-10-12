"""
QQ 移动端文本排版规范与工具函数

所有面向玩家的多行输出都应通过这里的函数拼装，保证风格一致：
- 标题统一用【标题】，不用 ===
- 每行一件事，宽度不超过 LINE_WIDTH 个汉字（按东亚字宽计算），超长时在字段边界换行
- 不靠补空格对齐；列表当前项前加 ●，其余项不加任何标记
- 键值对用全角冒号：；变化量带正负号；前后对比写作 30→15（箭头两侧不加空格）
- 分隔用空行或 DIVIDER；符号只用 ● → ×
- 错误两行：第一行写问题，第二行写「用法：.xx ...」；补充说明放在最后一行「提示：...」
"""

import unicodedata
from collections.abc import Iterable

LINE_WIDTH = 18
MAX_LIST_LINES = 15
DIVIDER = "──────"
ACTIVE_MARK = "●"
ARROW = "→"

# 字段边界：优先在这些字符之后换行
_BREAK_AFTER = " ，,、；;/|）)"
_BREAK_BEFORE = "（("


def char_width(ch: str) -> int:
    """单个字符的显示宽度（半角为 1，全角为 2；宽度不确定的符号按全角计，宁宽勿窄）"""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1


def display_width(text: str) -> int:
    """文本的显示宽度（半角单位）"""
    return sum(char_width(ch) for ch in text)


def fits(line: str, width: int = LINE_WIDTH) -> bool:
    """一行是否不超过 width 个汉字宽"""
    return display_width(line) <= width * 2


def title(text: str, extra: str = "") -> str:
    """标题行：【text】extra"""
    return f"【{text}】{extra}"


def kv(key: str, value) -> str:
    """键值对：key：value"""
    return f"{key}：{value}"


def item(index: int | str, text: str, active: bool = False) -> str:
    """列表项：当前项前加 ●，序号后接一个空格"""
    return f"{ACTIVE_MARK if active else ''}{index}. {text}"


def delta(old, new) -> str:
    """前后对比：old→new"""
    return f"{old}{ARROW}{new}"


def num(value) -> str:
    """数值显示：整数值不带 .0（角色卡里的数字都以 float 存储）"""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def signed(value: str | int | float) -> str:
    """给数值加正负号；value 可以是已经格式化好的字符串"""
    text = str(value)
    if text.startswith(("+", "-")):
        return text
    return f"+{text}"


def hint(text: str) -> str:
    """末尾提示行"""
    return f"提示：{text}"


def error(message: str, usage: str | None = None) -> str:
    """错误两行：问题 + 用法"""
    if not usage:
        return message
    return f"{message}\n用法：{usage}"


def join(*parts: str | None) -> str:
    """把非空片段按行拼接"""
    return "\n".join(p for p in parts if p)


def _wrap_line(line: str, width: int, indent: str) -> list[str]:
    limit = width * 2
    if display_width(line) <= limit:
        return [line]

    result: list[str] = []
    rest = line
    prefix = ""
    while display_width(prefix + rest) > limit:
        budget = limit - display_width(prefix)
        used = 0
        cut = 0
        last_break = 0
        for i, ch in enumerate(rest):
            w = char_width(ch)
            if ch in _BREAK_BEFORE and i > 0:
                last_break = i
            if used + w > budget:
                break
            used += w
            cut = i + 1
            if ch in _BREAK_AFTER:
                last_break = i + 1
        # 边界离行尾太远（不到一半）时直接硬切，避免出现很短的行
        if last_break and display_width(rest[:last_break]) * 2 >= budget:
            cut = last_break
        cut = max(cut, 1)
        result.append(prefix + rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
        prefix = indent
        if not rest:
            break
    if rest:
        result.append(prefix + rest)
    return result


def wrap(text: str, width: int = LINE_WIDTH, indent: str = "  ") -> str:
    """
    按东亚字宽换行：超过 width 个汉字宽的行在字段边界处断开，续行加 indent 缩进

    已有的换行保持不变。
    """
    lines: list[str] = []
    for line in text.split("\n"):
        lines.extend(_wrap_line(line, width, indent))
    return "\n".join(lines)


def clip_lines(
    lines: Iterable[str],
    max_lines: int = MAX_LIST_LINES,
    more_hint: str | None = None,
) -> list[str]:
    """
    行数超过 max_lines 时截断，最后一行提示还有多少行未显示

    Args:
        more_hint: 查看完整内容的方式，如「.tl get 时间点 查看某一时刻」
    """
    lines = list(lines)
    if len(lines) <= max_lines:
        return lines
    keep = max(max_lines - 1, 1)
    hidden = len(lines) - keep
    tail = f"……还有{hidden}行未显示"
    if more_hint:
        tail = f"{tail}\n{hint(more_hint)}"
    return lines[:keep] + [tail]
