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
import time
import re
from typing import Dict, List, Optional, Any, Union

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend
from ...infrastructure.config.game_config import game_config

# 属性别名配置
ATTRIBUTE_ALIASES = {
    "力量": "力量",
    "str": "力量",
    "敏捷": "敏捷",
    "dex": "敏捷",
    "体质": "体质",
    "con": "体质",
    "智力": "智力",
    "int": "智力",
    "感知": "感知",
    "wis": "感知",
    "魅力": "魅力",
    "cha": "魅力",
}


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
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="bt",
            usage="[属性/wp] [时间]t/[影响值] (笔记)",
            summary="战斗系统",
            detail=(
                "力量/敏捷等属性 时间t/影响值 (笔记) - 添加战斗行动\n"
                "wp 时间t/影响值 (笔记) - 使用武器进行战斗\n"
                "插入时间t 属性 时间t/影响值 (笔记) - 在指定时间插入行动\n"
                "undo - 撤销最后行动\n"
                "\n"
                "增幅武器可以使用t或者数字\n"
                "火力武器只可以使用数字\n"
                "其他武器不可以使用指令\n"
                "\n"
                "注：时间线管理请使用 .tl 指令"
            ),
        )
    
    async def bt(self, ctx: CommandContext) -> bool:
        """
        处理战斗命令
        """
        user_id = ctx.sender_id or "default"
        conversation_id = ctx.group_id or ctx.session_id or user_id
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
            if first_arg.endswith('t') and second_arg in ATTRIBUTE_ALIASES or second_arg in ATTRIBUTE_ALIASES.values():
                # 插入时间t 属性 时间t/影响值 格式
                if first_arg.endswith('t'):
                    insert_time = first_arg
                    attribute = second_arg
                    remaining_args = ctx.args[2:] if len(ctx.args) > 2 else []
                    result = await self._insert_action(storage_key, user_id, insert_time, attribute, remaining_args)
                    ctx.send(result)
                    return True
            
            # 检查是否是属性+时间/影响值格式
            if first_arg in ATTRIBUTE_ALIASES or first_arg in ATTRIBUTE_ALIASES.values():
                # 属性命令：属性 时间t/影响值 (笔记)
                resolved_attr = self._resolve_attribute_name(first_arg)
                remaining_args = ctx.args[1:] if len(ctx.args) > 1 else []
                result = await self._add_action(storage_key, user_id, resolved_attr, remaining_args)
                ctx.send(result)
                return True
        
        main_command = ctx.args[0].lower()
        
        # 老项目 bt 指令只支持：属性命令、wp命令、undo、插入时间
        # 以下指令已移至 tl 模块：new, join/in, leave/out, ready, start, end, status
        
        if main_command == 'wp':
            result = self._weapon_battle(storage_key, user_id, ctx.args[1:] if len(ctx.args) > 1 else [])
            ctx.send(result)
        
        elif main_command == 'undo':
            result = await self._undo_action(storage_key, user_id)
            ctx.send(result)
        
        elif main_command in ATTRIBUTE_ALIASES or main_command in ATTRIBUTE_ALIASES.values():
            # 属性命令（当只有一个参数时）
            resolved_attr = self._resolve_attribute_name(main_command)
            remaining_args = ctx.args[1:] if len(ctx.args) > 1 else []
            result = await self._add_action(storage_key, user_id, resolved_attr, remaining_args)
            ctx.send(result)
        
        else:
            ctx.send(self.system_reply.render("command_not_found", command=ctx.command))
        
        return True
    
    def _resolve_attribute_name(self, attribute: str) -> str:
        """解析属性名称，使用别名映射"""
        return ATTRIBUTE_ALIASES.get(attribute, attribute)

    def _get_battle(self, storage_key: str) -> Dict:
        """
        获取当前活跃的战斗对象
        适配 StorageBackend 的数据结构：{"active_battle_id": xxx, "player": {}, "battle_list": {"xxx": {...}}}
        """
        data = StorageBackend.load_battle(storage_key)
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
                "ready": [],
                "timeline": {},
                "current_time": 0,
                "max_time": 0,
                "scheduled_events": []
            }

    def _save_battle(self, storage_key: str, battle: Dict):
        """
        保存战斗数据
        适配 StorageBackend 的数据结构
        """
        # 先加载现有数据
        data = StorageBackend.load_battle(storage_key)

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
            new_battle_id = f"battle_{int(time.time())}"
            data["active_battle_id"] = new_battle_id
            data["battle_list"][new_battle_id] = battle

        StorageBackend.save_battle(storage_key, data)

    def _set_active_battle(self, storage_key: str, battle_id: str):
        """设置当前活跃的战斗"""
        data = StorageBackend.load_battle(storage_key)
        data["active_battle_id"] = battle_id
        StorageBackend.save_battle(storage_key, data)

    def _clear_active_battle(self, storage_key: str):
        """清除当前活跃的战斗"""
        data = StorageBackend.load_battle(storage_key)
        data["active_battle_id"] = None
        StorageBackend.save_battle(storage_key, data)
    
    def _get_character_module(self):
        """获取角色模块"""
        from ..character.character import character_module
        return character_module
    
    async def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色"""
        char_module = self._get_character_module()
        return await char_module.get_active_character(user_id)
    
    async def _get_character_attributes(self, user_id: str, character_name: str) -> Dict[str, float]:
        """获取角色的最终属性值（包含Buff修正）"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return {}
        
        # 获取角色基础属性
        char_data = active_char.get('data', {})
        attributes = {}
        
        # 常见属性映射
        attr_keys = ['力量', '敏捷', '体质', '智力', '感知', '魅力']
        for key in attr_keys:
            if key in char_data:
                try:
                    attributes[key] = float(char_data[key])
                except (ValueError, TypeError):
                    attributes[key] = 0.0
        
        # TODO: 从Buff系统获取属性修正
        # TODO: 从资源修正系统获取属性修正
        
        return attributes
    
    async def _get_final_attribute(self, user_id: str, attribute: str) -> Optional[float]:
        """获取角色的最终属性值"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return None
        
        char_data = active_char.get('data', {})
        
        # 直接检查
        if attribute in char_data:
            try:
                return float(char_data[attribute])
            except (ValueError, TypeError):
                pass
        
        # 尝试别名
        for alias, canonical in ATTRIBUTE_ALIASES.items():
            if canonical == attribute and alias in char_data:
                try:
                    return float(char_data[alias])
                except (ValueError, TypeError):
                    pass
        
        return None
    
    def _parse_time_input(self, time_input: str, default_attribute_value: float = None):
        """
        解析时间输入
        格式：时间t/影响值 或 时间t 或 纯数字（影响值）
        返回：(time, impact_value, error_message)
        """
        if '/' in time_input:
            parts = time_input.split('/')
            if len(parts) != 2:
                return None, None, "invalid_time_format"
            
            time_part = parts[0].strip()
            impact_part = parts[1].strip()
            
            # 解析时间
            try:
                if time_part.endswith('t'):
                    time_val = float(time_part[:-1])
                else:
                    time_val = float(time_part)
            except ValueError:
                return None, None, "invalid_time_value"
            
            # 解析影响值
            try:
                impact_val = float(impact_part)
            except ValueError:
                return None, None, "invalid_impact_value"
            
            return time_val, impact_val, None
        else:
            # 格式：时间t 或 纯数字（作为影响值）
            try:
                if time_input.endswith('t'):
                    time_val = float(time_input[:-1])
                    # 如果只有时间，影响值为属性值的一半
                    if default_attribute_value is not None:
                        impact_val = default_attribute_value / 2
                    else:
                        impact_val = 10  # 默认影响值
                else:
                    # 如果是纯数字，这是影响值，时间默认为1
                    impact_val = float(time_input)
                    time_val = 1.0
            except ValueError:
                return None, None, "invalid_input"
            
            return time_val, impact_val, None
    
    def _round_value(self, value: float, precision: int = 2) -> float:
        """根据精度四舍五入（保留本地方法，内部使用统一配置）"""
        return round(value, precision)
    
    def _format_time(self, value: float) -> Union[int, float]:
        """格式化时间值"""
        return game_config.round_value(value, "time")
    
    def _format_impact(self, value: float) -> Union[int, float]:
        """格式化影响值"""
        return game_config.round_value(value, "impact")
    
    def _create_battle(self, storage_key: str, user_id: str, name: str) -> str:
        """
        创建新战斗
        """
        # 先检查是否已有活跃战斗
        data = StorageBackend.load_battle(storage_key)
        active_battle_id = data.get("active_battle_id")

        if active_battle_id and active_battle_id in data.get("battle_list", {}):
            existing_battle = data["battle_list"][active_battle_id]
            if existing_battle.get("status") != "idle":
                return self.reply.render("battle_already_exists")

        # 创建新战斗
        import time
        new_battle_id = f"battle_{int(time.time())}"

        new_battle = {
            "name": name,
            "creator": user_id,
            "status": "ready",
            "participants": {user_id: {}},
            "ready": [],
            "timeline": {},
            "current_time": 0,
            "max_time": 0,
            "scheduled_events": []
        }

        # 保存到数据结构中
        if "battle_list" not in data:
            data["battle_list"] = {}
        data["battle_list"][new_battle_id] = new_battle
        data["active_battle_id"] = new_battle_id

        StorageBackend.save_battle(storage_key, data)
        return self.reply.render("battle_created", name=name)
    
    async def _join_battle(self, storage_key: str, user_id: str) -> str:
        """加入战斗"""
        battle = self._get_battle(storage_key)

        if battle.get("status") == "idle":
            return self.reply.render("no_battle")

        if user_id in battle["participants"]:
            # 用户已存在，检查是否有角色参与
            if not battle["participants"][user_id]:
                battle["participants"][user_id] = {}
        else:
            battle["participants"][user_id] = {}

        # 获取用户激活的角色并添加到战斗
        active_char = await self._get_active_character(user_id)
        if active_char:
            char_name = str(active_char.get('name', '未知角色'))
            if char_name not in battle["participants"][user_id]:
                battle["participants"][user_id][char_name] = {
                    "status": "参与中",
                    "last_action_time": 0
                }

        self._save_battle(storage_key, battle)
        if active_char:
            char_name = str(active_char.get('name', '未知角色'))
            return self.reply.render("status_joined", name=char_name)

        return self.reply.render("joined_battle")

    async def _leave_battle(self, storage_key: str, user_id: str) -> str:
        """离开战斗"""
        battle = self._get_battle(storage_key)

        if user_id not in battle["participants"] or not battle["participants"][user_id]:
            return self.reply.render("not_in_battle")

        # 获取角色名
        active_char = await self._get_active_character(user_id)
        if active_char:
            char_name = str(active_char.get('name', '未知角色'))
            if char_name in battle["participants"][user_id]:
                del battle["participants"][user_id][char_name]
                self._save_battle(storage_key, battle)
                return self.reply.render("status_left", name=char_name)

        self._save_battle(storage_key, battle)
        return self.reply.render("left_battle")

    def _toggle_ready(self, storage_key: str, user_id: str) -> str:
        """切换准备状态"""
        battle = self._get_battle(storage_key)

        if user_id not in battle["participants"] or not battle["participants"][user_id]:
            return self.reply.render("not_in_battle")

        if "ready" not in battle:
            battle["ready"] = []

        if user_id in battle["ready"]:
            battle["ready"].remove(user_id)
            self._save_battle(storage_key, battle)
            return self.reply.render("unready")
        else:
            battle["ready"].append(user_id)
            self._save_battle(storage_key, battle)
            return self.reply.render("ready")

    def _start_battle(self, storage_key: str, user_id: str) -> str:
        """开始战斗"""
        battle = self._get_battle(storage_key)

        if battle.get("status") == "idle":
            return self.reply.render("no_battle")

        if battle.get("creator") != user_id:
            return self.reply.render("not_creator")

        # 至少需要有一个准备好的玩家或者有参与者
        ready_count = len(battle.get("ready", []))
        participants_count = len(battle.get("participants", {}))
        if ready_count < 1 and participants_count < 1:
            return self.reply.render("no_ready_players")

        battle["status"] = "active"
        battle["current_time"] = 0
        battle["max_time"] = 0
        battle["timeline"] = {}

        self._save_battle(storage_key, battle)
        return self.reply.render("battle_started")

    def _end_battle(self, storage_key: str, user_id: str) -> str:
        """结束战斗"""
        battle = self._get_battle(storage_key)

        if battle.get("status") == "idle":
            return self.reply.render("no_battle")

        if battle.get("creator") != user_id:
            return self.reply.render("not_creator")

        battle["status"] = "idle"
        battle["name"] = None
        battle["creator"] = None
        battle["participants"] = {}
        battle["ready"] = []
        battle["timeline"] = {}
        battle["current_time"] = 0
        battle["max_time"] = 0
        battle["scheduled_events"] = []

        self._save_battle(storage_key, battle)
        # 清除活跃战斗ID
        self._clear_active_battle(storage_key)
        return self.reply.render("battle_ended")

    def _battle_status(self, storage_key: str) -> str:
        """获取战斗状态"""
        battle = self._get_battle(storage_key)

        if battle.get("status") == "idle":
            return self.reply.render("no_battle")

        ready_count = len(battle.get("ready", []))
        participants_count = len(battle.get("participants", {}))

        lines = [
            self.reply.render("battle_status_header", name=battle.get("name", "未命名")),
            self.reply.render("status_label") + battle.get("status", "unknown"),
            self.reply.render("participants_label") + str(participants_count),
            self.reply.render("ready_label") + str(ready_count)
        ]

        # 如果战斗已激活，显示时间轴
        if battle.get("status") == "active" and battle.get("timeline"):
            lines.append("")
            lines.append(self.reply.render("timeline_current_max_time",
                current=battle.get("current_time", 0),
                max=battle.get("max_time", 0)))

        return "\n".join(lines)
    
    async def _add_action(self, storage_key: str, user_id: str, attribute: str, args: List[str]) -> str:
        """添加战斗行动"""
        battle = self._get_battle(storage_key)

        # 如果没有战斗数据，自动创建一个（兼容 timeline 创建的时间线）
        if not battle:
            battle = {
                "name": "时间线战斗",
                "status": "active",
                "participants": {},
                "timeline": {},
                "current_time": 0,
                "max_time": 0,
                "created_at": self._get_current_time()
            }
        
        # 如果状态不是 active，设置为 active（兼容 tl new 创建的时间线）
        if battle.get("status") not in ("active", "ready"):
            return self.reply.render("battle_not_active")

        # 获取用户当前激活的角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        character_name = str(active_char.get('name', '未知角色'))

        # 确保 participants 存在
        if "participants" not in battle:
            battle["participants"] = {}

        # 确保用户在参与者列表中
        if user_id not in battle["participants"]:
            battle["participants"][user_id] = {}

        if character_name not in battle["participants"][user_id]:
            battle["participants"][user_id][character_name] = {
                "status": "参与中",
                "last_action_time": 0
            }

        participant = battle["participants"][user_id][character_name]

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
                if arg.startswith('(') or arg.endswith(')'):
                    notes = ' '.join(args[i:]).strip('()')
                    break
            if not notes and len(args) > 1:
                notes = ' '.join(args[1:])

        # 解析时间输入
        time_val, impact_val, error = self._parse_time_input(time_input, attribute_value)
        if error:
            return self.reply.render("invalid_input")

        # 计算行动时间点
        start_time = participant.get('last_action_time', 0)
        new_time_point = start_time + time_val
        new_time_point = self._format_time(new_time_point)

        # 创建行动记录
        action = {
            "user_id": user_id,
            "character_name": character_name,
            "start_time": start_time,
            "lead_time": time_val,
            "attribute_used": attribute,
            "impact_value": impact_val,
            "notes": notes
        }

        # 确保 timeline 存在
        if "timeline" not in battle:
            battle["timeline"] = {}

        # 添加到时间轴
        time_str = str(new_time_point)
        if time_str not in battle["timeline"]:
            battle["timeline"][time_str] = []
        battle["timeline"][time_str].append(action)

        # 更新参与者最后行动时间
        participant['last_action_time'] = new_time_point

        # 更新最大时间
        current_max = battle.get('max_time', 0)
        battle['max_time'] = max(current_max, new_time_point)

        # 重新计算当前时间
        self._recalculate_current_time(battle)

        # 保存战斗数据
        self._save_battle(storage_key, battle)
        
        # 递减当前角色的计数模式buff事件（在添加新行动之后）
        self._decrement_count_based_events(storage_key, user_id, character_name)
        
        # 执行到期的定时事件
        executed = self.execute_scheduled_events(storage_key, user_id)
        
        # 如果有到期事件，将消息添加到返回结果中
        timeline_result = self._format_timeline_display(battle)
        if executed:
            event_msgs = "\n【到期事件】\n" + "\n".join(executed)
            return timeline_result + event_msgs
        
        return timeline_result
    
    def _decrement_count_based_events(self, storage_key: str, user_id: str, character_name: str):
        """
        递减指定用户当前角色的计数模式事件的剩余次数
        包括buff、护盾、资源修饰事件
        """
        from ...infrastructure.scheduler import scheduler_module
        
        battle = self._get_battle(storage_key)
        if battle.get("status") != "active":
            return
        
        scheduled_events = battle.get('scheduled_events', [])
        
        events_to_remove = []
        
        for i, event in enumerate(scheduled_events):
            # 检查是否为该用户和角色的计数模式事件
            if (event.get('user_id') == user_id and 
                event.get('character_name') == character_name and
                event.get('mode') == 'count_based' and
                event.get('remaining_count') is not None):
                
                # 递减剩余次数
                event['remaining_count'] -= 1
                
                # 检查是否已达到次数限制
                if event['remaining_count'] <= 0:
                    events_to_remove.append(i)
        
        # 从后往前删除已达到次数限制的事件
        for i in reversed(events_to_remove):
            del scheduled_events[i]
        
        # 保存数据
        if events_to_remove:
            self._save_battle(storage_key, battle)
    
    async def _insert_action(self, storage_key: str, user_id: str, insert_time: str, attribute: str, args: List[str]) -> str:
        """在指定时间点插入行动"""
        battle = self._get_battle(storage_key)

        # 如果没有战斗数据，自动创建一个（兼容 timeline 创建的时间线）
        if not battle:
            battle = {
                "name": "时间线战斗",
                "status": "active",
                "participants": {},
                "timeline": {},
                "current_time": 0,
                "max_time": 0,
                "created_at": self._get_current_time()
            }
        
        # 如果状态不是 active，设置为 active（兼容 tl new 创建的时间线）
        if battle.get("status") not in ("active", "ready"):
            return self.reply.render("battle_not_active")

        # 解析插入时间
        try:
            insert_time_val = float(insert_time.lower().replace('t', ''))
            insert_time_val = self._format_time(insert_time_val)
        except ValueError:
            return self.reply.render("invalid_time_value")

        # 验证角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        character_name = str(active_char.get('name', '未知角色'))

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
            notes = ' '.join(args[1:])

        # 解析时间输入
        time_val, impact_val, error = self._parse_time_input(time_input, attribute_value)
        if error:
            return self.reply.render("invalid_input")

        # 确保 timeline 存在
        if "timeline" not in battle:
            battle["timeline"] = {}

        # 检查该时间点是否有正在进行的行动
        found_ongoing = False
        for time_str, actions in battle.get('timeline', {}).items():
            for action in actions:
                action_start = float(time_str) - action['lead_time']
                action_end = float(time_str)

                if action_start < insert_time_val < action_end and action['user_id'] == user_id:
                    # 提前终止原行动
                    elapsed = insert_time_val - action_start
                    completion = elapsed / action['lead_time']
                    completed_impact = action['impact_value'] * completion
                    action['impact_value'] = self._format_impact(completed_impact)
                    action['lead_time'] = self._format_time(elapsed)
                    action['notes'] = "[提前终止] " + action['notes'] if action['notes'] else "[提前终止]"
                    found_ongoing = True
                    break
            if found_ongoing:
                break

        # 添加新行动
        if not found_ongoing:
            new_time_point = insert_time_val + time_val
            new_time_point = self._format_time(new_time_point)

            action = {
                "user_id": user_id,
                "character_name": character_name,
                "start_time": insert_time_val,
                "lead_time": time_val,
                "attribute_used": attribute,
                "impact_value": impact_val,
                "notes": notes
            }

            time_str = str(new_time_point)
            if time_str not in battle["timeline"]:
                battle["timeline"][time_str] = []
            battle["timeline"][time_str].append(action)
            
            # 更新参与者最后行动时间
            if user_id in battle["participants"] and character_name in battle["participants"][user_id]:
                battle["participants"][user_id][character_name]['last_action_time'] = new_time_point

            # 更新最大时间
            current_max = battle.get('max_time', 0)
            battle['max_time'] = max(current_max, new_time_point)

        # 重新计算当前时间
        self._recalculate_current_time(battle)

        # 保存战斗数据
        self._save_battle(storage_key, battle)
        
        # 执行到期的定时事件
        executed = self.execute_scheduled_events(storage_key, user_id)
        
        # 如果有到期事件，将消息添加到返回结果中
        timeline_result = self._format_timeline_display(battle)
        if executed:
            event_msgs = "\n【到期事件】\n" + "\n".join(executed)
            return timeline_result + event_msgs
        
        return timeline_result
    
    async def _undo_action(self, storage_key: str, user_id: str) -> str:
        """撤销最后的行动"""
        battle = self._get_battle(storage_key)

        if battle.get("status") != "active":
            return self.reply.render("battle_not_active")

        # 获取用户当前激活的角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        character_name = str(active_char.get('name', '未知角色'))

        # 找到该用户该角色的最后一个行动
        last_time_point = None
        last_action_index = -1
        last_action_time_str = None

        timeline = battle.get('timeline', {})
        for time_str, actions in timeline.items():
            for i, action in enumerate(actions):
                if (action['user_id'] == user_id and
                    str(action['character_name']) == character_name):
                    current_time = float(time_str) - action['lead_time']
                    if last_time_point is None or current_time > last_time_point:
                        last_time_point = current_time
                        last_action_index = i
                        last_action_time_str = time_str

        if last_action_index == -1:
            return self.reply.render("no_action_to_undo")

        # 删除行动
        if 'timeline' in battle and last_action_time_str in battle['timeline']:
            del battle['timeline'][last_action_time_str][last_action_index]
            if not battle['timeline'][last_action_time_str]:
                del battle['timeline'][last_action_time_str]

        # 重新计算参与者的最后行动时间
        latest_action_time = 0
        timeline = battle.get('timeline', {})
        for time_str, actions in timeline.items():
            for action in actions:
                if (action['user_id'] == user_id and
                    str(action['character_name']) == character_name):
                    action_time = float(time_str) - action['lead_time']
                    latest_action_time = max(latest_action_time, action_time)

        participants = battle.get('participants', {})
        if user_id in participants and character_name in participants[user_id]:
            battle['participants'][user_id][character_name]['last_action_time'] = latest_action_time

        # 重新计算max_time和current_time
        max_time = 0
        for time_str in timeline.keys():
            time_val = float(time_str)
            max_time = max(max_time, time_val)

        battle['max_time'] = self._format_time(max_time)
        self._recalculate_current_time(battle)

        # 恢复被撤销的计数模式事件（恢复1次）
        self._restore_count_based_events(storage_key, user_id, character_name)
        
        # 执行到期的定时事件
        executed = self.execute_scheduled_events(storage_key, user_id)
        
        # 保存战斗数据
        self._save_battle(storage_key, battle)
        
        # 返回结果
        result = self.reply.render("action_undone", name=character_name)
        if executed:
            event_msgs = "\n【到期事件】\n" + "\n".join(executed)
            result += event_msgs
        return result
    
    def _restore_count_based_events(self, storage_key: str, user_id: str, character_name: str):
        """
        恢复指定用户当前角色的计数模式事件的剩余次数（在撤销行动时调用）
        """
        battle = self._get_battle(storage_key)
        if battle.get("status") != "active":
            return
        
        scheduled_events = battle.get('scheduled_events', [])
        
        for event in scheduled_events:
            # 检查是否为该用户和角色的计数模式事件
            if (event.get('user_id') == user_id and 
                event.get('character_name') == character_name and
                event.get('mode') == 'count_based' and
                event.get('remaining_count') is not None):
                
                # 恢复剩余次数（增加1）
                event['remaining_count'] += 1
        
        # 保存数据
        self._save_battle(storage_key, battle)
    
    def _recalculate_current_time(self, battle: Dict):
        """重新计算当前时间（所有角色最后行动时间的最小值）"""
        last_times = []
        participants = battle.get('participants', {})
        for user_participants in participants.values():
            for participant_info in user_participants.values():
                if participant_info.get('status') == '参与中':
                    last_times.append(participant_info.get('last_action_time', 0))

        if last_times:
            battle['current_time'] = min(last_times)
            battle['current_time'] = self._format_time(battle['current_time'])
        else:
            battle['current_time'] = 0
    
    def _format_timeline_display(self, battle: Dict) -> str:
        """格式化时间轴显示"""
        timeline = battle.get('timeline', {})
        if not timeline:
            return self.reply.render("empty_timeline")
        
        # 按时间点排序
        sorted_times = sorted([float(t) for t in timeline.keys()])
        
        current_time = battle.get('current_time', 0)
        max_time = battle.get('max_time', 0)
        
        lines = [
            self.reply.render("timeline_header", name=battle.get('name', '未知战斗')),
            self.reply.render("timeline_current_max_time", 
                current=self._format_time(current_time), 
                max=self._format_time(max_time))
        ]
        
        for time_point in sorted_times:
            if time_point < current_time:
                continue
            
            time_str = f"{time_point:.1f}" if time_point.is_integer() else f"{time_point}"
            actions = timeline.get(time_str, [])
            
            if actions:
                # 时间分隔符
                dashes = "—" * 5
                lines.append(f"\n{dashes} {time_str}t {dashes}")
                
                for action in actions:
                    # 检查角色状态
                    user_id = action['user_id']
                    char_name = action['character_name']
                    
                    user_participants = battle['participants'].get(user_id, {})
                    char_info = user_participants.get(char_name, {})
                    
                    if char_info.get('status') != '参与中':
                        continue
                    
                    # 显示行动
                    start_time = self._format_time(action['start_time'])
                    lead_time = self._format_time(action['lead_time'])
                    impact_value = self._format_impact(action['impact_value'])
                    
                    lines.append(f"  [{action['character_name']}]")
                    lines.append(f"    起始: {start_time}t | 前摇: {lead_time}t")
                    lines.append(f"    属性: {action['attribute_used']} | 影响: {impact_value}")
                    if action.get('notes'):
                        lines.append(f"    {action['notes']}")
        
        # 显示定时事件
        scheduled_events = battle.get('scheduled_events', [])
        time_based_events = [
            e for e in scheduled_events 
            if e.get('mode') == 'time_based' and e.get('end_time') and current_time < e.get('end_time', 0)
        ]
        
        if time_based_events:
            lines.append("\n【定时事件】")
            for event in time_based_events:
                lines.append(self.reply.render("scheduled_event_display",
                    time=event.get('end_time', 0),
                    desc=event.get('action_description', '')))
        
        return "\n".join(lines)
    
    def _weapon_battle(self, storage_key: str, user_id: str, args: List[str]) -> str:
        """武器战斗指令（需要武器系统）"""
        battle = self._get_battle(storage_key)
        
        if battle["status"] != "active":
            return self.reply.render("battle_not_active")
        
        # TODO: 集成武器系统
        return self.reply.render("weapon_battle_placeholder")
    
    def schedule_buff_event(self, conversation_id: str, user_id: str, character_name: str,
                          action_description: str, duration_or_count: float,
                          callback_path: str, callback_args: Dict, callback_message: str,
                          mode: str = 'time_based') -> bool:
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
            event_type='buff'
        )
    
    def execute_scheduled_events(self, conversation_id: str, user_id: str = None) -> List[str]:
        """
        执行到期的定时事件
        
        委托给 infrastructure.scheduler_module 处理
        """
        from ...infrastructure.scheduler import execute_scheduled_events
        return execute_scheduled_events(conversation_id, user_id)


battle_module = BattleModule()
