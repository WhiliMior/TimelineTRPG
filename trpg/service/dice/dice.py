"""
掷骰模块 - 处理所有与掷骰相关的功能
迁移自老项目 Game/Runtime/RollDice/
"""

import random
import re

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry

# 默认游戏设置
DEFAULT_SETTINGS = {
    "max_dice_count": 10,
    "max_dice_sides": 1000,
    "max_command_length": 100,
}


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
                "{表达式} - 掷骰表达式\n"
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
            # 无参数，默认掷骰
            result = random.randint(1, 100)
            response = self.reply.render("default_roll", result=result)
        else:
            args = ctx.args[0] if ctx.args else ""
            total, rolls = await self._parse_roll_command(args)

            # 格式化骰子结果显示
            if len(rolls) == 1:
                # 只有一个骰子或纯数字格式，不显示详细
                rolls_display = str(rolls[0])
            else:
                # 显示每个骰子结果，最多显示6个
                if len(rolls) <= 6:
                    rolls_display = "+".join(str(r) for r in rolls)
                else:
                    # 前6个骰子 + 省略号
                    rolls_display = (
                        "+".join(str(r) for r in rolls[:6]) + f"+...(+{len(rolls) - 6})"
                    )

            if "d" in args.lower():
                # NdM 格式 或 dN 格式
                response = self.reply.render(
                    "roll_result", expression=args, result=total, rolls=rolls_display
                )
            elif args.startswith("d"):
                # dN 格式
                response = self.reply.render(
                    "roll_result", expression=args, result=total, rolls=rolls_display
                )
            else:
                # 纯数字格式
                response = self.reply.render(
                    "rd_result", expression=args, result=total, rolls=rolls_display
                )

        ctx.send(response)
        return True

    async def _parse_roll_command(self, command: str) -> tuple[int | float, list]:
        """
        解析掷骰命令，支持多种格式

        小数点规则：
        - NdM：掷N个M面骰，如3d6
        - N.dM：掷N个标准骰 + 小数部分比例的额外骰，如3.4d5.2
          = 3个uniform(1, 5.2) + 1个uniform(0, 5.2)×0.4

        Returns:
            tuple: (总和, 骰子结果列表)
        """
        command = command.replace(" ", "")

        # 检查是否为 NdM 格式
        ndm_pattern = r"(\d+\.?\d*)d(\d+\.?\d*)"
        ndm_match = re.match(ndm_pattern, command.lower())

        if ndm_match:
            num_dice_str = ndm_match.group(1)
            dice_sides_str = ndm_match.group(2)

            try:
                num_dice = (
                    float(num_dice_str) if "." in num_dice_str else int(num_dice_str)
                )
                dice_sides = (
                    float(dice_sides_str)
                    if "." in dice_sides_str
                    else int(dice_sides_str)
                )

                if num_dice <= 0 or dice_sides <= 0:
                    result = random.randint(1, 100)
                    return (result, [result])

                # 限制最大骰子数量（基于整数部分）
                max_dice = int(num_dice) + 1  # 额外允许一个小数部分
                if max_dice > DEFAULT_SETTINGS["max_dice_count"]:
                    max_dice = DEFAULT_SETTINGS["max_dice_count"]

                if dice_sides > DEFAULT_SETTINGS["max_dice_sides"]:
                    dice_sides = DEFAULT_SETTINGS["max_dice_sides"]

                rolls = []

                # 整数部分：标准骰子 (1 到 面数)
                int_part = int(num_dice)
                for _ in range(int_part):
                    if isinstance(dice_sides, float):
                        rolls.append(random.uniform(1, dice_sides))
                    else:
                        rolls.append(random.randint(1, int(dice_sides)))

                # 小数部分：额外骰子 (0 到 面数)，乘以小数比例
                if "." in num_dice_str:
                    decimal_part = num_dice - int_part
                    if decimal_part > 0:
                        # 额外掷一个骰子，结果乘以小数比例
                        extra_roll = random.uniform(0, dice_sides) * decimal_part
                        rolls.append(extra_roll)

                # 计算小数位数
                max_decimal_places = 0
                if "." in dice_sides_str:
                    max_decimal_places = len(dice_sides_str.split(".")[1])
                if "." in num_dice_str:
                    num_decimal_places = len(num_dice_str.split(".")[1])
                    max_decimal_places = max(max_decimal_places, num_decimal_places)

                # 四舍五入到合适的小数位数
                result = round(sum(rolls), max_decimal_places)
                return (result, rolls)
            except ValueError:
                result = random.randint(1, 100)
                return (result, [result])

        # 检查是否为 dN 格式
        dn_pattern = r"d(\d+\.?\d*)"
        dn_match = re.match(dn_pattern, command.lower())

        if dn_match:
            dice_sides_str = dn_match.group(1)
            try:
                dice_sides = (
                    float(dice_sides_str)
                    if "." in dice_sides_str
                    else int(dice_sides_str)
                )

                if dice_sides <= 0:
                    result = random.randint(1, 100)
                    return (result, [result])

                if dice_sides > DEFAULT_SETTINGS["max_dice_sides"]:
                    dice_sides = DEFAULT_SETTINGS["max_dice_sides"]

                # dN 格式相当于 1dN
                if isinstance(dice_sides, float):
                    result = random.uniform(1, dice_sides)
                    decimal_places = (
                        len(dice_sides_str.split(".")[1])
                        if "." in dice_sides_str
                        else 0
                    )
                    result = round(result, decimal_places)
                    return (result, [result])
                else:
                    result = random.randint(1, int(dice_sides))
                    return (result, [result])
            except ValueError:
                result = random.randint(1, 100)
                return (result, [result])

        # 纯数字格式 (如 50 或 50.5)
        try:
            max_value = float(command)
            if max_value <= 0:
                result = random.randint(1, 100)
                return (result, [result])

            if max_value > DEFAULT_SETTINGS["max_dice_sides"]:
                max_value = DEFAULT_SETTINGS["max_dice_sides"]

            # 纯数字格式相当于 1dN
            if isinstance(max_value, float):
                result = random.uniform(1, max_value)
                decimal_places = len(command.split(".")[1]) if "." in command else 0
                result = round(result, decimal_places)
                return (result, [result])
            else:
                result = random.randint(1, int(max_value))
                return (result, [result])
        except ValueError:
            result = random.randint(1, 100)
            return (result, [result])


# 创建模块实例
roll_dice_module = RollDiceModule()
