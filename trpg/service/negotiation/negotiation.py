"""
交涉模块 - 处理交涉检定相关功能
迁移自老项目 Game/Runtime/Examination/NegotiationCommandHandler.py
"""

import math
import random

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.character_reader import CharacterReader
from ...infrastructure.config.game_config import game_config
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend


class NegotiationModule:
    """
    交涉模块

    支持的指令格式：
    - .neg - 显示当前交涉对象
    - .neg <rp评分> - 进行交涉
    - .neg <对象等级> <对象智力%> - 设定交涉对象
    - .neg <rp评分> <对象等级> <对象智力%> - 设定并交涉
    """

    def __init__(self):
        self.reply = ReplyManager("negotiation")
        self.system_reply = ReplyManager("system")

    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="neg",
            usage="[rp评分] [对象等级] [对象智力%]",
            summary="交涉检定",
            detail=(
                "{RP评分} - 进行交涉检定\n"
                "{对象等级} {对象智力%} - 设定交涉对象\n"
                "{RP评分} {对象等级} {对象智力%} - 设定交涉对象并交涉"
            ),
        )

    async def neg(self, ctx: CommandContext) -> bool:
        """
        处理交涉命令
        """
        # 判断会话类型
        session_type = "group" if ctx.group_id else "private"
        conversation_id = ctx.group_id or ctx.session_id or ctx.sender_id or "default"

        if not ctx.args:
            # 显示当前交涉对象
            target = self._get_negotiation_target(conversation_id, session_type)
            if target is None:
                response = self.reply.render("no_current_negotiation_target")
            else:
                target_level = target["level"]
                target_intelligence = target["intelligence"]
                response = self.reply.render(
                    "current_negotiation_target",
                    level=target_level,
                    intelligence=target_intelligence,
                )
            ctx.send(response)
            return True

        arg_list = ctx.args

        if len(arg_list) == 1:
            # 一个参数：进行交涉
            try:
                rp_grade = float(arg_list[0])
                result = await self._perform_negotiation(ctx, conversation_id, rp_grade)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("invalid_rp_grade")
                ctx.send(response)

        elif len(arg_list) == 2:
            # 两个参数：设定交涉对象
            try:
                target_level = int(float(arg_list[0]))
                intelligence_str = arg_list[1]
                if intelligence_str.endswith("%"):
                    target_intelligence = int(float(intelligence_str[:-1]))
                else:
                    target_intelligence = int(float(intelligence_str))

                self._set_negotiation_target(
                    conversation_id, target_level, target_intelligence, session_type
                )
                response = self.reply.render("negotiation_target_set")
                ctx.send(response)
            except ValueError:
                response = self.reply.render("invalid_target_params")
                ctx.send(response)

        elif len(arg_list) == 3:
            # 三个参数：设定并交涉
            try:
                rp_grade = float(arg_list[0])
                target_level = int(float(arg_list[1]))
                intelligence_str = arg_list[2]
                if intelligence_str.endswith("%"):
                    target_intelligence = int(float(intelligence_str[:-1]))
                else:
                    target_intelligence = int(float(intelligence_str))

                self._set_negotiation_target(
                    conversation_id, target_level, target_intelligence, session_type
                )
                result = await self._perform_negotiation(ctx, conversation_id, rp_grade)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("invalid_params")
                ctx.send(response)

        else:
            response = self.system_reply.render(
                "command_not_found", command=ctx.command
            )
            ctx.send(response)

        return True

    def _get_negotiation_target(
        self, conversation_id: str, session_type: str = "private"
    ) -> dict | None:
        return StorageBackend.load_negotiation(conversation_id, session_type)

    def _set_negotiation_target(
        self,
        conversation_id: str,
        level: int,
        intelligence: int,
        session_type: str = "private",
    ):
        data = {"level": level, "intelligence": intelligence}
        StorageBackend.save_negotiation(conversation_id, data, session_type)

    async def _perform_negotiation(
        self, ctx: CommandContext, conversation_id: str, rp_grade: float
    ) -> str:
        """执行交涉检定"""
        user_id = ctx.sender_id or "default"
        session_type = "group" if ctx.group_id else "private"

        # 获取当前激活角色
        character = CharacterReader.get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        character_name = character.get("name", "未知角色")

        # 获取最终属性（包含buff）
        final_attributes = CharacterReader.get_character_final_attributes(
            user_id, character_name
        )
        if not final_attributes or "交涉" not in final_attributes:
            return self.reply.render("negotiation_attribute_not_found")

        # 获取角色的等级
        character_data = character.get("data", {})
        level = character_data.get("等级", 1)

        # 获取目标
        target = self._get_negotiation_target(conversation_id, session_type)
        if not target or not target.get("level"):
            return self.reply.render("no_current_negotiation_target")

        target_level = target["level"]
        target_intelligence = target["intelligence"]

        # 获取交涉属性值（已包含buff修正）
        negotiation_value = final_attributes.get("交涉", 0)

        # 计算成功率
        success_rate = self._calculate_success_rate(
            rp_grade, negotiation_value, target_intelligence, level, target_level
        )

        # 格式化成功率显示
        success_rate_display = game_config.format_value(success_rate, "success_rate")

        # 掷骰
        roll = random.randint(1, 100)

        # 构建详细的交涉反馈
        lines = []
        lines.append(f"[{character_name}]进行交涉检定")
        lines.append(f"RP: {rp_grade} | 交涉加成: {negotiation_value}")
        lines.append(f"目标: 等级{target_level} | 智力{target_intelligence}%")
        lines.append(f"成功率: {success_rate_display}%")

        # 判断成功/失败 (roll <= success_rate 为成功)
        if roll <= success_rate:
            lines.append(f"投点: {roll}/{success_rate_display}% 🎉交涉成功!")
        else:
            lines.append(f"投点: {roll}/{success_rate_display}% ❌交涉失败")

        return "\n".join(lines)

    def _calculate_success_rate(
        self,
        rp_grade: float,
        negotiation_value: float,
        target_intelligence: float,
        level: float,
        target_level: float,
    ) -> float:
        """
        计算交涉成功率
        公式: ((rp_grade + (negotiation_value / level)) / target_intelligence * 25) * (math.log(level / target_level, math.e) + 1)
        """
        if target_intelligence <= 0:
            return 0.0

        success_rate = (
            (rp_grade + (negotiation_value / level)) / target_intelligence * 25
        ) * (math.log(level / target_level, math.e) + 1)

        return game_config.round_value(success_rate, "success_rate")


negotiation_module = NegotiationModule()
