"""
时间线模块 - 管理时间线/战斗时间轴
迁移自老项目 Game/Runtime/Battle/TimelineSystem.py

功能：
- 时间线列表管理
- 时间线选择/删除
- 玩家ID注册
- 时间线显示
- 时间点查询
"""
from typing import Dict, List, Optional
import re

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry


# 时间线数据存储
_timeline_storage: Dict[str, Dict] = {}


class TimelineModule:
    """
    时间线模块
    
    支持的指令格式：
    - .tl - 显示时间线列表
    - .tl new <名称> - 创建新时间线
    - .tl <序号> - 选择时间线
    - .tl del <序号>/all - 删除时间线
    - .tl register <玩家ID> - 设置玩家ID
    - .tl show [角色名] - 显示时间线
    - .tl get <时间点> - 查询时间节点
    """
    
    def __init__(self):
        self.reply = ReplyManager("timeline")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="tl",
            usage="[序号|new|del|register|show|get] [参数]",
            summary="时间线管理",
            detail=(
                "- 显示时间线列表\n"
                "new {名称} - 创建新时间线\n"
                "{序号} - 选择时间线\n"
                "del {序号}/all - 删除时间线\n"
                "register {数字} - 注册玩家ID\n"
                "show - 显示时间线\n"
                "get {时间点} - 查询指定时间点\n"
                "\n"
                "示例:\n"
                "  tl new 战斗1 → 创建名为\"战斗1\"的时间线\n"
                "  tl 1 → 选择第1个时间线\n"
                "  tl show → 显示当前时间线"
            ),
        )
    
    async def tl(self, ctx: CommandContext) -> bool:
        """
        处理时间线命令
        """
        user_id = ctx.sender_id or "default"
        conversation_id = ctx.group_id or ctx.session_id or user_id
        storage_key = f"{conversation_id}"
        
        if not ctx.args:
            result = self._list_timelines(storage_key, user_id)
            ctx.send(result)
            return True
        
        main_command = ctx.args[0].lower()
        remaining_args = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
        
        if main_command == 'new':
            if not remaining_args:
                response = self.reply.render("need_battle_name")
                ctx.send(response)
                return True
            result = self._create_timeline(storage_key, user_id, remaining_args)
            ctx.send(result)
        
        elif main_command.isdigit():
            try:
                index = int(main_command)
                result = self._select_timeline(storage_key, user_id, index)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("index_must_be_number")
                ctx.send(response)
        
        elif main_command == 'del':
            if not remaining_args:
                response = self.reply.render("need_delete_argument")
                ctx.send(response)
                return True
            result = self._delete_timeline(storage_key, user_id, remaining_args)
            ctx.send(result)
        
        elif main_command == 'register':
            if not remaining_args:
                response = self.reply.render("need_player_id")
                ctx.send(response)
                return True
            result = self._register_player_id(storage_key, user_id, remaining_args)
            ctx.send(result)
        
        elif main_command == 'show':
            character_name = remaining_args if remaining_args else None
            result = self._show_timeline(storage_key, user_id, character_name)
            ctx.send(result)
        
        elif main_command == 'get':
            if not remaining_args:
                response = self.reply.render("need_time_point")
                ctx.send(response)
                return True
            result = self._get_time_point(storage_key, user_id, remaining_args)
            ctx.send(result)
        
        else:
            response = self.reply.render("unknown_command")
            ctx.send(response)
        
        return True
    
    def _get_storage(self, storage_key: str) -> Dict:
        if storage_key not in _timeline_storage:
            _timeline_storage[storage_key] = {
                "timelines": [],  # [{name, created_at, max_time, current_time, timeline: {}}]
                "active_index": None,
                "player_ids": {}  # {user_id: player_id}
            }
        return _timeline_storage[storage_key]
    
    def _list_timelines(self, storage_key: str, user_id: str) -> str:
        data = self._get_storage(storage_key)
        timelines = data.get("timelines", [])
        
        if not timelines:
            return self.reply.render("no_timelines")
        
        lines = [self.reply.render("timeline_list_header")]
        for i, tl in enumerate(timelines):
            active = "●" if i == data.get("active_index") else "  "
            lines.append(f"[{i + 1}] [{active}] {tl.get('name', '未命名')}")
        
        return "\n".join(lines)
    
    def _create_timeline(self, storage_key: str, user_id: str, name: str) -> str:
        data = self._get_storage(storage_key)
        timelines = data.get("timelines", [])
        
        # 检查名称是否已存在
        for tl in timelines:
            if tl.get('name') == name:
                return self.reply.render("battle_name_exists", name=name)
        
        timelines.append({
            "name": name,
            "created_at": self._get_current_time(),
            "max_time": 0,
            "current_time": 0,
            "timeline": {}
        })
        
        data["timelines"] = timelines
        # 自动选择新创建的时间线
        data["active_index"] = len(timelines) - 1
        return self.reply.render("timeline_created", name=name)
    
    def _select_timeline(self, storage_key: str, user_id: str, index: int) -> str:
        data = self._get_storage(storage_key)
        timelines = data.get("timelines", [])
        
        if not timelines or index < 1 or index > len(timelines):
            return self.reply.render("invalid_index")
        
        data["active_index"] = index - 1
        return self.reply.render("timeline_selected", name=timelines[index - 1].get('name', '未命名'))
    
    def _delete_timeline(self, storage_key: str, user_id: str, arg: str) -> str:
        data = self._get_storage(storage_key)
        timelines = data.get("timelines", [])
        
        if not timelines:
            return self.reply.render("no_timelines")
        
        if arg.lower() == 'all':
            data["timelines"] = []
            data["active_index"] = None
            return self.reply.render("all_timelines_deleted")
        
        try:
            index = int(arg) - 1
            if index < 0 or index >= len(timelines):
                return self.reply.render("invalid_index")
            
            deleted = timelines.pop(index)
            
            # 调整 active_index
            active = data.get("active_index")
            if active is not None:
                if index < active:
                    data["active_index"] = active - 1
                elif index == active:
                    data["active_index"] = None
            
            return self.reply.render("timeline_deleted", name=deleted.get('name', '未命名'))
        except ValueError:
            return self.reply.render("invalid_index")
    
    def _register_player_id(self, storage_key: str, user_id: str, player_id: str) -> str:
        data = self._get_storage(storage_key)
        player_ids = data.get("player_ids", {})
        
        player_ids[user_id] = player_id
        data["player_ids"] = player_ids
        
        return self.reply.render("player_registered", player_id=player_id)
    
    def _show_timeline(self, storage_key: str, user_id: str, character_name: Optional[str]) -> str:
        data = self._get_storage(storage_key)
        active_index = data.get("active_index")
        
        if active_index is None or not data.get("timelines"):
            return self.reply.render("no_active_timeline")
        
        timeline = data["timelines"][active_index]
        timeline_data = timeline.get("timeline", {})
        
        if not timeline_data:
            return self.reply.render("empty_timeline")
        
        lines = [
            self.reply.render("timeline_header", name=timeline.get('name', '未命名')),
            self.reply.render("timeline_current_max_time", 
                current=timeline.get('current_time', 0), 
                max=timeline.get('max_time', 0))
        ]
        
        # 按时间点排序
        sorted_times = sorted([float(t) for t in timeline_data.keys()])
        current_time = timeline.get('current_time', 0)
        
        for time_point in sorted_times:
            if time_point < current_time:
                continue
            
            time_str = f"{time_point:.1f}" if time_point.is_integer() else f"{time_point}"
            actions = timeline_data.get(time_str, [])
            
            if actions:
                dashes = "—" * 5
                lines.append(f"\n{dashes} {time_str}t {dashes}")
                
                for action in actions:
                    lines.append(f"  [{action.get('character_name', '未知')}]")
                    lines.append(f"    起始: {action.get('start_time', 0):.1f}t | 前摇: {action.get('lead_time', 0):.1f}t")
                    lines.append(f"    属性: {action.get('attribute_used', '')} | 影响: {action.get('impact_value', 0):.1f}")
                    if action.get('notes'):
                        lines.append(f"    {action.get('notes')}")
        
        return "\n".join(lines)
    
    def _get_time_point(self, storage_key: str, user_id: str, time_point: str) -> str:
        data = self._get_storage(storage_key)
        active_index = data.get("active_index")
        
        if active_index is None or not data.get("timelines"):
            return self.reply.render("no_active_timeline")
        
        timeline = data["timelines"][active_index]
        
        # 处理数字和数字+t格式
        processed_time_str = time_point.lower().replace('t', '')
        
        try:
            target_time = float(processed_time_str)
        except ValueError:
            return self.reply.render("invalid_time_format")
        
        # 检查目标时间点是否超过max_time
        max_time = timeline.get('max_time', 0)
        if target_time > max_time:
            return self.reply.render("time_exceeds_max", time=target_time, max=max_time)
        
        timeline_data = timeline.get("timeline", {})
        
        result = f"【时间点 {target_time} 查询结果】\n"
        
        # 检查是否有正好在该时间点记录的行动
        time_str = str(target_time)
        exact_actions = timeline_data.get(time_str, [])
        
        if exact_actions:
            result += f"时间点 {target_time} 的直接记录行动:\n"
            for action in exact_actions:
                result += f"  [{action.get('character_name', '未知')}] "
                result += f"属性: {action.get('attribute_used', '')} 影响: {action.get('impact_value', 0):.1f}\n"
        
        # 检查在该时间点正在进行的行动
        ongoing_actions = []
        for time_str_recorded, actions in timeline_data.items():
            recorded_time = float(time_str_recorded)
            for action in actions:
                start_time = recorded_time - action.get('lead_time', 0)
                
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
            if exact_actions:
                result += "\n"
            result += f"{target_time}t 正在进行的行动:\n"
            for info in ongoing_actions:
                action = info['action']
                result += f"  [{action.get('character_name', '未知')}] "
                result += f"进度: {info['completed_impact']:.2f}/{action.get('impact_value', 0):.1f} ({info['completion_percentage']:.2f}%) "
                result += f"| 执行期: {info['start_time']:.2f}-{info['end_time']:.2f}\n"
        
        if not exact_actions and not ongoing_actions:
            result += f"时间点 {target_time} 没有相关行动"
        
        return result
    
    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


timeline_module = TimelineModule()
