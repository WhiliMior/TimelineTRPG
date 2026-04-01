"""
等级模块 - 管理角色等级
迁移自老项目 Game/Runtime/Level/

功能：
- 查询等级
- 设置等级
- 调整等级
"""

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry


class LevelModule:
    """
    等级模块

    支持的指令格式：
    - .lv - 查询当前等级
    - .lv <等级> - 设置等级
    - .lv +/-<数值> - 调整等级
    """

    def __init__(self):
        self.reply = ReplyManager("level")

    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="lv",
            usage="[等级|+/-等级]",
            summary="等级管理",
            detail=(
                "- 查询当前等级\n"
                "{等级} - 设置等级\n"
                "+{数值} - 增加等级\n"
                "-{数值} - 减少等级"
            ),
        )

    async def lv(self, ctx: CommandContext) -> bool:
        """
        处理等级命令
        """
        user_id = ctx.sender_id or "default"

        if not ctx.args:
            # 查询等级
            result = await self._query_level(user_id)
            ctx.send(result)
            return True

        command = ctx.args[0]

        # 检查是否是调整等级
        if command.startswith("+") or command.startswith("-"):
            try:
                delta = int(command)
                result = await self._adjust_level(user_id, delta)
                ctx.send(result)
            except ValueError:
                result = self.reply.render("invalid_format")
                ctx.send(result)
        else:
            # 设置等级
            try:
                level = int(command)
                result = await self._set_level(user_id, level)
                ctx.send(result)
            except ValueError:
                result = self.reply.render("invalid_format")
                ctx.send(result)

        return True

    async def _get_character_module(self):
        """获取角色模块"""
        from ..character.character import character_module

        return character_module

    async def _get_active_character(self, user_id: str) -> dict | None:
        """获取用户当前激活的角色"""
        char_module = await self._get_character_module()
        return await char_module.get_active_character(user_id)

    async def _query_level(self, user_id: str) -> str:
        """查询等级"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        name = active_char.get("name", "未知")
        level = active_char.get("data", {}).get("等级", 1)

        return self.reply.render("level_query", name=name, level=level)

    async def _set_level(self, user_id: str, level: int) -> str:
        """设置等级"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        if level < 1:
            level = 1

        # 获取当前等级
        old_level = active_char.get("data", {}).get("等级", 1)

        # 更新等级
        if "data" not in active_char:
            active_char["data"] = {}
        active_char["data"]["等级"] = level

        # 保存更改
        char_module = await self._get_character_module()
        characters = await char_module._get_user_characters(user_id)

        # 找到并更新活跃角色
        for i, char in enumerate(characters):
            if char.get("active", False):
                characters[i] = active_char
                break

        await char_module._save_characters(user_id, characters)

        return self.reply.render("level_adjusted", old=old_level, new=level)

    async def _adjust_level(self, user_id: str, delta: int) -> str:
        """调整等级"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        # 获取当前等级
        old_level = active_char.get("data", {}).get("等级", 1)

        # 计算新等级
        new_level = old_level + delta
        if new_level < 1:
            new_level = 1

        # 更新等级
        if "data" not in active_char:
            active_char["data"] = {}
        active_char["data"]["等级"] = new_level

        # 保存更改
        char_module = await self._get_character_module()
        characters = await char_module._get_user_characters(user_id)

        # 找到并更新活跃角色
        for i, char in enumerate(characters):
            if char.get("active", False):
                characters[i] = active_char
                break

        if not await char_module._save_characters(user_id, characters):
            return self.reply.render("save_failed")

        return self.reply.render("level_adjusted", old=old_level, new=new_level)


# 创建模块实例
level_module = LevelModule()
