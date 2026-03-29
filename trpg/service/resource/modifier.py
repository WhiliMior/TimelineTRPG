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
        "+所有": "+all", "-所有": "-all", "体力": "hp", "意志": "mp", "所有": "all"
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
        if command == 'add' and len(ctx.args) >= 5:
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
                try:
                    indices = [int(ctx.args[1]) - 1]
                    result = await self._delete_modifier(user_id, indices)
                    ctx.send(result)
                except ValueError:
                    response = self.reply.render("invalid_number")
                    ctx.send(response)
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
    
    def _parse_value(self, value_str: str, character_data: Dict) -> Optional[float]:
        """解析数值，支持百分比、d格式和普通数字"""
        value_str = value_str.strip()
        
        # 百分比格式: 15%
        if value_str.endswith('%'):
            try:
                value = float(value_str[:-1])
                return value / 100.0
            except ValueError:
                return None
        
        # d格式: 2d
        elif value_str.endswith('d') or value_str.endswith('D'):
            try:
                value = float(value_str[:-1])
                # 获取角色等级
                level = character_data.get('等级', 1)
                # 使用等级计算
                return value * level
            except ValueError:
                return None
        
        # 普通数字格式
        else:
            try:
                return float(value_str)
            except ValueError:
                return None
    
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
        value = self._parse_value(value_str, character.get('data', {}))
        if value is None:
            return self.reply.render("invalid_number")
        
        # 生成唯一ID
        modifier_id = f"rm_{int(time.time())}_{hash(source + normalized_range + str(value) + type_input) % 10000}"
        
        # 创建修饰符
        modifier = {
            "编号": modifier_id,
            "来源": source,
            "范围": normalized_range,
            "数值": value,
            "类型": type_input,
            "持续时间": duration if duration else ""
        }
        
        # 获取或初始化资源修饰列表
        modifiers = await self._get_modifiers(user_id)
        modifiers.append(modifier)
        
        # 如果有持续时间，调度资源修饰到期事件
        if duration and duration != "0t" and duration != "0":
            self._schedule_modifier_event(conversation_id, user_id, modifier_id, duration, source, normalized_range, value)
        
        if await self._save_modifiers(user_id, modifiers):
            return self.reply.render("modifier_added", source=source, range=range_input, value=str(value))
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
                modifiers = [mod for mod in modifiers if mod.get('范围') == normalized_filter]
            else:
                return self.reply.render("no_modifiers")
        
        if not modifiers:
            return self.reply.render("no_modifiers")
        
        # 构建列表
        lines = [self.reply.render("modifier_list_header")]
        
        for i, modifier in enumerate(modifiers):
            source = modifier.get('来源', '')
            range_val = modifier.get('范围', '')
            value = modifier.get('数值', 0)
            type_val = modifier.get('类型', '通用')
            duration = modifier.get('持续时间', '永久')
            
            # 格式化数值显示
            value_display = f"{value:.2f}" if isinstance(value, float) else str(value)
            
            lines.append(f"[{i + 1}] {source} {range_val} {value_display} {type_val} 持续: {duration}")
        
        return "\n".join(lines)


    def _schedule_modifier_event(self, conversation_id: str, user_id: str, modifier_id: str,
                                  duration: str, source: str, range_val: str, value: float):
        """
        调度资源修饰到期事件
        """
        # 使用 infrastructure scheduler 避免循环引用
        from ...infrastructure.scheduler import schedule_event
        
        # 获取角色名
        character = self._get_active_character(user_id)
        if not character:
            return
        character_name = character.get('name', '未知角色')
        
        # 确定模式
        mode = 'time_based' if (isinstance(duration, str) and duration.endswith('t')) else 'count_based'
        duration_value = float(duration[:-1]) if (isinstance(duration, str) and duration.endswith('t')) else float(duration)
        
        # 构建描述
        action_desc = f"{character_name} {source} {range_val} {value}"
        callback_msg = f"{character_name} {source} {range_val} {value} 修饰已到期"
        
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
    
    def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色（同步版本）"""
        from ..character.character import character_module
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(character_module.get_active_character(user_id))
        finally:
            loop.close()
        return result


def remove_expired_modifier(user_id: str, modifier_id: str) -> bool:
    """
    模块级函数，用于移除过期的资源修饰
    由战斗系统在定时事件触发时调用
    """
    import asyncio
    
    async def _do_remove():
        from ..character.character import character_module
        
        character = await character_module.get_active_character(user_id)
        if not character:
            return False
        
        modifiers = character.get('resource_modifiers', [])
        
        if not modifiers:
            return False
        
        # 查找并移除指定ID的修饰
        original_count = len(modifiers)
        modifiers = [m for m in modifiers if m.get('编号') != modifier_id]
        
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
    
    # 创建新的事件循环来执行异步操作
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_do_remove())
        loop.close()
        return result
    except Exception as e:
        print(f"Error removing expired modifier: {e}")
        return False


resource_modifier_module = ResourceModifierModule()
