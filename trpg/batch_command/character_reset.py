"""
角色重置指令 - 将角色恢复到初始状态

组合调用:
- .rc reset - 重置资源（HP、MP）到最大值，清除护盾
- .dr del all - 删除所有资源修饰
- .buff del all - 删除所有 buff

该指令位于 batch_command 层，单向引用 service 层功能。
指令转发通过 infrastructure 层的 CommandDispatcher 实现。
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapter.command_context import CommandContext

logger = logging.getLogger("TimelineTRPG.character_reset")


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
        from ..infrastructure.character_reader import character_reader
        from ..service.buff.buff import buff_module
        from ..service.resource.modifier import resource_modifier_module
        from ..service.resource.resource import resource_record_module

        self._ensure_reply_manager()
        character = character_reader.get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        steps = [
            ("part_resource", resource_record_module._reset_resources),
            ("part_modifier", resource_modifier_module._delete_all_modifiers),
            ("part_buff", buff_module._remove_all_buffs),
        ]
        lines = []
        failed = 0
        for part_key, step in steps:
            part = self.reply.render(part_key)
            try:
                result = await step(user_id)
            except Exception:
                logger.exception("角色重置步骤失败: %s", part_key)
                failed += 1
                lines.append(self.reply.render("reset_line_failed", part=part))
                continue
            # 子指令的回复可能带“用法/提示”行，汇总时只保留结论
            lines.append(
                self.reply.render(
                    "reset_line", part=part, result=result.split("\n", 1)[0]
                )
            )

        key = "reset_partial" if failed else "reset_success"
        return self.reply.render(
            key, name=character.get("name", ""), details="\n".join(lines)
        )


# 创建模块实例
character_reset_module = CharacterResetModule()
