"""
检定模块 - 处理属性检定相关功能
迁移自老项目 Game/Runtime/Examination/
"""
import random
from typing import Dict, Any

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry


# 属性别名配置
ATTRIBUTE_ALIASES: Dict[str, str] = {}


class ExaminationModule:
    """
    检定模块
    
    支持的指令格式：
    - .ex <属性名> - 使用角色属性进行检定
    - .ex <属性名> <目标值> - 使用指定目标值进行检定
    - .ex <属性名> <数字1> <数字2> - 使用两数字乘积作为目标值
    
    注意：此模块需要角色系统支持，需要先创建角色
    """
    
    def __init__(self):
        self.reply = ReplyManager("examination")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="ex",
            usage="<属性名> [目标值|数字1 数字2]",
            summary="属性检定",
            detail=(
                "{属性名} - 使用属性进行检定\n"
                "{属性名} {目标值} - 设定目标值进行检定\n"
                "{属性名} {数值1} {数值2} - 设定范围进行检定\n"
                "\n"
                "示例:\n"
                "  ex 力量 → 使用角色力量属性进行检定\n"
                "  ex 敏捷 50 → 以 50 为目标值进行检定\n"
                "  ex 智力 10 5 → 以 10×5=50 为目标值进行检定"
            ),
        )
    
    async def ex(self, ctx: CommandContext) -> bool:
        """
        处理检定命令
        
        .ex {属性名} - 进行属性检定
        .ex {属性名} {目标值} - 使用指定目标值进行检定
        .ex {属性名} {数字1} {数字2} - 使用两数字乘积作为目标值进行检定
        """
        if not ctx.args:
            response = self.reply.render("no_attribute_provided")
            ctx.send(response)
            return True
        
        arg_list = ctx.args
        
        if len(arg_list) == 1:
            # 单个参数：使用默认目标值
            attribute_name = arg_list[0]
            result = await self._perform_examination(ctx, attribute_name)
        elif len(arg_list) == 2:
            # 两个参数：属性名和目标值
            attribute_name = arg_list[0]
            try:
                target_value = int(float(arg_list[1]))
                result = await self._perform_examination_with_target(ctx, attribute_name, target_value)
            except ValueError:
                response = self.reply.render("invalid_target_value")
                ctx.send(response)
                return True
        elif len(arg_list) == 3:
            # 三个参数：属性名和两个数字（相乘作为目标值）
            attribute_name = arg_list[0]
            try:
                num1 = float(arg_list[1])
                num2 = float(arg_list[2])
                target_value = int(num1 * num2)
                result = await self._perform_examination_with_target(ctx, attribute_name, target_value)
            except ValueError:
                response = self.reply.render("invalid_target_value")
                ctx.send(response)
                return True
        else:
            response = self.reply.render("invalid_command_format")
            ctx.send(response)
            return True
        
        ctx.send(result)
        return True
    
    async def _perform_examination(self, ctx: CommandContext, attribute: str) -> str:
        """执行属性检定"""
        # 解析属性名称（使用别名映射）
        resolved_attribute = await self._resolve_attribute_name(attribute)
        
        # TODO: 从角色系统获取属性值
        # 目前返回提示信息，需要角色系统支持
        attribute_value = await self._get_character_attribute(ctx, resolved_attribute)
        
        if attribute_value is None:
            return self.reply.render("no_character", user=ctx.sender_name or "用户")
        
        if attribute_value == 0:
            return self.reply.render("attribute_not_found", attribute=resolved_attribute)
        
        # 生成随机数（1-100）
        roll_result = random.randint(1, 100)
        
        # 检定成功或失败
        if roll_result <= attribute_value:
            success_msg = self.reply.render("check_success")
            return f"{ctx.sender_name} 进行 {resolved_attribute} 检定: {roll_result}/{attribute_value}\n{success_msg}"
        else:
            failure_msg = self.reply.render("check_failure")
            return f"{ctx.sender_name} 进行 {resolved_attribute} 检定: {roll_result}/{attribute_value}\n{failure_msg}"
    
    async def _perform_examination_with_target(self, ctx: CommandContext, attribute: str, target_value: int) -> str:
        """执行自定义目标值的属性检定"""
        resolved_attribute = await self._resolve_attribute_name(attribute)
        
        # 获取角色属性值
        attribute_value = await self._get_character_attribute(ctx, resolved_attribute)
        
        if attribute_value is None:
            return self.reply.render("no_character", user=ctx.sender_name or "用户")
        
        if attribute_value == 0:
            return self.reply.render("attribute_not_found", attribute=resolved_attribute)
        
        # 生成随机数（1-100）
        roll_result = random.randint(1, 100)
        
        # 检定成功或失败
        if roll_result <= target_value:
            success_msg = self.reply.render("check_success")
            return f"{ctx.sender_name} 进行 {resolved_attribute} 检定 (目标值 {target_value}): {roll_result}/{attribute_value}\n{success_msg}"
        else:
            failure_msg = self.reply.render("check_failure")
            return f"{ctx.sender_name} 进行 {resolved_attribute} 检定 (目标值 {target_value}): {roll_result}/{attribute_value}\n{failure_msg}"
    
    async def _resolve_attribute_name(self, attribute: str) -> str:
        """解析属性名称，使用别名映射"""
        return ATTRIBUTE_ALIASES.get(attribute, attribute)
    
    async def _get_character_attribute(self, ctx: CommandContext, attribute: str) -> int | None:
        """
        获取角色属性值
        TODO: 从角色数据存储中获取
        目前返回 None 表示没有角色
        """
        # TODO: 实现角色系统后从此处获取角色数据
        return None


# 创建模块实例
examination_module = ExaminationModule()
