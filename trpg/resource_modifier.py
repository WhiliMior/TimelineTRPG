"""
资源修正模块 - 管理资源修饰/修正值
迁移自老项目 Game/Runtime/Buff/ResourceModifierCommandHandler.py
"""
import re
from typing import Dict, List, Optional
from datetime import datetime

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry
from ..adapter.storage import StorageBackend, StorageType


class ResourceModifierModule:
    """
    资源修正模块
    
    支持的指令格式：
    - .dr - 显示资源修正列表
    - .dr add <来源> <范围> <数值> [类型] [持续时间] - 添加资源修正
    - .dr del <序号> - 删除资源修正
    - .dr del all - 删除所有资源修正
    - .dr <范围> - 显示指定范围的资源修正
    """
    
    def __init__(self):
        self.reply = ReplyManager("resource_modifier")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="dr",
            usage="[add|del] [参数]",
            summary="资源修正管理",
            detail=(
                "- 查看资源修饰列表\n"
                "{资源类型} {修饰类型} {数值} {范围} (持续时间) - 添加资源修饰\n"
                "del {序号}/all - 移除资源修饰\n"
                "\n"
                "示例:\n"
                "  dr → 查看资源修正列表\n"
                "  dr add 装备 全局 +5 永久 → 添加装备提供的全局+5修正\n"
                "  dr add 技能 hp +10 3t → 添加技能提供的hp+10修正，持续3时间\n"
                "  dr del 1 → 删除第1个资源修正\n"
                "  dr del all → 删除所有资源修正"
            ),
        )
    
    async def dr(self, ctx: CommandContext) -> bool:
        """
        处理资源修正命令
        """
        user_id = ctx.sender_id or "default"
        
        if not ctx.args:
            result = self._list_modifiers(user_id)
            ctx.send(result)
            return True
        
        command = ctx.args[0].lower()
        
        if command == 'add' and len(ctx.args) >= 4:
            source = ctx.args[1]
            range_input = ctx.args[2]
            value_str = ctx.args[3]
            
            type_input = "通用"
            duration = ""
            
            if len(ctx.args) >= 5:
                if ctx.args[4].endswith('t') or ctx.args[4].isdigit():
                    duration = ctx.args[4]
                else:
                    type_input = ctx.args[4]
                    if len(ctx.args) >= 6:
                        duration = ctx.args[5]
            
            result = self._add_modifier(user_id, source, range_input, value_str, type_input, duration)
            ctx.send(result)
        
        elif command == 'del' and len(ctx.args) >= 2:
            if ctx.args[1].lower() == 'all':
                result = self._delete_all_modifiers(user_id)
                ctx.send(result)
            else:
                try:
                    indices = [int(x) - 1 for x in ctx.args[1:] if x.isdigit()]
                    if not indices:
                        response = self.reply.render("invalid_number")
                        ctx.send(response)
                        return True
                    result = self._delete_modifier(user_id, indices)
                    ctx.send(result)
                except ValueError:
                    response = self.reply.render("invalid_number")
                    ctx.send(response)
        
        elif command in ["+hp", "-hp", "+mp", "-mp", "+all", "-all", "hp", "mp", "all"]:
            result = self._list_modifiers(user_id, command)
            ctx.send(result)
        
        else:
            result = self._list_modifiers(user_id)
            ctx.send(result)
        
        return True
    
    def _get_modifiers(self, user_id: str) -> List[Dict]:
        return StorageBackend.load(StorageType.RESOURCE, user_id, filename="modifiers.json", default=[])
    
    def _save_modifiers(self, user_id: str, modifiers: List[Dict]):
        StorageBackend.save(StorageType.RESOURCE, user_id, modifiers, filename="modifiers.json")
    
    def _add_modifier(self, user_id: str, source: str, range_input: str, value_str: str, type_input: str, duration: str) -> str:
        modifiers = self._get_modifiers(user_id)
        
        modifier = {
            "source": source,
            "range": range_input,
            "value": value_str,
            "type": type_input,
            "duration": duration,
            "created_at": datetime.now().isoformat()
        }
        
        modifiers.append(modifier)
        self._save_modifiers(user_id, modifiers)
        
        return self.reply.render("modifier_added", source=source, range=range_input, value=value_str)
    
    def _delete_modifier(self, user_id: str, indices: List[int]) -> str:
        modifiers = self._get_modifiers(user_id)
        
        if not modifiers:
            return self.reply.render("no_modifiers")
        
        # 按降序删除
        indices.sort(reverse=True)
        deleted = 0
        for idx in indices:
            if 0 <= idx < len(modifiers):
                modifiers.pop(idx)
                deleted += 1
        
        self._save_modifiers(user_id, modifiers)
        return self.reply.render("modifier_deleted", count=deleted)
    
    def _delete_all_modifiers(self, user_id: str) -> str:
        modifiers = self._get_modifiers(user_id)
        
        if not modifiers:
            return self.reply.render("no_modifiers")
        
        self._save_modifiers(user_id, [])
        return self.reply.render("all_modifiers_deleted")
    
    def _list_modifiers(self, user_id: str, range_filter: Optional[str] = None) -> str:
        modifiers = self._get_modifiers(user_id)
        
        if not modifiers:
            return self.reply.render("no_modifiers")
        
        if range_filter:
            filtered = [m for m in modifiers if m.get('range') == range_filter]
            if filtered:
                modifiers = filtered
            else:
                return self.reply.render("no_modifiers")
        
        lines = [self.reply.render("modifier_list_header")]
        
        for i, mod in enumerate(modifiers):
            src = mod.get('source', '')
            rng = mod.get('range', '')
            val = mod.get('value', '')
            typ = mod.get('type', '')
            dur = mod.get('duration', '永久')
            lines.append(f"[{i + 1}] {src} {rng} {val} {typ} 持续: {dur}")
        
        return "\n".join(lines)


resource_modifier_module = ResourceModifierModule()
