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
from typing import Dict, List, Optional, Any

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry

# 战斗数据存储
_battle_storage: Dict[str, Dict] = {}

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
    
    支持的指令格式：
    - .bt - 显示帮助
    - .bt new <战斗名> - 创建新战斗
    - .bt join/in - 加入战斗
    - .bt leave/out - 离开战斗
    - .bt ready - 准备/取消准备
    - .bt start - 开始战斗
    - .bt end - 结束战斗
    - .bt status - 查看战斗状态
    - <属性> <时间>t/<影响值> (笔记) - 添加战斗行动
    - wp <时间>t/<影响值> (笔记) - 武器战斗
    - 插入时间t <属性> <时间>t/<影响值> (笔记) - 插入行动
    - undo - 撤销最后行动
    """
    
    def __init__(self):
        self.reply = ReplyManager("battle")
    
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
                "in - 加入战斗\n"
                "out - 退出战斗\n"
                "undo - 撤销最后行动\n"
                "\n"
                "增幅武器可以使用t或者数字\n"
                "火力武器只可以使用数字\n"
                "其他武器不可以使用指令\n"
                "\n"
                "示例:\n"
                "  力量 5t/10 (备注) → 使用力量属性，5时间，影响值10\n"
                "  5t 力量 3t/5 → 在5t插入力量行动\n"
                "  wp 5 → 使用武器，5时间"
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
                    result = self._insert_action(storage_key, user_id, insert_time, attribute, remaining_args)
                    ctx.send(result)
                    return True
            
            # 检查是否是属性+时间/影响值格式
            if first_arg in ATTRIBUTE_ALIASES or first_arg in ATTRIBUTE_ALIASES.values():
                # 属性命令：属性 时间t/影响值 (笔记)
                resolved_attr = self._resolve_attribute_name(first_arg)
                remaining_args = ctx.args[1:] if len(ctx.args) > 1 else []
                result = self._add_action(storage_key, user_id, resolved_attr, remaining_args)
                ctx.send(result)
                return True
        
        main_command = ctx.args[0].lower()
        
        if main_command == 'new':
            if len(ctx.args) < 2:
                response = self.reply.render("need_battle_name")
                ctx.send(response)
                return True
            battle_name = " ".join(ctx.args[1:])
            result = self._create_battle(storage_key, user_id, battle_name)
            ctx.send(result)
        
        elif main_command in ('join', 'in'):
            result = self._join_battle(storage_key, user_id)
            ctx.send(result)
        
        elif main_command in ('leave', 'out'):
            result = self._leave_battle(storage_key, user_id)
            ctx.send(result)
        
        elif main_command == 'ready':
            result = self._toggle_ready(storage_key, user_id)
            ctx.send(result)
        
        elif main_command == 'start':
            result = self._start_battle(storage_key, user_id)
            ctx.send(result)
        
        elif main_command == 'end':
            result = self._end_battle(storage_key, user_id)
            ctx.send(result)
        
        elif main_command == 'status':
            result = self._battle_status(storage_key)
            ctx.send(result)
        
        elif main_command == 'wp':
            result = self._weapon_battle(storage_key, user_id, ctx.args[1:] if len(ctx.args) > 1 else [])
            ctx.send(result)
        
        elif main_command == 'undo':
            result = self._undo_action(storage_key, user_id)
            ctx.send(result)
        
        elif main_command in ATTRIBUTE_ALIASES or main_command in ATTRIBUTE_ALIASES.values():
            # 属性命令（当只有一个参数时）
            resolved_attr = self._resolve_attribute_name(main_command)
            remaining_args = ctx.args[1:] if len(ctx.args) > 1 else []
            result = self._add_action(storage_key, user_id, resolved_attr, remaining_args)
            ctx.send(result)
        
        else:
            ctx.send(self.reply.render("help"))
        
        return True
    
    def _resolve_attribute_name(self, attribute: str) -> str:
        """解析属性名称，使用别名映射"""
        return ATTRIBUTE_ALIASES.get(attribute, attribute)
    
    def _get_battle(self, storage_key: str) -> Dict:
        if storage_key not in _battle_storage:
            _battle_storage[storage_key] = {
                "name": None,
                "creator": None,
                "participants": {},  # {user_id: {character_name: {status, last_action_time}}}
                "ready": [],
                "status": "idle",  # idle, ready, active, ended
                "timeline": {},  # {time_str: [actions]}
                "current_time": 0,
                "max_time": 0,
                "scheduled_events": [],
                "player": {}  # {user_id: {player_id}}
            }
        return _battle_storage[storage_key]
    
    def _get_character_module(self):
        """获取角色模块"""
        from trpg.character import character_module
        return character_module
    
    def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色"""
        char_module = self._get_character_module()
        return char_module.get_active_character(user_id)
    
    def _get_character_attributes(self, user_id: str, character_name: str) -> Dict[str, float]:
        """获取角色的最终属性值（包含Buff修正）"""
        active_char = self._get_active_character(user_id)
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
    
    def _get_final_attribute(self, user_id: str, attribute: str) -> Optional[float]:
        """获取角色的最终属性值"""
        active_char = self._get_active_character(user_id)
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
        """根据精度四舍五入"""
        return round(value, precision)
    
    def _create_battle(self, storage_key: str, user_id: str, name: str) -> str:
        battle = self._get_battle(storage_key)
        
        if battle["status"] != "idle":
            return self.reply.render("battle_already_exists")
        
        battle["name"] = name
        battle["creator"] = user_id
        battle["status"] = "ready"
        battle["participants"] = {user_id: {}}
        
        return self.reply.render("battle_created", name=name)
    
    def _join_battle(self, storage_key: str, user_id: str) -> str:
        battle = self._get_battle(storage_key)
        
        if battle["status"] == "idle":
            return self.reply.render("no_battle")
        
        if user_id in battle["participants"]:
            # 用户已存在，检查是否有角色参与
            if not battle["participants"][user_id]:
                battle["participants"][user_id] = {}
        else:
            battle["participants"][user_id] = {}
        
        # 获取用户激活的角色并添加到战斗
        active_char = self._get_active_character(user_id)
        if active_char:
            char_name = str(active_char.get('name', '未知角色'))
            if char_name not in battle["participants"][user_id]:
                battle["participants"][user_id][char_name] = {
                    "status": "参与中",
                    "last_action_time": 0
                }
            return self.reply.render("status_joined", name=char_name)
        
        return self.reply.render("joined_battle")
    
    def _leave_battle(self, storage_key: str, user_id: str) -> str:
        battle = self._get_battle(storage_key)
        
        if user_id not in battle["participants"] or not battle["participants"][user_id]:
            return self.reply.render("not_in_battle")
        
        # 获取角色名
        active_char = self._get_active_character(user_id)
        if active_char:
            char_name = str(active_char.get('name', '未知角色'))
            if char_name in battle["participants"][user_id]:
                del battle["participants"][user_id][char_name]
                return self.reply.render("status_left", name=char_name)
        
        return self.reply.render("left_battle")
    
    def _toggle_ready(self, storage_key: str, user_id: str) -> str:
        battle = self._get_battle(storage_key)
        
        if user_id not in battle["participants"] or not battle["participants"][user_id]:
            return self.reply.render("not_in_battle")
        
        if user_id in battle["ready"]:
            battle["ready"].remove(user_id)
            return self.reply.render("unready")
        else:
            battle["ready"].append(user_id)
            return self.reply.render("ready")
    
    def _start_battle(self, storage_key: str, user_id: str) -> str:
        battle = self._get_battle(storage_key)
        
        if battle["status"] == "idle":
            return self.reply.render("no_battle")
        
        if user_id != battle["creator"]:
            return self.reply.render("not_creator")
        
        # 至少需要有一个准备好的玩家或者有参与者
        if len(battle["ready"]) < 1 and len(battle["participants"]) < 1:
            return self.reply.render("no_ready_players")
        
        battle["status"] = "active"
        battle["current_time"] = 0
        battle["max_time"] = 0
        battle["timeline"] = {}
        
        return self.reply.render("battle_started")
    
    def _end_battle(self, storage_key: str, user_id: str) -> str:
        battle = self._get_battle(storage_key)
        
        if battle["status"] == "idle":
            return self.reply.render("no_battle")
        
        if user_id != battle["creator"]:
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
        
        return self.reply.render("battle_ended")
    
    def _battle_status(self, storage_key: str) -> str:
        battle = self._get_battle(storage_key)
        
        if battle["status"] == "idle":
            return self.reply.render("no_battle")
        
        lines = [
            self.reply.render("battle_status_header", name=battle.get("name", "未命名")),
            self.reply.render("status_label") + battle["status"],
            self.reply.render("participants_label") + str(len(battle["participants"])),
            self.reply.render("ready_label") + str(len(battle["ready"]))
        ]
        
        # 如果战斗已激活，显示时间轴
        if battle["status"] == "active" and battle.get("timeline"):
            lines.append("")
            lines.append(self.reply.render("timeline_current_max_time", 
                current=battle.get("current_time", 0), 
                max=battle.get("max_time", 0)))
        
        return "\n".join(lines)
    
    def _add_action(self, storage_key: str, user_id: str, attribute: str, args: List[str]) -> str:
        """添加战斗行动"""
        battle = self._get_battle(storage_key)
        
        if battle["status"] != "active":
            return self.reply.render("battle_not_active")
        
        # 获取用户当前激活的角色
        active_char = self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")
        
        character_name = str(active_char.get('name', '未知角色'))
        
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
        attribute_value = self._get_final_attribute(user_id, attribute)
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
        new_time_point = self._round_value(new_time_point)
        
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
        
        # 返回时间轴显示
        return self._format_timeline_display(battle)
    
    def _insert_action(self, storage_key: str, user_id: str, insert_time: str, attribute: str, args: List[str]) -> str:
        """在指定时间点插入行动"""
        battle = self._get_battle(storage_key)
        
        if battle["status"] != "active":
            return self.reply.render("battle_not_active")
        
        # 解析插入时间
        try:
            insert_time_val = float(insert_time.lower().replace('t', ''))
            insert_time_val = self._round_value(insert_time_val)
        except ValueError:
            return self.reply.render("invalid_time_value")
        
        # 验证角色
        active_char = self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")
        
        character_name = str(active_char.get('name', '未知角色'))
        
        # 检查属性
        attribute_value = self._get_final_attribute(user_id, attribute)
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
        
        # 检查该时间点是否有正在进行的行动
        found_ongoing = False
        for time_str, actions in battle['timeline'].items():
            for action in actions:
                action_start = float(time_str) - action['lead_time']
                action_end = float(time_str)
                
                if action_start < insert_time_val < action_end and action['user_id'] == user_id:
                    # 提前终止原行动
                    elapsed = insert_time_val - action_start
                    completion = elapsed / action['lead_time']
                    completed_impact = action['impact_value'] * completion
                    action['impact_value'] = self._round_value(completed_impact)
                    action['lead_time'] = self._round_value(elapsed)
                    action['notes'] = "[提前终止] " + action['notes'] if action['notes'] else "[提前终止]"
                    found_ongoing = True
                    break
            if found_ongoing:
                break
        
        # 添加新行动
        if not found_ongoing:
            new_time_point = insert_time_val + time_val
            new_time_point = self._round_value(new_time_point)
            
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
        
        return self._format_timeline_display(battle)
    
    def _undo_action(self, storage_key: str, user_id: str) -> str:
        """撤销最后的行动"""
        battle = self._get_battle(storage_key)
        
        if battle["status"] != "active":
            return self.reply.render("battle_not_active")
        
        # 获取用户当前激活的角色
        active_char = self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")
        
        character_name = str(active_char.get('name', '未知角色'))
        
        # 找到该用户该角色的最后一个行动
        last_time_point = None
        last_action_index = -1
        last_action_time_str = None
        
        for time_str, actions in battle['timeline'].items():
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
        del battle['timeline'][last_action_time_str][last_action_index]
        if not battle['timeline'][last_action_time_str]:
            del battle['timeline'][last_action_time_str]
        
        # 重新计算参与者的最后行动时间
        latest_action_time = 0
        for time_str, actions in battle['timeline'].items():
            for action in actions:
                if (action['user_id'] == user_id and 
                    str(action['character_name']) == character_name):
                    action_time = float(time_str) - action['lead_time']
                    latest_action_time = max(latest_action_time, action_time)
        
        if user_id in battle['participants'] and character_name in battle['participants'][user_id]:
            battle['participants'][user_id][character_name]['last_action_time'] = latest_action_time
        
        # 重新计算max_time和current_time
        max_time = 0
        for time_str in battle['timeline'].keys():
            time_val = float(time_str)
            max_time = max(max_time, time_val)
        
        battle['max_time'] = self._round_value(max_time)
        self._recalculate_current_time(battle)
        
        return self.reply.render("action_undone", name=character_name)
    
    def _recalculate_current_time(self, battle: Dict):
        """重新计算当前时间（所有角色最后行动时间的最小值）"""
        last_times = []
        for user_participants in battle['participants'].values():
            for participant_info in user_participants.values():
                if participant_info.get('status') == '参与中':
                    last_times.append(participant_info.get('last_action_time', 0))
        
        if last_times:
            battle['current_time'] = min(last_times)
            battle['current_time'] = self._round_value(battle['current_time'])
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
        
        lines = [
            self.reply.render("timeline_header", name=battle.get('name', '未知战斗')),
            self.reply.render("timeline_current_max_time", 
                current=current_time, 
                max=battle.get('max_time', 0))
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
                    lines.append(f"  [{action['character_name']}]")
                    lines.append(f"    起始: {action['start_time']:.1f}t | 前摇: {action['lead_time']:.1f}t")
                    lines.append(f"    属性: {action['attribute_used']} | 影响: {action['impact_value']:.1f}")
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
        
        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            character_name: 角色名
            action_description: 行动描述
            duration_or_count: 持续时间或生效次数
            callback_path: 回调函数路径
            callback_args: 回调函数参数
            callback_message: 回调执行提示
            mode: 模式 ('time_based' 或 'count_based')
        
        Returns:
            bool: 是否成功调度
        """
        storage_key = conversation_id
        battle = self._get_battle(storage_key)
        
        if battle["status"] != "active":
            return False
        
        # 获取当前时间点
        current_time = battle.get('current_time', 0)
        
        # 创建事件对象
        event = {
            'id': f"event_{int(time.time())}_{len(battle.get('scheduled_events', []))}",
            'event_type': 'buff',
            'action_description': action_description,
            'start_time': current_time,
            'user_id': user_id,
            'character_name': character_name,
            'callback_path': callback_path,
            'callback_args': callback_args,
            'callback_message': callback_message,
            'mode': mode
        }
        
        if mode == 'time_based':
            # 持续时间模式：当前时间 + 持续时间 = 结束时间
            event['end_time'] = current_time + duration_or_count
            event['remaining_count'] = None
        elif mode == 'count_based':
            # 生效次数模式：记录剩余次数
            event['remaining_count'] = int(duration_or_count)
            event['end_time'] = None
        else:
            return False
        
        # 添加到事件列表
        if 'scheduled_events' not in battle:
            battle['scheduled_events'] = []
        battle['scheduled_events'].append(event)
        
        return True
    
    def execute_scheduled_events(self, conversation_id: str, user_id: str = None) -> List[str]:
        """
        执行到期的定时事件
        
        Args:
            conversation_id: 会话ID
            user_id: 用户ID，如果指定则只执行该用户的到期事件
        
        Returns:
            List[str]: 执行结果消息列表
        """
        storage_key = conversation_id
        battle = self._get_battle(storage_key)
        
        if battle["status"] != "active":
            return []
        
        current_time = battle.get('current_time', 0)
        scheduled_events = battle.get('scheduled_events', [])
        
        executed_messages = []
        events_to_remove = []
        
        for i, event in enumerate(scheduled_events):
            # 检查是否为时间模式且已到期
            if (event.get('mode') == 'time_based' and 
                event.get('end_time') is not None and 
                current_time >= event.get('end_time', 0)):
                
                # 如果指定了用户ID，只执行该用户的事件
                if user_id is not None and event.get('user_id') != user_id:
                    continue
                
                # 执行回调
                if 'callback_path' in event and event['callback_path']:
                    try:
                        # 解析回调路径
                        callback_path = event['callback_path']
                        callback_args = event.get('callback_args', {})
                        
                        if callback_path == "trpg.buff.remove_expired_buff":
                            from trpg.buff import remove_expired_buff
                            remove_expired_buff(**callback_args)
                            executed_messages.append(event.get('callback_message', ''))
                    except Exception as e:
                        print(f"Error executing scheduled event callback: {e}")
                
                # 标记为删除
                events_to_remove.append(i)
        
        # 从后往前删除已执行的事件
        for i in reversed(events_to_remove):
            if i < len(scheduled_events):
                del scheduled_events[i]
        
        return executed_messages


battle_module = BattleModule()
