import random

import pytest

from timeline_trpg.trpg.service.dice.dice import (
    DEFAULT_SETTINGS,
    DiceError,
    format_breakdown,
    roll_dice_module,
    roll_expression,
)


def test_modifier_is_added():
    rng = random.Random(1)
    result = roll_expression("3d6+2", rng)
    dice_sum = sum(result.terms[0].rolls)
    assert result.total == dice_sum + 2
    assert result.dice_count == 3
    assert format_breakdown(result).endswith("+2")


def test_negative_modifier_and_multiple_terms():
    result = roll_expression("2d6+1d4-1", random.Random(2))
    expected = sum(result.terms[0].rolls) + sum(result.terms[1].rolls) - 1
    assert result.total == expected


def test_pure_number_is_random_range():
    for _ in range(50):
        assert 1 <= roll_expression("5").total <= 5


def test_dice_count_cap_is_enforced():
    limit = DEFAULT_SETTINGS["max_dice_count"]
    with pytest.raises(DiceError) as err:
        roll_expression(f"{limit + 1}d6")
    assert err.value.template == "too_many_dice"
    with pytest.raises(DiceError):
        roll_expression(f"{limit}d6+{limit}d6")
    assert roll_expression(f"{limit}d6").dice_count == limit


def test_huge_dice_count_does_not_loop(monkeypatch):
    calls = []
    rng = random.Random(0)
    monkeypatch.setattr(rng, "randint", lambda a, b: calls.append(1) or 1)
    with pytest.raises(DiceError):
        roll_expression("999999d6", rng)
    assert calls == []


@pytest.mark.parametrize("expr", ["abc", "3d", "d", "3d6++2", "0d6", "1d0"])
def test_invalid_expressions(expr):
    with pytest.raises(DiceError):
        roll_expression(expr)


def test_command_reports_invalid_expression(make_ctx, run):
    ctx = make_ctx("r", "abc")
    run(roll_dice_module.r(ctx))
    assert "用法" in ctx.get_reply_texts()[0]


def test_fractional_dice_keep_decimal_places():
    result = roll_expression("1.5d4.2", random.Random(3))
    assert result.decimals == 1
    assert len(result.terms[0].rolls) == 2
