"""
掷骰模块 - 处理所有与掷骰相关的功能
迁移自老项目 Game/Runtime/RollDice/
"""

import random
import re
from dataclasses import dataclass, field

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry

# 默认游戏设置
DEFAULT_SETTINGS = {
    "max_dice_count": 100,
    "max_dice_sides": 1000,
    "max_command_length": 100,
}

# 单项最多展示的骰子数，超出部分用省略号表示
MAX_DISPLAYED_ROLLS = 6

_NUMBER = r"\d+(?:\.\d*)?"
_TERM = rf"(?:{_NUMBER})?d{_NUMBER}|{_NUMBER}"
_EXPRESSION_RE = re.compile(rf"[+-]?(?:{_TERM})(?:[+-](?:{_TERM}))*")
_TERM_RE = re.compile(rf"([+-]?)({_TERM})")


class DiceError(ValueError):
    """掷骰表达式错误，args[0] 为 roll_dice 模块的回复模板名"""

    def __init__(self, template: str, **variables):
        super().__init__(template)
        self.template = template
        self.variables = variables


@dataclass
class DiceTerm:
    """表达式中的一项：骰子项或常数项"""

    sign: int
    text: str
    rolls: list[float] = field(default_factory=list)
    value: float = 0
    is_dice: bool = False


@dataclass
class RollResult:
    total: int | float
    terms: list[DiceTerm]
    decimals: int = 0

    @property
    def dice_count(self) -> int:
        return sum(len(t.rolls) for t in self.terms if t.is_dice)


def _decimals_of(text: str) -> int:
    return len(text.split(".", 1)[1]) if "." in text else 0


def _to_number(text: str) -> int | float:
    return float(text) if "." in text else int(text)


def _roll_dice_term(
    count_text: str, sides_text: str, rng: random.Random
) -> list[float]:
    """
    掷一个骰子项

    小数点规则：
    - NdM：掷N个M面骰，如3d6
    - N.dM：掷N个标准骰 + 小数部分比例的额外骰，如3.4d5.2
      = 3个uniform(1, 5.2) + 1个uniform(0, 5.2)×0.4
    """
    count = _to_number(count_text) if count_text else 1
    sides = _to_number(sides_text)

    if count <= 0 or sides <= 0:
        raise DiceError("invalid_expression")
    if sides > DEFAULT_SETTINGS["max_dice_sides"]:
        raise DiceError("too_many_sides", max=DEFAULT_SETTINGS["max_dice_sides"])

    int_part = int(count)
    if int_part > DEFAULT_SETTINGS["max_dice_count"]:
        raise DiceError("too_many_dice", max=DEFAULT_SETTINGS["max_dice_count"])

    rolls: list[float] = []
    for _ in range(int_part):
        if isinstance(sides, float):
            rolls.append(rng.uniform(1, sides))
        else:
            rolls.append(rng.randint(1, sides))

    decimal_part = count - int_part
    if decimal_part > 0:
        rolls.append(rng.uniform(0, sides) * decimal_part)
    return rolls


