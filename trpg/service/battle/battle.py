"""
战斗模块 - 处理战斗相关功能
迁移自老项目 Game/Runtime/Battle/BattleSystem.py 和 BattleCommandHandler.py

功能：
- 战斗时间轴管理
- 角色属性集成
- 战斗行动添加/插入/撤销
- 定时事件（与Buff系统集成）
- 武器战斗（需武器系统支持）
"""

import math
import time

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.attribute_resolver import AttributeResolver
from ...infrastructure.character_reader import CharacterReader
from ...infrastructure.config.game_config import game_config
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend
from ...infrastructure.timeline_formatter import timeline_formatter

from .core import init_timeline_core, timeline_core


class BattleModule:
    """
    战斗模块

    支持的指令格式（根据老项目设计）：
    - .bt - 显示帮助
    - <属性> <时间>t/<影响值> (笔记) - 添加战斗行动
    - wp <时间>t/<影响值> (笔记) - 武器战斗
    - 插入时间t <属性> <时间>t/<影响值> (笔记) - 插入行动
    - undo - 撤销最后行动

    注意：以下指令已移至 .tl 指令：
    - new, join/in, leave/out, ready, start, end, status
    """

    def __init__(self):
        self.reply = ReplyManager("battle")
        self.system_reply = ReplyManager("system")
        # 初始化 timeline_core
        init_timeline_core(self)

    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="bt",
            usage="[属性/wp] [时间]t/[影响值] (笔记)",
            summary="战斗系统",
            detail=(
                "<属性> <时间>t (笔记) - 添加战斗行动(时间模式)\n"
                "<属性> <影响值> (笔记) - 添加战斗行动(影响值模式)\n"
                "wp <时间>t/<影响值> (笔记) - 使用武器进行战斗\n"
                "wp re - 装填火力武器\n"
                "<时间t> <属性> <时间>t/<影响值> - 在指定时间插入行动\n"
                "undo - 撤销最后行动\n"
                "\n"
                "增幅武器: 时间模式(t)和影响值模式(数字)都支持\n"
                "火力武器: 只支持影响值模式(数字)\n"
                "类型为其他的武器: 不可以使用wp指令\n"
                "\n"
                "公式: 影响值 = 属性 × 时间 / 20\n"
                "注：时间线管理请使用 .tl 指令"
            ),
        )

    async def bt(self, ctx: CommandContext) -> bool:
        """
        处理战斗命令
        """
        user_id = ctx.sender_id or "default"
        conversation_id = ctx.group_id or ctx.session_id or user_id
        is_group = ctx.group_id is not None
        storage_key = f"{conversation_id}"

        if not ctx.args:
            # 显示帮助
            ctx.send(self.reply.render("help"))
            return True

        # 解析命令
        # 检查是否是属性命令（直接使用属性名）
        if len(ctx.args) >= 2:
            first_arg = ctx.args[0]
            second_arg = ctx.args[1]

            # 检查是否是插入时间命令
            if first_arg.endswith("t") and (AttributeResolver.is_valid(second_arg)):
                # 插入时间t 属性 时间t/影响值 格式
                if first_arg.endswith("t"):
                    insert_time = first_arg
                    resolved_attr = AttributeResolver.resolve(second_arg)
                    remaining_args = ctx.args[2:] if len(ctx.args) > 2 else []
                    result = await self._insert_action(
                        storage_key,
                        user_id,
                        is_group,
                        insert_time,
                        resolved_attr,
                        remaining_args,
                    )
                    ctx.send(result)
                    return True

            # 检查是否是属性+时间/影响值格式
            if AttributeResolver.is_valid(first_arg):
                # 属性命令：属性 时间t/影响值 (笔记)
                resolved_attr = AttributeResolver.resolve(first_arg)
                remaining_args = ctx.args[1:] if len(ctx.args) > 1 else []
                result = await self._add_action(
                    storage_key, user_id, is_group, resolved_attr, remaining_args
                )
                ctx.send(result)
                return True

        main_command = ctx.args[0].lower()

        # bt 指令支持：属性命令、wp命令、undo、in、out、插入时间

        if main_command == "wp":
            result = await self._weapon_battle(
                storage_key,
                user_id,
                is_group,
                ctx.args[1:] if len(ctx.args) > 1 else [],
            )
            ctx.send(result)

        elif main_command == "undo":
            result = await self._undo_action(storage_key, user_id, is_group)
            ctx.send(result)

        elif main_command in ("in", "join"):
            result = await self._join_battle(storage_key, user_id, is_group)
            ctx.send(result)

        elif main_command in ("out", "leave"):
            result = await self._leave_battle(storage_key, user_id, is_group)
            ctx.send(result)

        elif AttributeResolver.is_valid(main_command):
            # 属性命令（当只有一个参数时）
            resolved_attr = AttributeResolver.resolve(main_command)
            remaining_args = ctx.args[1:] if len(ctx.args) > 1 else []
            result = await self._add_action(
                storage_key, user_id, is_group, resolved_attr, remaining_args
            )
            ctx.send(result)

        else:
            ctx.send(self.system_reply.render("command_not_found", command=ctx.command))

        return True

    def _get_battle(self, storage_key: str, is_group: bool = True) -> dict:
        """
        获取当前活跃的战斗对象
        数据结构：{"active_battle_id": xxx, "player": {}, "battle_list": {"xxx": {...}}}

        Args:
            storage_key: 会话ID
            is_group: 是否为群聊
        """
        data = StorageBackend.load_battle_timeline(storage_key, is_group)
        if not data.get("battle_list"):
            data["battle_list"] = {}

        # 获取当前活跃的战斗 ID
        active_battle_id = data.get("active_battle_id")

        # 如果有活跃战斗，返回该战斗对象；否则返回一个新的空战斗对象
        if active_battle_id and active_battle_id in data["battle_list"]:
            return data["battle_list"][active_battle_id]
        else:
            # 返回一个新的空战斗对象，用于新建战斗
            return {
                "status": "idle",
                "name": None,
                "creator": None,
                "participants": {},
                "timeline": {},
                "current_time": 0,
                "max_time": 0,
                "scheduled_events": [],
            }

    def _save_battle(self, storage_key: str, battle: dict, is_group: bool = True):
        """
        保存战斗数据

        Args:
            storage_key: 会话ID
            battle: 战斗数据
            is_group: 是否为群聊
        """
        # 先加载现有数据
        data = StorageBackend.load_battle_timeline(storage_key, is_group)

        # 确保数据结构完整
        if not data.get("battle_list"):
            data["battle_list"] = {}
        if "player" not in data:
            data["player"] = {}

        # 获取当前活跃的战斗 ID
        active_battle_id = data.get("active_battle_id")

        # 如果当前有活跃战斗，更新它；否则创建新战斗
        if active_battle_id:
            data["battle_list"][active_battle_id] = battle
        else:
            # 创建新的战斗 ID（使用时间戳）
            import time

            new_battle_id = str(int(time.time()))
            data["active_battle_id"] = new_battle_id
            data["battle_list"][new_battle_id] = battle

        StorageBackend.save_battle_timeline(storage_key, data, is_group)

    def _set_active_battle(
        self, storage_key: str, battle_id: str, is_group: bool = True
    ):
        """设置当前活跃的战斗"""
        data = StorageBackend.load_battle_timeline(storage_key, is_group)
        data["active_battle_id"] = battle_id
        StorageBackend.save_battle_timeline(storage_key, data, is_group)

    def _clear_active_battle(self, storage_key: str, is_group: bool = True):
        """清除当前活跃的战斗"""
        data = StorageBackend.load_battle_timeline(storage_key, is_group)
        data["active_battle_id"] = None
        StorageBackend.save_battle_timeline(storage_key, data, is_group)

    def _get_character_module(self):
        """获取角色模块"""
        from ..character.character import character_module

        return character_module

    async def _get_active_character(self, user_id: str) -> dict | None:
        """获取用户当前激活的角色"""
        char_module = self._get_character_module()
        return await char_module.get_active_character(user_id)

    async def _get_character_attributes(
        self, user_id: str, character_name: str
    ) -> dict[str, float]:
        """获取角色的最终属性值（包含Buff修正）"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return {}

        # 获取角色基础属性
        char_data = active_char.get("data", {})
        attributes = {}

        # 常见属性映射
        attr_keys = ["力量", "敏捷", "体质", "智力", "感知", "魅力"]
        for key in attr_keys:
            if key in char_data:
                try:
                    attributes[key] = float(char_data[key])
                except (ValueError, TypeError):
                    attributes[key] = 0.0

        # TODO: 从Buff系统获取属性修正
        # TODO: 从资源修正系统获取属性修正

        return attributes

    async def _get_final_attribute(self, user_id: str, attribute: str) -> float | None:
        """获取角色的最终属性值（包含Buff修正）"""
        # 使用 CharacterReader 获取最终属性（包含Buff修正）
        return CharacterReader.get_attribute_value(
            user_id, attribute, include_buffs=True
        )

    def _parse_time_input(self, time_input: str, default_attribute_value: float = None):
        """
        解析时间输入
        格式：时间t 或 纯数字（影响值）

        计算公式：
        - impact = (Final_attribute_value / 10) * (time / 2)
        - time = (impact * 2) / (Final_attribute_value / 10) = impact * 20 / Final_attribute_value

        如果计算时间小于最小精度单位，则使用最小精度重新计算impact值

        返回：(time, impact_value, error_message)
        """
        # 格式：时间t 或 纯数字（作为影响值）
        time_val = 1.0
        impact_val = 10
        try:
            if time_input.endswith("t"):
                # 输入是时间格式：计算 impact = (attr / 10) * (time / 2)
                time_val = float(time_input[:-1])
                if default_attribute_value is not None:
                    impact_val = (default_attribute_value / 10) * (time_val / 2)
                else:
                    impact_val = 10  # 默认影响值
            else:
                # 输入是纯数字，视为影响值：计算 time = impact * 20 / attr
                impact_val = float(time_input)
                if default_attribute_value is not None and default_attribute_value > 0:
                    time_val = (impact_val * 20) / default_attribute_value
                else:
                    time_val = 1.0  # 默认时间
        except ValueError:
            return None, None, "invalid_input"

        # 检查时间是否小于最小精度单位，如果是则使用最小精度重新计算impact
        min_time_unit = game_config.get_min_time_unit()
        if (
            time_val < min_time_unit
            and default_attribute_value is not None
            and default_attribute_value > 0
        ):
            time_val = min_time_unit
            impact_val = (default_attribute_value / 10) * (time_val / 2)

        return time_val, impact_val, None

    @staticmethod
    def calculate_impact_from_time(attribute_value: float, time: float) -> float:
        """
        使用统一公式计算影响值
        公式: impact = (attr / 10) * (time / 2) = attr * time / 20
        """
        return attribute_value * time / 20

    @staticmethod
    def calculate_time_from_impact(attribute_value: float, impact: float) -> float:
        """
        使用统一公式计算时间
        公式: time = impact * 20 / attr
        """
        if attribute_value <= 0:
            return 0.0
        return impact * 20 / attribute_value

    def _round_value(self, value: float, precision: int = 2) -> float:
        """根据精度四舍五入（保留本地方法，内部使用统一配置）"""
        return round(value, precision)

    def _format_time(self, value: float) -> int | float:
        """格式化时间值"""
        return game_config.round_value(value, "time")

    def _format_impact(self, value: float) -> int | float:
        """格式化影响值"""
        return game_config.round_value(value, "impact")

    def _create_battle(
        self, storage_key: str, user_id: str, is_group: bool, name: str
    ) -> str:
        """
        创建新战斗

        Args:
            storage_key: 会话ID
            user_id: 用户ID
            is_group: 是否为群聊
            name: 战斗名称
        """
        # 先检查是否已有活跃战斗
        data = StorageBackend.load_battle_timeline(storage_key, is_group)
        active_battle_id = data.get("active_battle_id")

        if active_battle_id and active_battle_id in data.get("battle_list", {}):
            existing_battle = data["battle_list"][active_battle_id]
            if existing_battle.get("status") != "idle":
                return self.reply.render("battle_already_exists")

        # 创建新战斗 - 使用时间戳作为ID

        new_battle_id = str(int(time.time()))

        new_battle = {
            "name": name,
            "created_at": self._get_current_time(),
            "participants": {},
            "timeline": {},
            "current_time": 0,
            "max_time": 0,
            "scheduled_events": [],
        }

        # 保存到数据结构中
        if "battle_list" not in data:
            data["battle_list"] = {}
        data["battle_list"][new_battle_id] = new_battle
        data["active_battle_id"] = new_battle_id

        StorageBackend.save_battle_timeline(storage_key, data, is_group)
        return self.reply.render("battle_created", name=name)

    async def _join_battle(self, storage_key: str, user_id: str, is_group: bool) -> str:
        """
        加入战斗

        Args:
            storage_key: 会话ID
            user_id: 用户ID
            is_group: 是否为群聊
        """
        battle = self._get_battle(storage_key, is_group)

        # 如果没有战斗，返回错误
        if not battle.get("name"):
            return self.reply.render("no_battle")

        # 获取用户激活的角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        char_name = str(active_char.get("name", "未知角色"))

        # 确保 participants 结构正确
        if "participants" not in battle:
            battle["participants"] = {}

        if user_id not in battle["participants"]:
            battle["participants"][user_id] = {}

        # 添加角色到战斗
        if char_name not in battle["participants"][user_id]:
            battle["participants"][user_id][char_name] = {
                "status": "参与中",
            }

        self._save_battle(storage_key, battle, is_group)
        return self.reply.render("status_joined", name=char_name)

    async def _leave_battle(
        self, storage_key: str, user_id: str, is_group: bool
    ) -> str:
        """
        离开战斗

        Args:
            storage_key: 会话ID
            user_id: 用户ID
            is_group: 是否为群聊
        """
        battle = self._get_battle(storage_key, is_group)

        # 检查用户是否在战斗中
        if user_id not in battle.get("participants", {}):
            return self.reply.render("not_in_battle")

        # 获取用户激活的角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        char_name = str(active_char.get("name", "未知角色"))

        if char_name in battle["participants"][user_id]:
            # 修改状态为"已退出"而不是删除
            battle["participants"][user_id][char_name]["status"] = "已退出"
            self._save_battle(storage_key, battle, is_group)
            return self.reply.render("status_left", name=char_name)

        return self.reply.render("not_in_battle")

    def _toggle_ready(self, storage_key: str, user_id: str, is_group: bool) -> str:
        """切换准备状态"""
        battle = self._get_battle(storage_key, is_group)

        if user_id not in battle.get("participants", {}):
            return self.reply.render("not_in_battle")

        # 这里暂时不需要 ready 功能
        return self.reply.render("ready")

    def _start_battle(self, storage_key: str, user_id: str, is_group: bool) -> str:
        """开始战斗"""
        battle = self._get_battle(storage_key, is_group)

        if not battle.get("name"):
            return self.reply.render("no_battle")

        # 开始战斗只需要有参与者即可
        participants_count = len(battle.get("participants", {}))
        if participants_count < 1:
            return self.reply.render("no_ready_players")

        battle["current_time"] = 0
        battle["max_time"] = 0

        self._save_battle(storage_key, battle, is_group)
        return self.reply.render("battle_started")

    def _end_battle(self, storage_key: str, user_id: str, is_group: bool) -> str:
        """结束战斗"""
        battle = self._get_battle(storage_key, is_group)

        if not battle.get("name"):
            return self.reply.render("no_battle")

        # 清除战斗数据
        battle["name"] = None
        battle["participants"] = {}
        battle["timeline"] = {}
        battle["current_time"] = 0
        battle["max_time"] = 0
        battle["scheduled_events"] = []

        self._save_battle(storage_key, battle, is_group)
        # 清除活跃战斗ID
        self._clear_active_battle(storage_key, is_group)
        return self.reply.render("battle_ended")

    def _battle_status(self, storage_key: str, is_group: bool) -> str:
        """获取战斗状态"""
        battle = self._get_battle(storage_key, is_group)

        if not battle.get("name"):
            return self.reply.render("no_battle")

        ready_count = len(battle.get("ready", []))
        participants_count = len(battle.get("participants", {}))

        lines = [
            self.reply.render(
                "battle_status_header", name=battle.get("name", "未命名")
            ),
            self.reply.render("status_label") + battle.get("status", "unknown"),
            self.reply.render("participants_label") + str(participants_count),
            self.reply.render("ready_label") + str(ready_count),
        ]

        # 如果战斗已激活，显示时间轴
        if battle.get("status") == "active" and battle.get("timeline"):
            lines.append("")
            lines.append(
                self.reply.render(
                    "timeline_current_max_time",
                    current=battle.get("current_time", 0),
                    max=battle.get("max_time", 0),
                )
            )

        return "\n".join(lines)

    async def _add_action(
        self,
        storage_key: str,
        user_id: str,
        is_group: bool,
        attribute: str,
        args: list[str],
    ) -> str:
        """
        添加战斗行动

        Args:
            storage_key: 会话ID
            user_id: 用户ID
            is_group: 是否为群聊
            attribute: 属性名（已解析为标准属性名）
            args: 命令参数
        """
        battle = self._get_battle(storage_key, is_group)

        # 如果没有战斗数据，返回错误
        if not battle.get("name"):
            return self.reply.render("no_battle")

        # 获取用户当前激活的角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        character_name = str(active_char.get("name", "未知角色"))

        # 确保 participants 结构正确
        if "participants" not in battle:
            battle["participants"] = {}

        if user_id not in battle["participants"]:
            battle["participants"][user_id] = {}

        # 如果角色不在参与者中，自动添加
        if character_name not in battle["participants"][user_id]:
            battle["participants"][user_id][character_name] = {
                "status": "参与中",
            }

        # 获取角色最新行动的结束时间（用于计算新行动起始时间）
        latest_end_time = self._timeline_core.get_latest_action_end_time(
            battle, user_id, character_name
        )

        # 获取属性值
        attribute_value = await self._get_final_attribute(user_id, attribute)
        if attribute_value is None:
            return self.reply.render("attribute_not_found", attribute=attribute)

        # 解析参数
        if not args:
            return self.reply.render("input_error")

        time_input = args[0]
        notes = ""
        if len(args) > 1:
            # 检查是否有括号包裹的笔记
            for i, arg in enumerate(args):
                if arg.startswith("(") or arg.endswith(")"):
                    notes = " ".join(args[i:]).strip("()")
                    break
            if not notes and len(args) > 1:
                notes = " ".join(args[1:])

        # 解析时间输入
        time_val, impact_val, error = self._parse_time_input(
            time_input, attribute_value
        )
        if error:
            return self.reply.render("invalid_input")

        # 计算行动时间点（使用角色最新行动的结束时间作为新行动的起始时间）
        start_time = latest_end_time
        new_time_point = start_time + time_val
        new_time_point = self._format_time(new_time_point)

        # 格式化时间和影响值（使用配置的精度）
        formatted_time = self._format_time(time_val)
        formatted_impact = self._format_impact(impact_val)

        # 创建行动记录
        action = {
            "user_id": user_id,
            "character_name": character_name,
            "start_time": self._format_time(start_time),
            "lead_time": formatted_time,
            "attribute_used": attribute,
            "impact_value": formatted_impact,
            "notes": notes,
        }

        # 确保 timeline 存在
        if "timeline" not in battle:
            battle["timeline"] = {}

        # 添加到时间轴
        time_str = str(new_time_point)
        if time_str not in battle["timeline"]:
            battle["timeline"][time_str] = []
        battle["timeline"][time_str].append(action)

        # current_time 和 max_time 通过 self._timeline_core 实时计算，不再存储到文件

        # 保存战斗数据
        self._save_battle(storage_key, battle, is_group)

        # 递减当前角色的计数模式buff事件（在添加新行动之后）
        self._decrement_count_based_events(
            storage_key, user_id, character_name, is_group
        )

        # 执行到期的定时事件
        executed = self.execute_scheduled_events(storage_key, user_id, is_group)

        # 如果有到期事件，将消息添加到返回结果中
        timeline_result = self._format_timeline_display(battle)
        if executed:
            event_msgs = "\n【到期事件】\n" + "\n".join(executed)
            return timeline_result + event_msgs

        return timeline_result

    def _decrement_count_based_events(
        self, storage_key: str, user_id: str, character_name: str, is_group: bool
    ):
        """
        递减指定用户当前角色的计数模式事件的剩余次数
        包括buff、护盾、资源修饰事件

        Args:
            storage_key: 会话ID
            user_id: 用户ID
            character_name: 角色名
            is_group: 是否为群聊
        """
        battle = self._get_battle(storage_key, is_group)
        if not battle.get("name"):
            return

        scheduled_events = battle.get("scheduled_events", [])

        events_to_remove = []

        for i, event in enumerate(scheduled_events):
            # 检查是否为该用户和角色的计数模式事件
            if (
                event.get("user_id") == user_id
                and event.get("character_name") == character_name
                and event.get("mode") == "count_based"
                and event.get("remaining_count") is not None
            ):
                # 递减剩余次数
                event["remaining_count"] -= 1

                # 检查是否已达到次数限制
                if event["remaining_count"] <= 0:
                    events_to_remove.append(i)

        # 从后往前删除已达到次数限制的事件
        for i in reversed(events_to_remove):
            del scheduled_events[i]

        # 保存数据
        if events_to_remove:
            self._save_battle(storage_key, battle, is_group)

    async def _insert_action(
        self,
        storage_key: str,
        user_id: str,
        insert_time: str,
        attribute: str,
        args: list[str],
    ) -> str:
        """在指定时间点插入行动"""
        battle = self._get_battle(storage_key)

        # 如果没有战斗数据，自动创建一个（兼容 timeline 创建的时间线）
        if not battle:
            battle = {
                "name": "时间线战斗",
                "name": "时间线战斗",
                "participants": {},
                "timeline": {},
                "current_time": 0,
                "max_time": 0,
                "created_at": self._get_current_time(),
            }

        # 如果没有战斗，返回错误
        if not battle.get("name"):
            return self.reply.render("no_battle")

        # 解析插入时间
        try:
            insert_time_val = float(insert_time.lower().replace("t", ""))
            insert_time_val = self._format_time(insert_time_val)
        except ValueError:
            return self.reply.render("invalid_time_value")

        # 验证角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        character_name = str(active_char.get("name", "未知角色"))

        # 检查属性
        attribute_value = await self._get_final_attribute(user_id, attribute)
        if attribute_value is None:
            return self.reply.render("attribute_not_found", attribute=attribute)

        # 解析参数
        if not args:
            return self.reply.render("input_error")

        time_input = args[0]
        notes = ""
        if len(args) > 1:
            notes = " ".join(args[1:])

        # 解析时间输入
        time_val, impact_val, error = self._parse_time_input(
            time_input, attribute_value
        )
        if error:
            return self.reply.render("invalid_input")

        # 确保 timeline 存在
        if "timeline" not in battle:
            battle["timeline"] = {}

        # 检查该时间点是否有正在进行的行动
        found_ongoing = False
        for time_str, actions in battle.get("timeline", {}).items():
            for action in actions:
                action_start = float(time_str) - action["lead_time"]
                action_end = float(time_str)

                if (
                    action_start < insert_time_val < action_end
                    and action["user_id"] == user_id
                ):
                    # 提前终止原行动
                    elapsed = insert_time_val - action_start
                    completion = elapsed / action["lead_time"]
                    completed_impact = action["impact_value"] * completion
                    action["impact_value"] = self._format_impact(completed_impact)
                    action["lead_time"] = self._format_time(elapsed)
                    action["notes"] = (
                        "[提前终止] " + action["notes"]
                        if action["notes"]
                        else "[提前终止]"
                    )
                    found_ongoing = True
                    break
            if found_ongoing:
                break

        # 添加新行动
        if not found_ongoing:
            new_time_point = insert_time_val + time_val
            new_time_point = self._format_time(new_time_point)

            # 格式化时间和影响值（使用配置的精度）
            formatted_time = self._format_time(time_val)
            formatted_impact = self._format_impact(impact_val)

            action = {
                "user_id": user_id,
                "character_name": character_name,
                "start_time": self._format_time(insert_time_val),
                "lead_time": formatted_time,
                "attribute_used": attribute,
                "impact_value": formatted_impact,
                "notes": notes,
            }

            time_str = str(new_time_point)
            if time_str not in battle["timeline"]:
                battle["timeline"][time_str] = []
            battle["timeline"][time_str].append(action)

        # current_time 和 max_time 通过 self._timeline_core 实时计算，不再存储到文件

        # 保存战斗数据
        self._save_battle(storage_key, battle, is_group)

        # 执行到期的定时事件
        executed = self.execute_scheduled_events(storage_key, user_id, is_group)

        # 如果有到期事件，将消息添加到返回结果中
        timeline_result = self._format_timeline_display(battle)
        if executed:
            event_msgs = "\n【到期事件】\n" + "\n".join(executed)
            return timeline_result + event_msgs

        return timeline_result

    async def _undo_action(self, storage_key: str, user_id: str, is_group: bool) -> str:
        """
        撤销最后的行动

        Args:
            storage_key: 会话ID
            user_id: 用户ID
            is_group: 是否为群聊
        """
        battle = self._get_battle(storage_key, is_group)

        if not battle.get("name"):
            return self.reply.render("no_battle")

        # 获取用户当前激活的角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        character_name = str(active_char.get("name", "未知角色"))

        # 找到该用户该角色的最后一个行动（比较结束时间 time_str）
        last_end_time = None
        last_action_index = -1
        last_action_time_str = None

        timeline = battle.get("timeline", {})
        for time_str, actions in timeline.items():
            for i, action in enumerate(actions):
                if (
                    action["user_id"] == user_id
                    and str(action["character_name"]) == character_name
                ):
                    # 直接比较 time_str（结束时间），找到最后添加的行动
                    action_end_time = float(time_str)
                    if last_end_time is None or action_end_time > last_end_time:
                        last_end_time = action_end_time
                        last_action_index = i
                        last_action_time_str = time_str

        if last_action_index == -1:
            return self.reply.render("no_action_to_undo")

        # 删除行动
        if "timeline" in battle and last_action_time_str in battle["timeline"]:
            del battle["timeline"][last_action_time_str][last_action_index]
            if not battle["timeline"][last_action_time_str]:
                del battle["timeline"][last_action_time_str]

        # 恢复被撤销的计数模式事件（恢复1次）
        self._restore_count_based_events(storage_key, user_id, character_name, is_group)

        # 执行到期的定时事件
        executed = self.execute_scheduled_events(storage_key, user_id, is_group)

        # 保存战斗数据
        self._save_battle(storage_key, battle, is_group)

        # 格式化输出当前时间轴状态
        timeline_result = self._format_timeline_display(battle)

        # 返回结果
        result = self.reply.render("action_undone", name=character_name)
        if executed:
            event_msgs = "\n【到期事件】\n" + "\n".join(executed)
            result += event_msgs
        result += "\n" + timeline_result
        return result

    def _restore_count_based_events(
        self, storage_key: str, user_id: str, character_name: str, is_group: bool
    ):
        """
        恢复指定用户当前角色的计数模式事件的剩余次数（在撤销行动时调用）

        Args:
            storage_key: 会话ID
            user_id: 用户ID
            character_name: 角色名
            is_group: 是否为群聊
        """
        battle = self._get_battle(storage_key, is_group)
        if not battle.get("name"):
            return

        scheduled_events = battle.get("scheduled_events", [])

        for event in scheduled_events:
            # 检查是否为该用户和角色的计数模式事件
            if (
                event.get("user_id") == user_id
                and event.get("character_name") == character_name
                and event.get("mode") == "count_based"
                and event.get("remaining_count") is not None
            ):
                # 恢复剩余次数（增加1）
                event["remaining_count"] += 1

        # 保存数据
        self._save_battle(storage_key, battle, is_group)

    def _format_timeline_display(
        self, battle: dict, attribute_label: str = "属性", extra_info: dict = None
    ) -> str:
        """格式化时间轴显示（使用统一格式化器）

        Args:
            battle: 战斗数据
            attribute_label: 属性列标签（"属性"或"武器"）
            extra_info: 额外信息（如弹药）
        """
        # 实时计算 current_time 和 max_time（通过 self._timeline_core）
        current_time = self._timeline_core.get_current_time(battle)
        max_time = self._timeline_core.get_max_time(battle)
        # 设置到 battle 中供 formatter 使用
        battle["current_time"] = current_time
        battle["max_time"] = max_time
        return timeline_formatter.format_timeline(
            battle, attribute_label=attribute_label, extra_info=extra_info
        )

    async def _weapon_battle(
        self, storage_key: str, user_id: str, is_group: bool, args: list[str]
    ) -> str:
        """武器战斗指令（需要武器系统）"""
        from ..weapon.weapon import weapon_module

        battle = self._get_battle(storage_key, is_group)

        if not battle.get("name"):
            return self.reply.render("no_battle")

        # 检查是否是装填指令
        if args and args[0].lower() in ("re", "reload", "装填"):
            return await self._weapon_reload(user_id, battle, is_group)

        # 解析参数
        if not args:
            return self.reply.render("wp_usage")

        value_str = args[0]
        notes = " ".join(args[1:]) if len(args) > 1 else ""

        # 获取装备的武器
        weapon = await weapon_module.get_equipped_weapon(user_id)

        if not weapon:
            return self.reply.render("no_weapon_equipped")

        weapon_type = weapon.get("type", "")
        weapon_name = weapon.get("name", "")
        weapon_damage = weapon.get("damage", 0)
        weapon_cast = weapon.get("cast", 0)  # 前摇
        weapon_attribute = weapon.get("attribute", "")

        # 检查武器类型
        if weapon_type == "none":
            return self.reply.render("weapon_type_none", name=weapon_name)

        # 获取角色名
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")
        character_name = str(active_char.get("name", "未知角色"))

        # 增幅武器
        if weapon_type == "amplifier":
            return await self._handle_amplifier_weapon(
                user_id,
                battle,
                is_group,
                weapon,
                character_name,
                weapon_name,
                weapon_damage,
                weapon_attribute,
                value_str,
                notes,
                storage_key,
            )

        # 火力武器
        elif weapon_type == "artillery":
            return await self._handle_artillery_weapon(
                user_id,
                battle,
                is_group,
                weapon,
                character_name,
                weapon_name,
                weapon_damage,
                weapon_cast,
                value_str,
                notes,
                storage_key,
            )

        return self.reply.render("weapon_type_unsupported", type=weapon_type)

    async def _handle_amplifier_weapon(
        self,
        user_id: str,
        battle: dict,
        is_group: bool,
        weapon: dict,
        character_name: str,
        weapon_name: str,
        damage: float,
        attribute: str,
        value_str: str,
        notes: str,
        storage_key: str,
    ) -> str:
        """处理增幅武器"""
        # 解析输入
        is_time_input = value_str.endswith("t")

        # 获取角色经过buff后的属性值
        final_attr_value = CharacterReader.get_attribute_value(
            user_id, attribute, include_buffs=True
        )
        if final_attr_value is None or final_attr_value == 0:
            return self.reply.render("attribute_not_found_or_zero", attribute=attribute)

        # 计算增幅后的属性值
        amplified_attr = final_attr_value * (1 + damage / 100)

        # 使用统一公式计算
        if is_time_input:
            try:
                time_input = float(value_str.rstrip("t"))
            except ValueError:
                return self.reply.render("invalid_time")
            time_val = time_input
            impact_val = self.calculate_impact_from_time(amplified_attr, time_input)
        else:
            try:
                impact_input = float(value_str)
            except ValueError:
                return self.reply.render("invalid_impact")
            impact_val = impact_input
            if amplified_attr == 0:
                return self.reply.render("amplified_attr_zero")
            time_val = self.calculate_time_from_impact(amplified_attr, impact_input)

        # 格式化
        time_val = game_config.round_value(time_val, "time")
        impact_val = game_config.round_value(impact_val, "impact")

        # 添加战斗行动
        return await self._add_action_with_weapon(
            storage_key,
            user_id,
            is_group,
            character_name,
            attribute,
            time_val,
            impact_val,
            weapon_name,
            notes,
        )

    async def _handle_artillery_weapon(
        self,
        user_id: str,
        battle: dict,
        is_group: bool,
        weapon: dict,
        character_name: str,
        weapon_name: str,
        damage: float,
        cast: float,
        value_str: str,
        notes: str,
        storage_key: str,
    ) -> str:
        """
        处理火力武器

        火力武器设计：
        - 伤害 = 单发子弹伤害 x 发射子弹数
        - 不需要角色的任何属性增幅
        - weapon.damage = 单发子弹的基础伤害
        - weapon.cast = 每发子弹的前摇时间
        - weapon.load = 弹匣容量
        """
        # 获取当前弹药数
        current_load = weapon.get("current_load", 0)
        max_load = weapon.get("load", 0)

        # 单发子弹伤害
        per_bullet_damage = damage

        if per_bullet_damage <= 0:
            return self.reply.render("weapon_damage_zero")

        if cast <= 0:
            return self.reply.render("weapon_cast_zero")

        # 如果没有弹药，直接返回提示
        if current_load == 0:
            return self.reply.render(
                "weapon_ammo_insufficient",
                current_load=0,
                max_load=max_load,
                available_time=0,
                max_impact=0,
            )

        # 解析输入
        is_time_input = value_str.endswith("t")

        if is_time_input:
            # 时间模式：让武器开火直到总时间接近输入值
            try:
                time_input = float(value_str.rstrip("t"))
            except ValueError:
                return self.reply.render("invalid_time")

            # 计算最多可以发射的子弹数
            max_bullets = int(time_input // cast)

            if max_bullets == 0:
                return self.reply.render(
                    "time_insufficient_for_bullets", time=time_input, cast=cast
                )

            # 检查弹药是否足够
            if max_bullets > current_load:
                # 弹药不足，返回提示信息
                available_time = current_load * cast
                max_impact = per_bullet_damage * current_load
                return self.reply.render(
                    "weapon_ammo_insufficient",
                    current_load=current_load,
                    max_load=max_load,
                    available_time=game_config.round_value(available_time, "time"),
                    max_impact=int(max_impact),
                )

            actual_bullets = max_bullets
            remaining_bullets = current_load - actual_bullets
            time_val = actual_bullets * cast
            # 火力武器伤害 = 单发伤害 x 子弹数
            impact_val = per_bullet_damage * actual_bullets

        else:
            # 影响值模式：输入目标影响值，计算需要的子弹数和时间
            try:
                impact_input = float(value_str)
            except ValueError:
                return self.reply.render("invalid_impact")

            # 计算需要的子弹数（向上取整）
            needed_bullets = math.ceil(impact_input / per_bullet_damage)

            # 检查弹药是否足够
            if needed_bullets > current_load:
                # 弹药不足，返回提示信息
                available_time = current_load * cast
                max_impact = per_bullet_damage * current_load
                return self.reply.render(
                    "weapon_ammo_insufficient",
                    current_load=current_load,
                    max_load=max_load,
                    available_time=game_config.round_value(available_time, "time"),
                    max_impact=int(max_impact),
                )

            actual_bullets = needed_bullets
            remaining_bullets = current_load - actual_bullets

            # 实际发射的子弹数决定实际伤害
            actual_impact = per_bullet_damage * actual_bullets
            time_val = actual_bullets * cast
            impact_val = actual_impact

        # 格式化
        time_val = game_config.round_value(time_val, "time")
        impact_val = game_config.round_value(impact_val, "impact")

        # 更新弹药数
        await self._update_weapon_ammo(user_id, weapon, remaining_bullets)

        # 传递弹药信息
        extra_info = {"ammo": {"current": remaining_bullets, "max": max_load}}

        # 添加战斗行动（使用"火力"作为属性标识）
        return await self._add_action_with_weapon(
            storage_key,
            user_id,
            is_group,
            character_name,
            "火力",
            time_val,
            impact_val,
            weapon_name,
            notes,
            extra_info=extra_info,
        )

    async def _weapon_reload(self, user_id: str, battle: dict, is_group: bool) -> str:
        """火力武器装填"""
        from ..weapon.weapon import weapon_module

        if not battle.get("name"):
            return self.reply.render("no_battle")

        weapon = await weapon_module.get_equipped_weapon(user_id)

        if not weapon:
            return self.reply.render("no_weapon_equipped")

        if weapon.get("type") != "artillery":
            return self.reply.render("weapon_not_artillery", name=weapon.get("name"))

        reload_time = weapon.get("reload_time", 0)
        max_load = weapon.get("load", 0)

        if reload_time <= 0:
            return self.reply.render("weapon_no_reload_time", name=weapon.get("name"))

        # 装填弹药
        await self._update_weapon_ammo(user_id, weapon, max_load)

        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")
        character_name = str(active_char.get("name", "未知角色"))

        storage_key = f"{battle.get('conversation_id', 'default')}"

        # 添加装填行动
        result = await self._add_action_with_weapon(
            storage_key,
            user_id,
            is_group,
            character_name,
            "火力",
            reload_time,
            0,
            weapon.get("name"),
            "装填",
        )

        return result + f"\n[装填完成: {max_load}/{max_load}]"

    async def _update_weapon_ammo(self, user_id: str, weapon: dict, new_ammo: int):
        """更新武器弹药数"""
        from ..weapon.weapon import weapon_module

        weapons = await weapon_module._get_weapons(user_id)

        for w in weapons:
            if w.get("name") == weapon.get("name"):
                w["current_load"] = new_ammo
                break

        await weapon_module._save_weapons(user_id, weapons)

    async def _add_action_with_weapon(
        self,
        storage_key: str,
        user_id: str,
        is_group: bool,
        character_name: str,
        attribute: str,
        time_val: float,
        impact_val: float,
        weapon_name: str,
        notes: str,
        extra_info: dict = None,
    ) -> str:
        """添加武器战斗行动

        Args:
            storage_key: 会话ID
            user_id: 用户ID
            is_group: 是否为群聊
            character_name: 角色名
            attribute: 属性名
            time_val: 时间值
            impact_val: 影响值
            weapon_name: 武器名
            notes: 备注
            extra_info: 额外信息字典（如弹药 {"ammo": {"current": 5, "max": 10}}）
        """
        battle = self._get_battle(storage_key, is_group)

        # 确保 participants 结构正确
        if "participants" not in battle:
            battle["participants"] = {}

        if user_id not in battle["participants"]:
            battle["participants"][user_id] = {}

        if character_name not in battle["participants"][user_id]:
            battle["participants"][user_id][character_name] = {
                "status": "参与中",
            }

        # 获取角色最新行动的结束时间（用于计算新行动起始时间）
        latest_end_time = self._timeline_core.get_latest_action_end_time(
            battle, user_id, character_name
        )

        # 计算时间点（使用角色最新行动的结束时间作为新行动的起始时间）
        start_time = latest_end_time
        new_time_point = start_time + time_val
        new_time_point = self._format_time(new_time_point)

        # 格式化
        formatted_time = self._format_time(time_val)
        formatted_impact = self._format_impact(impact_val)

        # 创建行动记录
        action = {
            "user_id": user_id,
            "character_name": character_name,
            "start_time": self._format_time(start_time),
            "lead_time": formatted_time,
            "attribute_used": attribute,
            "impact_value": formatted_impact,
            "notes": notes,
            "weapon": weapon_name,
            "using_weapon": True,
        }

        # 添加到时间轴
        if "timeline" not in battle:
            battle["timeline"] = {}

        time_str = str(new_time_point)
        if time_str not in battle["timeline"]:
            battle["timeline"][time_str] = []
        battle["timeline"][time_str].append(action)

        # current_time 和 max_time 通过 self._timeline_core 实时计算，不再存储到文件

        # 保存战斗数据
        self._save_battle(storage_key, battle, is_group)

        # 递减当前角色的计数模式buff事件
        self._decrement_count_based_events(
            storage_key, user_id, character_name, is_group
        )

        # 执行到期的定时事件
        executed = self.execute_scheduled_events(storage_key, user_id, is_group)

        # 格式化输出 - 使用统一的 timeline 格式化器
        timeline_result = self._format_timeline_display(
            battle, attribute_label="武器", extra_info=extra_info
        )

        # 如果有到期事件，将消息添加到返回结果中
        if executed:
            event_msgs = "\n【到期事件】\n" + "\n".join(executed)
            return timeline_result + event_msgs

        return timeline_result

    def schedule_buff_event(
        self,
        conversation_id: str,
        user_id: str,
        character_name: str,
        action_description: str,
        duration_or_count: float,
        callback_path: str,
        callback_args: dict,
        callback_message: str,
        mode: str = "time_based",
        is_group: bool = True,
    ) -> bool:
        """
        调度一个定时事件

        委托给 infrastructure.scheduler_module 处理
        """
        from ...infrastructure.scheduler import schedule_event

        return schedule_event(
            conversation_id=conversation_id,
            user_id=user_id,
            character_name=character_name,
            action_description=action_description,
            duration_or_count=duration_or_count,
            callback_path=callback_path,
            callback_args=callback_args,
            callback_message=callback_message,
            mode=mode,
            event_type="buff",
            is_group=is_group,
        )

    def execute_scheduled_events(
        self, conversation_id: str, user_id: str = None, is_group: bool = True
    ) -> list[str]:
        """
        执行到期的定时事件

        委托给 infrastructure.scheduler_module 处理
        """
        from ...infrastructure.scheduler import execute_scheduled_events

        return execute_scheduled_events(conversation_id, user_id, is_group)


battle_module = BattleModule()
