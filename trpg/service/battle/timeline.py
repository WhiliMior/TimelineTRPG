"""
时间线模块 - 管理时间线/战斗时间轴
迁移自老项目 Game/Runtime/Battle/TimelineSystem.py

功能：
- 时间线列表管理
- 时间线选择/删除
- 玩家ID注册
- 时间线显示
- 时间点查询

注意：根据新设计，战斗指令（in/out）已移至 battle 模块
"""
from typing import Dict, List, Optional
import re
from datetime import datetime

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend
from ...infrastructure.config.game_config import game_config
from ...infrastructure.timeline_formatter import timeline_formatter


class TimelineModule:
    """
    时间线模块（根据老项目设计）
    
    支持的指令格式：
    - .tl - 显示时间线列表
    - .tl new <名称> - 创建新时间线
    - .tl <序号> - 选择时间线
    - .tl del <序号>/all - 删除时间线
    - .tl show - 显示时间线
    - .tl get <时间点> - 查询时间节点
    """
    
    def __init__(self):
        self.reply = ReplyManager("timeline")
        self.system_reply = ReplyManager("system")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="tl",
            usage="[序号|new|del|show|get|acc] [参数]",
            summary="时间线管理",
            detail=(
                "- 显示时间线列表\n"
                "new {名称} - 创建新时间线\n"
                "{序号} - 选择时间线\n"
                "del {序号}/all - 删除时间线\n"
                "show - 显示时间线\n"
                "get {时间点} - 查询指定时间点\n"
                "acc {精度} - 设置时间精度(0=整数,1=0.1,2=0.01)\n"
            ),
        )
    
    async def tl(self, ctx: CommandContext) -> bool:
        """
        处理时间线命令
        """
        user_id = ctx.sender_id or "default"
        conversation_id = ctx.group_id or ctx.session_id or user_id
        is_group = ctx.group_id is not None
        storage_key = f"{conversation_id}"
        
        if not ctx.args:
            result = self._list_timelines(storage_key, user_id, is_group)
            ctx.send(result)
            return True
        
        main_command = ctx.args[0].lower()
        remaining_args = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
        
        if main_command == 'new':
            if not remaining_args:
                response = self.reply.render("need_battle_name")
                ctx.send(response)
                return True
            result = self._create_timeline(storage_key, user_id, is_group, remaining_args)
            ctx.send(result)
        
        elif main_command.isdigit():
            try:
                index = int(main_command)
                result = self._select_timeline(storage_key, user_id, is_group, index)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("index_must_be_number")
                ctx.send(response)
        
        elif main_command == 'del':
            if not remaining_args:
                response = self.reply.render("need_delete_argument")
                ctx.send(response)
                return True
            result = self._delete_timeline(storage_key, user_id, is_group, remaining_args)
            ctx.send(result)
        
        elif main_command == 'show':
            character_name = remaining_args if remaining_args else None
            result = self._show_timeline(storage_key, user_id, is_group, character_name)
            ctx.send(result)
        
        elif main_command == 'get':
            if not remaining_args:
                response = self.reply.render("need_time_point")
                ctx.send(response)
                return True
            result = self._get_time_point(storage_key, user_id, is_group, remaining_args)
            ctx.send(result)
        
        elif main_command == 'acc':
            result = self._set_accuracy(remaining_args)
            ctx.send(result)
        
        else:
            response = self.system_reply.render("command_not_found", command=ctx.command)
            ctx.send(response)
        
        return True
    
    def _get_battle_data(self, storage_key: str, is_group: bool) -> Dict:
        """获取战斗时间轴数据"""
        return StorageBackend.load_battle_timeline(storage_key, is_group)
    
    def _save_battle_data(self, storage_key: str, data: Dict, is_group: bool):
        """保存战斗时间轴数据"""
        StorageBackend.save_battle_timeline(storage_key, data, is_group)
    
    def _list_timelines(self, storage_key: str, user_id: str, is_group: bool) -> str:
        data = self._get_battle_data(storage_key, is_group)
        battle_list = data.get("battle_list", {})
        
        if not battle_list:
            return self.reply.render("no_timelines")
        
        lines = [self.reply.render("timeline_list_header")]
        
        # 按时间线ID排序
        sorted_ids = sorted(battle_list.keys(), key=lambda x: int(x) if x.isdigit() else 0)
        
        active_id = data.get("active_battle_id")
        
        for i, battle_id in enumerate(sorted_ids):
            battle = battle_list[battle_id]
            active = "●" if battle_id == active_id else "  "
            name = battle.get('name', '未命名')
            lines.append(f"[{i + 1}] [{active}] {name}")
        
        return "\n".join(lines)
    
    def _create_timeline(self, storage_key: str, user_id: str, is_group: bool, name: str) -> str:
        data = self._get_battle_data(storage_key, is_group)
        battle_list = data.get("battle_list", {})
        
        # 检查名称是否已存在
        for battle in battle_list.values():
            if battle.get('name') == name:
                return self.reply.render("battle_name_exists", name=name)
        
        # 使用时间戳作为新的战斗ID
        import time
        new_battle_id = str(int(time.time()))
        
        # 创建新的时间线（战斗）
        new_battle = {
            "name": name,
            "created_at": self._get_current_time(),
            "max_time": 0,
            "current_time": 0,
            "timeline": {},
            "participants": {},
            "scheduled_events": []
        }
        
        data["battle_list"][new_battle_id] = new_battle
        # 自动选择新创建的时间线
        data["active_battle_id"] = new_battle_id
        
        self._save_battle_data(storage_key, data, is_group)
        return self.reply.render("timeline_created", name=name)
    
    def _select_timeline(self, storage_key: str, user_id: str, is_group: bool, index: int) -> str:
        data = self._get_battle_data(storage_key, is_group)
        battle_list = data.get("battle_list", {})
        
        if not battle_list:
            return self.reply.render("no_timelines")
        
        # 按时间线ID排序
        sorted_ids = sorted(battle_list.keys(), key=lambda x: int(x) if x.isdigit() else 0)
        
        if index < 1 or index > len(sorted_ids):
            return self.reply.render("invalid_index")
        
        selected_id = sorted_ids[index - 1]
        selected_battle = battle_list[selected_id]
        
        data["active_battle_id"] = selected_id
        self._save_battle_data(storage_key, data, is_group)
        
        return self.reply.render("timeline_selected", name=selected_battle.get('name', '未命名'))
    
    def _delete_timeline(self, storage_key: str, user_id: str, is_group: bool, arg: str) -> str:
        data = self._get_battle_data(storage_key, is_group)
        battle_list = data.get("battle_list", {})

        if not battle_list:
            return self.reply.render("no_timelines")

        if arg.lower() == 'all':
            data["battle_list"] = {}
            data["active_battle_id"] = None
            self._save_battle_data(storage_key, data, is_group)
            return self.reply.render("all_timelines_deleted")

        # 按时间线ID排序
        sorted_ids = sorted(battle_list.keys(), key=lambda x: int(x) if x.isdigit() else 0)

        # 支持多个数字输入，如 "1 4 5"
        parts = arg.split()
        indices = [int(x) - 1 for x in parts if x.isdigit()]

        if not indices:
            return self.reply.render("invalid_index")

        # 验证所有序号
        invalid_indices = []
        valid_indices = []

        for idx in indices:
            if 0 <= idx < len(sorted_ids):
                valid_indices.append(idx)
            else:
                invalid_indices.append(idx + 1)

        if not valid_indices:
            return self.reply.render("invalid_index")

        # 从后往前删除，避免索引偏移
        deleted_names = []
        for idx in sorted(valid_indices, reverse=True):
            delete_id = sorted_ids[idx]
            deleted = battle_list.pop(delete_id)
            deleted_names.append(deleted.get('name', '未命名'))

            # 调整 active_battle_id
            active = data.get("active_battle_id")
            if active == delete_id:
                data["active_battle_id"] = None

        self._save_battle_data(storage_key, data, is_group)

        if len(valid_indices) == 1:
            return self.reply.render("timeline_deleted", name=deleted_names[0])
        else:
            if invalid_indices:
                return self.reply.render(
                    "timeline_multi_deleted_partial",
                    valid=len(valid_indices),
                    invalid=len(invalid_indices)
                )
            else:
                return self.reply.render("timeline_multi_deleted", count=len(valid_indices))
    
    def _set_accuracy(self, arg: str) -> str:
        """
        设置时间精度
        参数为小数位数，例如 0=整数，1=0.1，2=0.01
        """
        if not arg:
            current_precision = game_config.get_precision("time")
            min_unit = game_config.get_min_time_unit()
            return self.reply.render("timeline_current_accuracy", precision=current_precision, min_unit=min_unit)
        
        try:
            precision = int(arg)
            if precision < 0 or precision > 5:
                return self.reply.render("precision_range")

            # 设置时间精度
            if game_config.set_precision("time", precision):
                min_unit = game_config.get_min_time_unit()
                return self.reply.render("timeline_accuracy_set", precision=precision, min_unit=min_unit)
            else:
                return self.reply.render("save_config_failed")
        except ValueError:
            return self.reply.render("invalid_number")
    
    def _show_timeline(self, storage_key: str, user_id: str, is_group: bool, character_name: Optional[str]) -> str:
        """显示时间线（使用统一格式化器）"""
        data = self._get_battle_data(storage_key, is_group)
        active_id = data.get("active_battle_id")

        if active_id is None or not data.get("battle_list"):
            return self.reply.render("no_active_timeline")

        battle = data["battle_list"].get(active_id)
        if not battle:
            return self.reply.render("no_active_timeline")

        # 使用统一的 timeline 格式化器
        return timeline_formatter.format_timeline(battle, attribute_label="属性")
    
    def _get_time_point(self, storage_key: str, user_id: str, is_group: bool, time_point: str) -> str:
        data = self._get_battle_data(storage_key, is_group)
        active_id = data.get("active_battle_id")
        
        if active_id is None or not data.get("battle_list"):
            return self.reply.render("no_active_timeline")
        
        battle = data["battle_list"].get(active_id)
        if not battle:
            return self.reply.render("no_active_timeline")
        
        # 处理数字和数字+t格式
        processed_time_str = time_point.lower().replace('t', '')
        
        try:
            target_time = float(processed_time_str)
        except ValueError:
            return self.reply.render("invalid_time_format")
        
        # 检查目标时间点是否超过max_time
        max_time = battle.get('max_time', 0)
        if target_time > max_time:
            return self.reply.render("time_exceeds_max", time=target_time, max=max_time)
        
        timeline_data = battle.get("timeline", {})
        participants = battle.get("participants", {})
        
        result = f"【{battle.get('name', '战斗')} - {target_time}t 时间点状态】\n"
        
        # 检查在该时间点正在进行的行动（包含跨时间点的行动）
        ongoing_actions = []
        for time_str_recorded, actions in timeline_data.items():
            recorded_time = float(time_str_recorded)
            for action in actions:
                # 检查角色状态
                action_user_id = action.get('user_id', '')
                char_name = action.get('character_name', '未知')
                user_participants = participants.get(action_user_id, {})
                char_info = user_participants.get(char_name, {})
                
                if char_info.get('status') != '参与中':
                    continue
                
                start_time = recorded_time - action.get('lead_time', 0)
                
                # 检查该时间点是否有行动在执行
                if start_time <= target_time <= recorded_time:
                    elapsed_time = target_time - start_time
                    lead_time = action.get('lead_time', 1)
                    completion_ratio = elapsed_time / lead_time if lead_time > 0 else 0
                    completed_impact = action.get('impact_value', 0) * completion_ratio
                    completion_percentage = completion_ratio * 100
                    
                    ongoing_actions.append({
                        'action': action,
                        'completed_impact': completed_impact,
                        'completion_percentage': completion_percentage,
                        'start_time': start_time,
                        'end_time': recorded_time
                    })
        
        if ongoing_actions:
            for info in ongoing_actions:
                action = info['action']
                completed_impact = game_config.round_value(info['completed_impact'], "impact")
                impact_value = game_config.round_value(action.get('impact_value', 0), "impact")
                completion_percentage = game_config.round_value(info['completion_percentage'], "percentage")
                start_time = game_config.round_value(info['start_time'], "time")
                end_time = game_config.round_value(info['end_time'], "time")
                
                result += f"[{action.get('character_name', '未知')}]\n"
                result += f"  属性: {action.get('attribute_used', '')} | 影响: {completed_impact}/{impact_value}\n"
                result += f"  进度: {completion_percentage}% | 执行期: {start_time}-{end_time}t\n"
                if action.get('notes'):
                    result += f"  备注: {action['notes']}\n"
                result += "\n"
        
        if not ongoing_actions:
            result += f"时间点 {target_time}t 没有正在进行的行动"
        
        return result
    
    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


timeline_module = TimelineModule()