def roll_expression(expression: str, rng: random.Random | None = None) -> RollResult:
    """
    计算掷骰表达式

    支持：
    - 3d6、d20、3.4d5.2（小数骰规则见 _roll_dice_term）
    - 带修正值与多项相加：3d6+2、2d6+1d4-1
    - 单独一个数字 N：在 1~N 之间取随机数（等同 1dN）

    Raises:
        DiceError: 表达式非法或超出上限
    """
    rng = rng or random
    expr = expression.replace(" ", "").lower()

    if not expr:
        raise DiceError("invalid_expression")
    if len(expr) > DEFAULT_SETTINGS["max_command_length"]:
        raise DiceError(
            "expression_too_long", max=DEFAULT_SETTINGS["max_command_length"]
        )
    if not _EXPRESSION_RE.fullmatch(expr):
        raise DiceError("invalid_expression")

    if re.fullmatch(_NUMBER, expr):
        expr = f"d{expr}"

    terms: list[DiceTerm] = []
    decimals = 0
    total_dice = 0
    for sign_text, term_text in _TERM_RE.findall(expr):
        sign = -1 if sign_text == "-" else 1
        if "d" in term_text:
            count_text, sides_text = term_text.split("d", 1)
            decimals = max(decimals, _decimals_of(count_text), _decimals_of(sides_text))
            total_dice += int(_to_number(count_text)) if count_text else 1
            if total_dice > DEFAULT_SETTINGS["max_dice_count"]:
                raise DiceError("too_many_dice", max=DEFAULT_SETTINGS["max_dice_count"])
            rolls = _roll_dice_term(count_text, sides_text, rng)
            terms.append(
                DiceTerm(sign, term_text, rolls, sum(rolls) * sign, is_dice=True)
            )
        else:
            decimals = max(decimals, _decimals_of(term_text))
            value = _to_number(term_text)
            terms.append(DiceTerm(sign, term_text, value=value * sign))

    total = sum(t.value for t in terms)
    total = round(total, decimals) if decimals else int(round(total))
    return RollResult(total=total, terms=terms, decimals=decimals)


def _format_number(value: float, decimals: int) -> str:
    if decimals:
        return f"{value:.{decimals}f}"
    return str(int(round(value)))


def format_breakdown(result: RollResult) -> str:
    """
    生成掷骰明细，如 "(4+5+3)+2"；只有一个骰子且没有修正值时返回空字符串
    """
    if len(result.terms) == 1 and result.dice_count <= 1:
        return ""

    parts: list[str] = []
    for i, term in enumerate(result.terms):
        prefix = "-" if term.sign < 0 else ("+" if i else "")
        if term.is_dice:
            shown = [_format_number(r, result.decimals) for r in term.rolls]
            if len(shown) > MAX_DISPLAYED_ROLLS:
                hidden = len(shown) - MAX_DISPLAYED_ROLLS
                shown = shown[:MAX_DISPLAYED_ROLLS] + [f"…{hidden}个"]
            body = "+".join(shown)
            if len(term.rolls) > 1 and len(result.terms) > 1:
                body = f"({body})"
            parts.append(prefix + body)
        else:
            parts.append(prefix + _format_number(abs(term.value), result.decimals))
    return "".join(parts)


class RollDiceModule:
    """
    掷骰模块

    支持的指令格式：
    - .r 或 .r <表达式> - 掷骰 (如 .r 3d6+2)
    - .r <数字> - 生成 1 到该数字之间的随机数
    - .r d<数字> - 掷指定面数的骰子
    """

    def __init__(self):
        self.reply = ReplyManager("roll_dice")

    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="r",
            usage="[表达式]",
            summary="掷骰子",
            detail=(
                "默认掷骰(d100)\n"
                "{表达式} - 掷骰表达式，如 3d6+2\n"
                "{数字} - 掷1-{数字}之间的随机数\n"
                "d{数字} - 掷1个{数字}面骰"
            ),
        )

    async def r(self, ctx: CommandContext) -> bool:
        """
        处理掷骰命令

        .r 3d6+2 - 掷 3 个 6 面骰加 2
        .r 100 - 生成 1-100 之间的随机数
        .r d100 - 掷 1 个 100 面骰
        """
        if not ctx.args:
            result = random.randint(1, 100)
            ctx.send(self.reply.render("default_roll", result=result))
            return True

        expression = "".join(ctx.args)
        try:
            result = roll_expression(expression)
        except DiceError as e:
            ctx.send(
                self.reply.render(e.template, expression=expression, **e.variables)
            )
            return True

        breakdown = format_breakdown(result)
        total = _format_number(result.total, result.decimals)
        if "d" not in expression.lower():
            response = self.reply.render(
                "rd_result", expression=expression, result=total
            )
        elif breakdown:
            response = self.reply.render(
                "roll_result", expression=expression, result=total, rolls=breakdown
            )
        else:
            response = self.reply.render(
                "roll_result_single", expression=expression, result=total
            )

        ctx.send(response)
        return True


# 创建模块实例
roll_dice_module = RollDiceModule()
