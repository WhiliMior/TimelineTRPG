"""
资源修正模块 - 管理资源修饰/修正值
迁移自老项目 Game/Runtime/Buff/ResourceModifier.py
"""
import re
import time
from typing import Dict, List, Optional
from datetime import datetime

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend, StorageType


class ResourceModifierModule:
    """
    资源修正模块
    
    支持的指令格式：
    - .dr - 查看资源修饰列表
    - .dr add <来源> <范围> <数值> [类型] [持续时间] - 添加资源修饰
    - .dr del <序号>/all - 移除资源修饰
    - .dr <范围> - 显示指定范围的资源修饰
    """
    
    # 支持的范围类型
    SUPPORTED_RANGES = ["+hp", "-hp", "+mp", "-mp", "+all", "-all", "hp", "mp", "all"]
    
    # 中文别名映射
    CHINESE_ALIASES = {
        "+体力": "+hp", "-体力": "-hp", "+意志": "+mp", "-意志": "-mp",
        "+所有": "+all", "-所有": "-all", "体力": "hp", "意志": "mp", "所有": "all",
        "+全部": "+all", "-全部": "-all", "全部": "all"
    }
    
    def __init__(self):
        self.reply = ReplyManager("resource_modifier")
        self.system_reply = ReplyManager("system")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="dr",
            usage="[add|del] [参数]",
            summary="资源修正管理",
            detail=(
                "- 查看资源修饰列表\n"
                "add {来源} {范围} {数值} (类型) (持续时间) - 添加资源修饰\n"
                "del {序号}/all - 移除资源修饰\n"
                "{范围} - 显示指定范围的资源修饰"
            ),
        )
    
    async def dr(self, ctx: CommandContext) -> bool:
        """
        处理资源修正命令
        
        指令格式：
        - .dr - 查看资源修饰列表
        - .dr add <来源> <范围> <数值> [类型] [持续时间] - 添加资源修饰
        - .dr del <序号>/all - 移除资源修饰
        - .dr <范围> - 显示指定范围的资源修饰
        """
        user_id = ctx.sender_id or "default"
        
        if not ctx.args:
            # 显示资源修饰列表
            result = await self._list_modifiers(user_id)
            ctx.send(result)
            return True
        
        command = ctx.args[0].lower()
        
        # 添加资源修饰
        if command == 'add' and len(ctx.args) >= 4:
            source = ctx.args[1]
            range_input = ctx.args[2]
            value_str = ctx.args[3]
            type_input = ctx.args[4] if len(ctx.args) > 4 else "通用"
            duration = ctx.args[5] if len(ctx.args) > 5 else ""
            
            conversation_id = ctx.group_id or ctx.session_id or user_id
            result = await self._add_modifier(user_id, conversation_id, source, range_input, value_str, type_input, duration)
            ctx.send(result)
            return True
        
        # 删除资源修饰
        if command == 'del':
            if len(ctx.args) < 2:
                response = self.reply.render("need_item_index")
                ctx.send(response)
                return True

            if ctx.args[1].lower() == 'all':
                result = await self._delete_all_modifiers(user_id)
                ctx.send(result)
            else:
                # 支持多个数字输入，如 del 1 4 5
                indices = [int(x) - 1 for x in ctx.args[1:] if x.isdigit()]
                if not indices:
                    response = self.reply.render("invalid_number")
                    ctx.send(response)
                else:
                    result = await self._delete_modifier(user_id, indices)
                    ctx.send(result)
            return True
        
        # 检查是否是范围过滤
        normalized_range = self._normalize_range(command)
        if normalized_range:
            result = await self._list_modifiers(user_id, normalized_range)
            ctx.send(result)
            return True
        
        # 无效命令，显示列表
        result = await self._list_modifiers(user_id)
        ctx.send(result)
        return True
    
    async def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色"""
        from ..character.character import character_module
        return await character_module.get_active_character(user_id)
    
    async def _get_modifiers(self, user_id: str) -> List[Dict]:
        """获取角色资源修饰列表"""
        character = await self._get_active_character(user_id)
        if not character:
            return []
        return character.get('resource_modifiers', [])
    
    async def _save_modifiers(self, user_id: str, modifiers: List[Dict]) -> bool:
        """保存角色资源修饰列表"""
        from ..character.character import character_module
        character = await self._get_active_character(user_id)
        if not character:
            return False
        
        character['resource_modifiers'] = modifiers
        
        # 保存到角色数据
        char_module = character_module
        characters = await char_module._get_user_characters(user_id)
        
        for i, char in enumerate(characters):
            if char.get('name') == character.get('name'):
                characters[i] = character
                break
        
        return await char_module._save_characters(user_id, characters)
    
    def _normalize_range(self, range_input: str) -> Optional[str]:
        """标准化范围输入"""
        range_input = range_input.strip().lower()
        
        # 检查中文别名
        if range_input in self.CHINESE_ALIASES:
            return self.CHINESE_ALIASES[range_input]
        
        # 检查是否以正负号开头
        if range_input.startswith(('+', '-')):
            sign = range_input[0]
            base_range = range_input[1:]
            if base_range in ['hp', 'mp', 'all']:
                return range_input
        else:
            # 如果没有正负号，默认为减伤（-）
            if range_input in ['hp', 'mp', 'all']:
                return '-' + range_input
        
        return None
    
    def _parse_value(self, value_str: str) -> Optional[Dict]:
        """
        解析数值，支持百分比、d格式(防御值)和普通数字(固定值)
        
        返回格式（记录原始值）:
        - 百分比: {"raw": "15%", "type": "percentage"}
        - 固定值: {"raw": "15", "type": "fixed"}
        - 防御值: {"raw": "24d", "type": "defense"}
        """
        value_str = value_str.strip()
        
        # 百分比格式: 15%
        if value_str.endswith('%'):
            return {"raw": value_str, "type": "percentage"}
        
        # d格式: 2d (防御值)
        elif value_str.endswith('d') or value_str.endswith('D'):
            return {"raw": value_str, "type": "defense"}
        
        # 普通数字格式 - 固定值
        else:
            try:
                float(value_str)
                return {"raw": value_str, "type": "fixed"}
            except ValueError:
                return None
    
    def _calculate_modifier_value(self, value_data: Dict, character_data: Dict, range_val: str) -> float:
        """
        根据保存的原始值计算实际的修饰数值
        在.rc指令中调用此方法计算实际效果
        """
        raw = value_data.get('raw', '0')
        value_type = value_data.get('type', 'percentage')
        
        if value_type == 'percentage':
            # 百分比: 15% -> 0.15
            try:
                return float(raw.rstrip('%')) / 100.0
            except ValueError:
                return 0.0
        
        elif value_type == 'defense':
            # 防御值: 需要根据角色等级和范围计算
            try:
                defense = float(raw.rstrip('dD'))
                level = character_data.get('等级', 1)
                
                if range_val.startswith('-'):
                    # 减伤效果: 防御/(防御+(等级*10))
                    return defense / (defense + (level * 10))
                else:
                    # 增疗效果: 防御/(等级*10)
                    return defense / (level * 10)
            except ValueError:
                return 0.0
        
        else:  # fixed
            # 固定值
            try:
                return float(raw)
            except ValueError:
                return 0.0
    
    def _format_modifier_display(self, value_data: Dict, character_data: Dict, range_val: str) -> str:
        """
        格式化修饰数值显示（显示原始值和换算后的值）
        """
        raw = value_data.get('raw', '0')
        value_type = value_data.get('type', 'percentage')
        
        if value_type == 'percentage':
            try:
                pct = float(raw.rstrip('%'))
                return f"{pct:.0f}%"
            except ValueError:
                return raw
        
        elif value_type == 'defense':
            try:
                # 计算换算后的百分比
                calculated = self._calculate_modifier_value(value_data, character_data, range_val)
                return f"{raw} ({calculated*100:.0f}%)"
            except ValueError:
                return raw
        
        else:  # fixed
            return raw
    
    async def _add_modifier(self, user_id: str, conversation_id: str, source: str, range_input: str, 
                           value_str: str, type_input: str, duration: str) -> str:
        """添加资源修饰"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")
        
        # 标准化范围
        normalized_range = self._normalize_range(range_input)
        if not normalized_range:
            return self.reply.render("invalid_number")
        
        # 解析数值
        value = self._parse_value(value_str)
        if value is None:
            return self.reply.render("invalid_number")
        
        # 创建时间
        from datetime import datetime
        created_at = datetime.now().isoformat()
        
        # 创建修饰符（使用英文key）
        modifier = {
            "source": source,
            "range": normalized_range,
            "value": value,
            "type": type_input if type_input else "所有",
            "duration": duration if duration else "",
            "created_at": created_at
        }
        
        # 获取或初始化资源修饰列表
        modifiers = await self._get_modifiers(user_id)
        modifiers.append(modifier)
        
        # 如果有持续时间，调度资源修饰到期事件
        if duration and duration != "0t" and duration != "0":
            character_name = character.get('name', '未知角色')
            # 传递原始字符串用于显示
            self._schedule_modifier_event(conversation_id, user_id, created_at, duration, source, normalized_range, value_str, character_name)
        
        if await self._save_modifiers(user_id, modifiers):
            # 格式化数值显示（原始值和换算后）
            character_data = character.get('data', {})
            value_display = self._format_modifier_display(value, character_data, normalized_range)
            return self.reply.render("modifier_added", source=source, range=range_input, value=value_display)
        else:
            return self.reply.render("save_failed")
    
    async def _delete_modifier(self, user_id: str, indices: List[int]) -> str:
        """删除指定序号的资源修饰"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")
        
        modifiers = await self._get_modifiers(user_id)
        
        if not modifiers:
            return self.reply.render("no_modifiers")
        
        # 按降序删除，避免索引变化问题
        indices.sort(reverse=True)
        deleted = 0
        for idx in indices:
            if 0 <= idx < len(modifiers):
                modifiers.pop(idx)
                deleted += 1
        
        if await self._save_modifiers(user_id, modifiers):
            return self.reply.render("modifier_deleted", count=deleted)
        else:
            return self.reply.render("save_failed")
    
    async def _delete_all_modifiers(self, user_id: str) -> str:
        """删除所有资源修饰"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")
        
        modifiers = await self._get_modifiers(user_id)
        
        if not modifiers:
            return self.reply.render("no_modifiers")
        
        if await self._save_modifiers(user_id, []):
            return self.reply.render("all_modifiers_deleted")
        else:
            return self.reply.render("save_failed")
    
    async def _list_modifiers(self, user_id: str, range_filter: Optional[str] = None) -> str:
        """列出资源修饰"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")
        
        modifiers = await self._get_modifiers(user_id)
        
        if not modifiers:
            return self.reply.render("no_modifiers")
        
        # 如果有范围过滤，则只显示指定范围的资源修饰
        if range_filter:
            normalized_filter = self._normalize_range(range_filter)
            if normalized_filter:
                modifiers = [mod for mod in modifiers if mod.get('range') == normalized_filter]
            else:
                return self.reply.render("no_modifiers")
        
        if not modifiers:
            return self.reply.render("no_modifiers")
        
        # 获取角色数据用于计算防御值
        character_data = character.get('data', {})
        
        # 构建列表
        lines = [self.reply.render("modifier_list_header")]
        
        for i, modifier in enumerate(modifiers):
            source = modifier.get('source', '')
            range_val = modifier.get('range', '')
            value = modifier.get('value', {})
            type_val = modifier.get('type', '所有')
            duration = modifier.get('duration', '')
            
            # 使用格式化方法显示数值
            value_display = self._format_modifier_display(value, character_data, range_val)
            
            # 省略默认值的显示
            type_display = f" [{type_val}]" if type_val and type_val != '通用' else ""
            duration_display = f" 持续{duration}" if duration else ""
            
            lines.append(f"[{i + 1}] {source} {range_val} {value_display}{type_display}{duration_display}")
        
        return "\n".join(lines)


    def _schedule_modifier_event(self, conversation_id: str, user_id: str, modifier_id: str,
                                  duration: str, source: str, range_val: str, value: str,
                                  character_name: str = '未知角色'):
        """
        调度资源修饰到期事件
        """
        # 使用 infrastructure scheduler 避免循环引用
        from ...infrastructure.scheduler import schedule_event
        
        # 确定模式
        mode = 'time_based' if (isinstance(duration, str) and duration.endswith('t')) else 'count_based'
        duration_value = float(duration[:-1]) if (isinstance(duration, str) and duration.endswith('t')) else float(duration)
        
        # 构建描述
        action_desc = f"{character_name} {source} {range_val} {value}"
        callback_msg = f"{character_name} {source} {range_val} {value} 到期"
        
        # 调用 scheduler 调度事件
        schedule_event(
            conversation_id=conversation_id,
            user_id=user_id,
            character_name=character_name,
            action_description=action_desc,
            duration_or_count=duration_value,
            callback_path=f"trpg.service.resource.modifier.remove_expired_modifier",
            callback_args={
                "user_id": user_id,
                "modifier_id": modifier_id
            },
            callback_message=callback_msg,
            mode=mode,
            event_type='modifier'
        )


async def remove_expired_modifier(user_id: str, modifier_id: str) -> bool:
    """
    模块级函数，用于移除过期的资源修饰
    由战斗系统在定时事件触发时调用
    
    infrastructure 层会统一处理事件循环
    """
    from ..character.character import character_module
    
    character = await character_module.get_active_character(user_id)
    if not character:
        return False
    
    modifiers = character.get('resource_modifiers', [])
    
    if not modifiers:
        return False
    
    # 查找并移除指定ID的修饰
    original_count = len(modifiers)
    modifiers = [m for m in modifiers if m.get('created_at') != modifier_id]
    
    if len(modifiers) < original_count:
        character['resource_modifiers'] = modifiers
        
        # 保存角色数据
        characters = await character_module._get_user_characters(user_id)
        for i, char in enumerate(characters):
            if char.get('name') == character.get('name'):
                characters[i] = character
                break
        
        await character_module._save_characters(user_id, characters)
        return True
    
    return False


resource_modifier_module = ResourceModifierModule()
