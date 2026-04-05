"""
角色重置指令 - 将角色恢复到初始状态

组合调用:
- .rc reset - 重置资源（HP、MP）到最大值，清除护盾
- .dr del all - 删除所有资源修饰
- .buff del all - 删除所有 buff

该指令位于 batch_command 层，单向引用 service 层功能。
指令转发通过 infrastructure 层的 CommandDispatcher 实现。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...adapter.command_context import CommandContext


class CharacterResetModule:
    """
    角色重置模块

    指令格式：.chrr reset
    功能：重置角色所有状态（资源、资源修饰、buff）到初始状态
    """

    def __init__(self):
        # Lazy import to avoid circular dependency issues
        pass

    def _ensure_reply_manager(self):
        """Lazy initialization of reply managers"""
        if not hasattr(self, "_reply_initialized"):
            from ..adapter.message import ReplyManager

            self.reply = ReplyManager("character_reset")
            self.system_reply = ReplyManager("system")
            self._reply_initialized = True

    @property
    def help_entry(self):
        from ..infrastructure.help import HelpEntry

        return HelpEntry(
            module="chrr",
            usage="reset",
            summary="重置角色状态",
            detail=(
                "reset - 重置角色所有状态\n"
                "  - 重置 HP/MP 到最大值\n"
                "  - 清除所有护盾\n"
                "  - 删除所有资源修饰\n"
                "  - 删除所有 buff\n"
                "\n"
                "快捷方式: .chr reset"
            ),
        )

    async def chrr(self, ctx: "CommandContext") -> bool:
        """
        处理角色重置命令 (.chrr)
        """
        if not ctx.args:
            return True

        command = ctx.args[0].lower()

        if command == "reset":
            result = await self._reset_character_state(ctx)
            ctx.send(result)
            return True

        return True

    async def _reset_character_state(self, ctx: "CommandContext") -> str:
        """
        执行角色状态重置

        调用 service 层功能：
        1. rc reset - 重置资源
        2. dr del all - 删除所有资源修饰
        3. buff del all - 删除所有 buff
        """
        user_id = ctx.sender_id or "default"

        # 导入 service 层模块（单向引用）
        from ..service.resource.resource import resource_record_module
        from ..service.resource.modifier import resource_modifier_module
        from ..service.buff.buff import buff_module

        results = []
        errors = []

        # 1. 重置资源（HP、MP 到最大值，清除护盾）
        try:
            result = await resource_record_module._reset_resources(user_id)
            results.append(f"资源重置: {result}")
        except Exception as e:
            errors.append(f"资源重置失败: {str(e)}")

        # 2. 删除所有资源修饰
        try:
            result = await resource_modifier_module._delete_all_modifiers(user_id)
            results.append(f"资源修饰: {result}")
        except Exception as e:
            errors.append(f"资源修饰清除失败: {str(e)}")

        # 3. 删除所有 buff
        try:
            result = await buff_module._remove_all_buffs(user_id)
            results.append(f"Buff: {result}")
        except Exception as e:
            errors.append(f"Buff清除失败: {str(e)}")

        # 构建最终回复
        self._ensure_reply_manager()
        if errors:
            return self.reply.render(
                "reset_partial",
                success="\n".join(results) if results else "无",
                errors="\n".join(errors),
            )
        else:
            return self.reply.render(
                "reset_success",
                details="\n".join(results),
            )


# 创建模块实例
character_reset_module = CharacterResetModule()

# 注册到 infrastructure 层的指令转发器
# service 层通过 command_dispatcher.dispatch("chr_reset", ctx) 调用
from ..infrastructure.command_dispatcher import command_dispatcher

command_dispatcher.register("chr_reset", character_reset_module._reset_character_state)
