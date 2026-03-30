"""
检定模块 - 处理属性检定相关功能
迁移自老项目 Game/Runtime/Examination/
"""
import random
from typing import Dict, Any

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.character_reader import character_reader
from ...infrastructure.attribute_resolver import AttributeResolver


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
        self.system_reply = ReplyManager("system")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="ex",
            usage="<属性名> [目标值|数字1 数字2]",
            summary="属性检定",
            detail=(
                "<属性名> - 使用tar目标值进行检定\n"
                "<属性名> <目标值> - 设定目标值进行检定\n"
                "<属性名> <数值1> <数值2> - 两数乘积为目标值\n"
                "\n"
                "例: .ex 力量 / .ex 力量 50 / .ex 力量 10 5"
            ),
        )
    
    async def ex(self, ctx: CommandContext) -> bool:
        """
        处理检定命令
        
        .ex {属性名} - 进行属性检定（使用已设置的tar目标值）
        .ex {属性名} {目标值} - 使用指定目标值进行检定
        .ex {属性名} {数字1} {数字2} - 使用两数字乘积作为目标值进行检定
        """
        if not ctx.args:
            response = self.reply.render("no_attribute_provided")
            ctx.send(response)
            return True
        
        # 先验证属性是否合法
        raw_attribute = ctx.args[0]
        if not AttributeResolver.is_valid(raw_attribute):
            valid_inputs = ", ".join(AttributeResolver.get_all_valid_inputs()[:10])
            response = f"无效的属性名：{raw_attribute}\n有效的属性包括：{valid_inputs}..."
            ctx.send(response)
            return True
        
        # 解析为标准属性名
        attribute_name = AttributeResolver.resolve(raw_attribute)
        
        # 判断会话类型
        session_type = "group" if ctx.group_id else "private"
        conversation_id = ctx.group_id or ctx.session_id or ctx.sender_id or "default"
        
        # 获取已设置的目标值
        from .target import target_module
        saved_target = await target_module._get_target(conversation_id, session_type)
        
        arg_list = ctx.args
        
        if len(arg_list) == 1:
            # 单个参数：使用已设置的tar目标值
            if saved_target is None:
                # 没有设置目标值，提示用户
                response = self.reply.render("no_target_value")
                ctx.send(response)
                return True
            result = await self._perform_examination_with_target(ctx, attribute_name, saved_target, is_custom_target=False)
        elif len(arg_list) == 2:
            # 两个参数：属性名和目标值
            try:
                target_value = int(float(arg_list[1]))
                result = await self._perform_examination_with_target(ctx, attribute_name, target_value, is_custom_target=True)
            except ValueError:
                response = self.reply.render("invalid_target_value")
                ctx.send(response)
                return True
        elif len(arg_list) == 3:
            # 三个参数：属性名和两个数字（相乘作为目标值）
            try:
                num1 = float(arg_list[1])
                num2 = float(arg_list[2])
                target_value = int(num1 * num2)
                result = await self._perform_examination_with_target(ctx, attribute_name, target_value, is_custom_target=True)
            except ValueError:
                response = self.reply.render("invalid_target_value")
                ctx.send(response)
                return True
        else:
            response = self.system_reply.render("command_not_found", command=ctx.command)
            ctx.send(response)
            return True
        
        ctx.send(result)
        return True
    
    async def _perform_examination_with_target(self, ctx: CommandContext, attribute: str, target_value: int, is_custom_target: bool = True) -> str:
        """
        执行目标值属性检定
        
        成功率计算公式：成功率 = 属性最终值 / (目标数值 * 5)
        检定成功条件：投掷结果 <= 成功率
        
        Args:
            ctx: 命令上下文
            attribute: 属性名（已解析为标准名）
            target_value: 目标值
            is_custom_target: 是否用户自定义目标值（True）或使用已保存的tar值（False）
        """
        from ...infrastructure.config.game_config import game_config
        
        resolved_attribute = attribute
        
        # 获取角色属性值
        attribute_value = await self._get_character_attribute(ctx, resolved_attribute)
        
        if attribute_value is None:
            return self.reply.render("no_character", user=ctx.sender_name or "用户")
        
        if attribute_value == 0:
            return self.reply.render("attribute_not_found", attribute=resolved_attribute)
        
        # 生成随机数（1-100）
        roll_result = random.randint(1, 100)
        
        # 计算成功率 = 属性最终值 / (目标数值 * 5)
        if target_value > 0:
            success_rate = attribute_value / (target_value * 5)
            # 使用 game_config 的精度
            success_rate = game_config.round_value(success_rate, "success_rate")
            # 不限制上限，允许超过100%（表示必定成功）
            success_rate = max(0, success_rate)
        else:
            success_rate = 0
        
        # 根据是否为自定义目标值生成不同的反馈格式
        if is_custom_target:
            # 用户自定义目标值
            target_info = f"(目标值 {target_value})"
        else:
            # 使用已保存的目标值
            target_info = f"[目标值 {target_value}]"
        
        # 构建详细的检定反馈
        character_name = ctx.sender_name or "角色"
        
        lines = []
        lines.append(f"{character_name} 进行 {resolved_attribute} 检定 {target_info}")
        lines.append(f"属性: {attribute_value} | 成功率: {success_rate * 100}% ({attribute_value}/{target_value*5})")
        
        # 检定成功或失败（投掷结果 <= 成功率）
        # 计算投点/成功率的比值（成功率已转换为百分比形式）
        if success_rate > 0:
            success_rate_percent = success_rate * 100
            ratio = roll_result / success_rate_percent
            ratio_display = game_config.format_value(ratio * 100, "success_rate")
        else:
            ratio_display = "0"
        
        if roll_result <= success_rate * 100:
            success_msg = self.reply.render("check_success")
            lines.append(f"投点: {roll_result} ({ratio_display}%) {success_msg}")
        else:
            failure_msg = self.reply.render("check_failure")
            lines.append(f"投点: {roll_result} ({ratio_display}%) {failure_msg}")
        
        return "\n".join(lines)
    
    async def _resolve_attribute_name(self, attribute: str) -> str:
        """解析属性名称，使用统一的 AttributeResolver"""
        resolved = AttributeResolver.resolve(attribute)
        return resolved if resolved else attribute
    
    async def _get_character_attribute(self, ctx: CommandContext, attribute: str) -> int | None:
        """
        获取角色属性值
        
        Args:
            ctx: 命令上下文
            attribute: 属性名（支持别名）
        
        Returns:
            属性值，如果角色不存在返回 None
        """
        user_id = ctx.sender_id or "default"
        
        # 使用 character_reader 获取属性值
        value = character_reader.get_attribute_value(user_id, attribute, include_buffs=True)
        
        if value is None:
            return None
        
        return int(value)


# 创建模块实例
examination_module = ExaminationModule()
