"""
掷骰模块 - 处理所有与掷骰相关的功能
迁移自老项目 Game/Runtime/RollDice/
"""
import random
import re

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry


# 默认游戏设置
DEFAULT_SETTINGS = {
    'max_dice_count': 10,
    'max_dice_sides': 1000,
    'max_command_length': 100
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
                "- 默认掷骰(d100)\n"
                "{表达式} - 掷骰表达式，如3d6+2\n"
                "{数字} - 掷1-{数字}之间的随机数\n"
                "d{数字} - 掷1个{数字}面骰\n"
                "\n"
                "示例:\n"
                "  r → 掷 1-100 随机数\n"
                "  r 3d6 → 掷 3 个 6 面骰\n"
                "  r 2d20+5 → 掷 2 个 20 面骰加 5\n"
                "  r d100 → 掷 1 个 100 面骰\n"
                "  r 50 → 生成 1-50 的随机数"
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
            result = await self._parse_roll_command(args)
            
            if 'd' in args.lower():
                # NdM 格式 或 dN 格式
                response = self.reply.render("roll_result", expression=args, result=result)
            elif args.startswith('d'):
                # dN 格式
                response = self.reply.render("roll_result", expression=args, result=result)
            else:
                # 纯数字格式
                response = self.reply.render("rd_result", expression=args, result=result)
        
        ctx.send(response)
        return True
    
    async def _parse_roll_command(self, command: str) -> int | float:
        """
        解析掷骰命令，支持多种格式
        """
        command = command.replace(' ', '')
        
        # 检查是否为 NdM 格式
        ndm_pattern = r'(\d+\.?\d*)d(\d+\.?\d*)'
        ndm_match = re.match(ndm_pattern, command.lower())
        
        if ndm_match:
            num_dice_str = ndm_match.group(1)
            dice_sides_str = ndm_match.group(2)
            
            try:
                num_dice = float(num_dice_str) if '.' in num_dice_str else int(num_dice_str)
                dice_sides = float(dice_sides_str) if '.' in dice_sides_str else int(dice_sides_str)
                
                if num_dice <= 0 or dice_sides <= 0:
                    return random.randint(1, 100)
                
                if num_dice > DEFAULT_SETTINGS['max_dice_count']:
                    num_dice = DEFAULT_SETTINGS['max_dice_count']
                
                if dice_sides > DEFAULT_SETTINGS['max_dice_sides']:
                    dice_sides = DEFAULT_SETTINGS['max_dice_sides']
                
                # 处理小数情况
                if isinstance(num_dice, float) or isinstance(dice_sides, float):
                    result = random.uniform(1, dice_sides)
                    max_decimal_places = max(
                        len(num_dice_str.split('.')[1]) if '.' in num_dice_str else 0,
                        len(dice_sides_str.split('.')[1]) if '.' in dice_sides_str else 0
                    )
                    return round(result, max_decimal_places)
                else:
                    rolls = [random.randint(1, int(dice_sides)) for _ in range(int(num_dice))]
                    return sum(rolls)
            except ValueError:
                return random.randint(1, 100)
        
        # 检查是否为 dN 格式
        dn_pattern = r'd(\d+\.?\d*)'
        dn_match = re.match(dn_pattern, command.lower())
        
        if dn_match:
            dice_sides_str = dn_match.group(1)
            try:
                dice_sides = float(dice_sides_str) if '.' in dice_sides_str else int(dice_sides_str)
                
                if dice_sides <= 0:
                    return random.randint(1, 100)
                
                if dice_sides > DEFAULT_SETTINGS['max_dice_sides']:
                    dice_sides = DEFAULT_SETTINGS['max_dice_sides']
                
                if isinstance(dice_sides, float):
                    result = random.uniform(1, dice_sides)
                    decimal_places = len(dice_sides_str.split('.')[1]) if '.' in dice_sides_str else 0
                    return round(result, decimal_places)
                else:
                    return random.randint(1, int(dice_sides))
            except ValueError:
                return random.randint(1, 100)
        
        # 纯数字格式
        try:
            max_value = float(command)
            if max_value <= 0:
                return random.randint(1, 100)
            
            if max_value > DEFAULT_SETTINGS['max_dice_sides']:
                max_value = DEFAULT_SETTINGS['max_dice_sides']
            
            if isinstance(max_value, float):
                result = random.uniform(1, max_value)
                decimal_places = len(command.split('.')[1]) if '.' in command else 0
                return round(result, decimal_places)
            else:
                return random.randint(1, int(max_value))
        except ValueError:
            return random.randint(1, 100)


# 创建模块实例
roll_dice_module = RollDiceModule()
