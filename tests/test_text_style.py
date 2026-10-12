from timeline_trpg.trpg.infrastructure.suggestion import closest
from timeline_trpg.trpg.infrastructure.text_style import (
    clip_lines,
    delta,
    display_width,
    error,
    item,
    num,
    signed,
    title,
    wrap,
)


def test_display_width_counts_fullwidth_as_two():
    assert display_width("abc") == 3
    assert display_width("体力") == 4
    assert display_width("：") == 2
    assert display_width("●→×") == 6


def test_wrap_keeps_short_lines():
    text = "【勇者】\n体力：30/30"
    assert wrap(text) == text


def test_wrap_breaks_at_field_boundary():
    line = "护盾：全类型5 体力3 意志2 全类型10 体力20 意志30"
    lines = wrap(line).split("\n")
    assert len(lines) > 1
    assert all(display_width(part) <= 36 for part in lines)
    assert lines[1].startswith("  ")
    assert "".join(p.strip() for p in lines).replace(" ", "") == line.replace(" ", "")


def test_wrap_hard_cuts_without_boundary():
    lines = wrap("一" * 40).split("\n")
    assert all(display_width(part) <= 36 for part in lines)
    assert "".join(p.strip() for p in lines) == "一" * 40


def test_clip_lines_adds_hidden_count_and_hint():
    lines = [f"{i}. 行动" for i in range(30)]
    clipped = clip_lines(lines, max_lines=15, more_hint=".tl get 时间点")
    assert len(clipped) == 15
    assert clipped[-1] == "……还有16行未显示\n提示：.tl get 时间点"
    assert clip_lines(lines[:5]) == lines[:5]


def test_small_helpers():
    assert title("背包", " 共2种") == "【背包】 共2种"
    assert item(1, "勇者", active=True) == "●1. 勇者"
    assert item(2, "游侠") == "2. 游侠"
    assert delta(30, 15) == "30→15"
    assert signed(5) == "+5" and signed("-3") == "-3"
    assert num(2.0) == "2" and num(2.5) == "2.5" and num("x") == "x"
    assert error("参数不够", ".r 3d6") == "参数不够\n用法：.r 3d6"


def test_closest_suggestions():
    assert closest("buf", ["r", "buff", "bt"]) == "buff"
    assert closest("力良", ["智力", "力量", "敏捷"]) == "力量"
    assert closest("BT", ["bt"]) is None
    assert closest("zzzz", ["r", "ex"]) is None
    assert closest("", ["r"]) is None
