"""
Buff模块 - 管理角色增益/减益效果
迁移自老项目 Game/Runtime/Buff/BuffManager.py

功能：
- 添加/移除 Buff
- 与战斗系统集成（定时事件）
- 与角色系统集成（属性修正）

数据存储：
- Buff数据存储在角色的 buffs 字段中
- 与老项目 TimelineBot 的数据存储方式完全一致
"""
import re
import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend, StorageType
from ...infrastructure.attribute_resolver import AttributeResolver

# Buff类型常量
VALID_BUFF_TYPES = {"直接加算", "直接乘算", "最终加算", "最终乘算"}


class BuffModule:
    """
    Buff模块
    
    支持的指令格式：
    - .buff - 显示buff列表
    - .buff add <名称> <属性> <类型> <数值> [持续时间] - 添加buff
    - .buff del <序号> - 删除指定buff
    - .buff del all - 删除所有buff
    - .buff show [属性] - 显示buff详情
    """
    
    def __init__(self):
        self.reply = ReplyManager("buff")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="buff",
            usage="[add|del|show] [参数]",
            summary="Buff增益管理",
            detail=(
                "- 显示buff列表\n"
                "add {名称} {属性} {类型} {数值} (持续时间) - 添加buff\n"
                "show (覆盖范围) - 查看所有Buff或对范围生效的Buff\n"
                "del {序号}/all - 移除Buff"
            ),
        )
    
    async def buff(self, ctx: CommandContext) -> bool:
        """
        处理buff命令
        """
        user_id = ctx.sender_id or "default"
        conversation_id = ctx.group_id or ctx.session_id or user_id
        
        if not ctx.args:
            # 没有参数，显示所有buff
            result = await self._list_buffs(user_id)
            ctx.send(result)
            return True
        
        command = ctx.args[0].lower()
        
        if command == 'add' and len(ctx.args) >= 5:
            # .buff add {名称} {属性} {类型} {数值} [持续时间]
            buff_name = ctx.args[1]
            attribute = ctx.args[2]
            buff_type = ctx.args[3]
            value_str = ctx.args[4]
            
            duration = None
            if len(ctx.args) >= 6:
                duration_input = ctx.args[5]
                if duration_input != '0' and duration_input != '0t':
                    try:
                        if duration_input.endswith('t'):
                            duration = duration_input
                        else:
                            duration = int(duration_input)
                    except ValueError:
                        response = self.reply.render("invalid_duration")
                        ctx.send(response)
                        return True
                else:
                    duration = None
            
            try:
                value = float(value_str)
            except ValueError:
                response = self.reply.render("invalid_value")
                ctx.send(response)
                return True
            
            # 验证buff类型
            if buff_type not in VALID_BUFF_TYPES:
                response = self.reply.render("invalid_buff_type")
                ctx.send(response)
                return True
            
            # 验证属性是否合法（使用 AttributeResolver）
            if not AttributeResolver.is_valid(attribute):
                valid_inputs = ", ".join(AttributeResolver.get_all_valid_inputs()[:10])
                response = f"无效的属性名：{attribute}\n有效的属性包括：{valid_inputs}..."
                ctx.send(response)
                return True
            
            # 解析为标准属性名，确保反馈时显示原名
            resolved_attribute = AttributeResolver.resolve(attribute)
            
            result = await self._add_buff(user_id, conversation_id, buff_name, resolved_attribute, buff_type, value, duration)
            ctx.send(result)
        
        elif command == 'del' and len(ctx.args) >= 2:
            if ctx.args[1].lower() == 'all':
                result = await self._remove_all_buffs(user_id)
                ctx.send(result)
            else:
                try:
                    index = int(ctx.args[1])
                    result = await self._remove_buff_by_index(user_id, index)
                    ctx.send(result)
                except ValueError:
                    response = self.reply.render("invalid_number")
                    ctx.send(response)
        
        elif command == 'show':
            if len(ctx.args) >= 2:
                attribute = ctx.args[1]
                result = await self._list_buffs(user_id, attribute)
            else:
                result = await self._list_buffs(user_id)
            ctx.send(result)
        
        else:
            result = await self._list_buffs(user_id)
            ctx.send(result)
        
        return True
    
    def _resolve_attribute_name(self, attribute: str) -> str:
        """解析属性名称，使用统一的 AttributeResolver"""
        resolved = AttributeResolver.resolve(attribute)
        return resolved if resolved else attribute
    
    def _get_character_module(self):
        """获取角色模块"""
        from ..character.character import character_module
        return character_module
    
    async def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色"""
        char_module = self._get_character_module()
        return await char_module.get_active_character(user_id)
    
    async def _get_buffs(self, user_id: str) -> List[Dict]:
        """获取buff列表 - 从角色buffs字段中获取"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return []
        return active_char.get('buffs', [])
    
    async def _save_buffs(self, user_id: str, buffs: List[Dict]):
        """保存buff列表 - 通过StorageBackend保存到角色buffs字段中"""
        from ...infrastructure.storage import StorageBackend
        
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return
        
        # 更新角色的buffs字段
        active_char['buffs'] = buffs
        
        # 通过StorageBackend保存整个角色数据
        StorageBackend.update_character(user_id, active_char.get('name'), active_char)
    
    async def _add_buff(self, user_id: str, conversation_id: str, 
                        buff_name: str, attribute: str, buff_type: str, value: float, duration) -> str:
        """添加buff"""
        # 检查角色
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")
        
        # 解析属性名称
        resolved_attribute = self._resolve_attribute_name(attribute)
        
        # 获取角色数据
        character_name = active_char.get('name', '未知角色')
        char_data = active_char.get('data', {})
        
        # 检查属性是否存在
        if resolved_attribute not in char_data:
            return self.reply.render("attribute_not_found", attribute=resolved_attribute)
        
        buffs = await self._get_buffs(user_id)
        
        buff = {
            "name": buff_name,
            "attribute": resolved_attribute,
            "type": buff_type,
            "value": value,
            "duration": duration,
            "created_at": datetime.now().isoformat()
        }
        
        buffs.append(buff)
        await self._save_buffs(user_id, buffs)
        
        # 如果有持续时间，调度战斗事件
        if duration is not None:
            # 通知战斗系统调度事件
            self._schedule_buff_event(conversation_id, user_id, character_name, 
                                    resolved_attribute, buff_type, value, duration)
        
        duration_str = "永久" if duration is None else str(duration)
        return self.reply.render("buff_added", name=buff_name, attribute=resolved_attribute, type=buff_type, value=value, duration=duration_str)
    
    def _schedule_buff_event(self, conversation_id: str, user_id: str, character_name: str,
                           attribute: str, buff_type: str, buff_value: float, duration):
        """
        调度buff事件
        """
        # 使用 infrastructure scheduler 避免循环引用
        from ...infrastructure.scheduler import schedule_event
        
        # 确定模式
        mode = 'time_based' if (isinstance(duration, str) and duration.endswith('t')) else 'count_based'
        duration_value = float(duration[:-1]) if (isinstance(duration, str) and duration.endswith('t')) else float(duration)
        
        # 构建描述
        action_desc = f"{character_name} Buff{buff_type} {attribute}{buff_value:+g}"
        
        # 调用 scheduler 调度事件
        schedule_event(
            conversation_id=conversation_id,
            user_id=user_id,
            character_name=character_name,
            action_description=action_desc,
            duration_or_count=duration_value,
            callback_path=f"trpg.service.buff.buff.remove_expired_buff",
            callback_args={
                "user_id": user_id,
                "attribute": attribute,
                "buff_type": buff_type,
                "buff_value": buff_value
            },
            callback_message=f"{character_name} Buff{buff_type} {attribute}{buff_value:+g} 已到期",
            mode=mode,
            event_type='buff'
        )
    
    async def _remove_buff(self, user_id: str, attribute: Optional[str]) -> str:
        """删除buff（按属性名）"""
        buffs = await self._get_buffs(user_id)
        
        if not buffs:
            return self.reply.render("no_buffs")
        
        if attribute is None:
            # 删除所有
            await self._save_buffs(user_id, [])
            return self.reply.render("all_buffs_removed")
        
        # 删除指定属性的buff
        original_count = len(buffs)
        buffs = [b for b in buffs if b.get('attribute') != attribute]
        
        if len(buffs) == original_count:
            return self.reply.render("buff_not_found", attribute=attribute)
        
        await self._save_buffs(user_id, buffs)
        return self.reply.render("buff_removed", attribute=attribute)
    
    async def _remove_buff_by_index(self, user_id: str, index: int) -> str:
        """按索引删除buff"""
        buffs = await self._get_buffs(user_id)
        
        if not buffs:
            return self.reply.render("no_buffs")
        
        if index < 1 or index > len(buffs):
            return self.reply.render("invalid_index")
        
        removed = buffs.pop(index - 1)
        await self._save_buffs(user_id, buffs)
        
        return self.reply.render("buff_removed_by_index", index=index, attribute=removed.get('attribute', ''))
    
    async def _remove_all_buffs(self, user_id: str) -> str:
        """删除所有buff"""
        buffs = await self._get_buffs(user_id)
        
        if not buffs:
            return self.reply.render("no_buffs")
        
        await self._save_buffs(user_id, [])
        return self.reply.render("all_buffs_removed")
    
    async def _list_buffs(self, user_id: str, attribute: Optional[str] = None) -> str:
        """显示buff列表"""
        buffs = await self._get_buffs(user_id)
        
        if not buffs:
            return self.reply.render("no_buffs")
        
        if attribute:
            # 筛选指定属性的buff
            filtered = [b for b in buffs if b.get('attribute') == attribute]
            if not filtered:
                return self.reply.render("no_buffs_for_attribute", attribute=attribute)
            buffs = filtered
        
        lines = [self.reply.render("buff_list_header")]
        
        for i, buff in enumerate(buffs):
            name = buff.get('name', '')
            attr = buff.get('attribute', '')
            btype = buff.get('type', '')
            val = buff.get('value', 0)
            dur = buff.get('duration', '永久')
            lines.append(f"[{i + 1}] {name} {attr} {btype} {val} 持续: {dur}")
        
        return "\n".join(lines)
    
    def get_buff_modifier(self, user_id: str, attribute: str) -> float:
        """
        获取角色指定属性的Buff修正值
        用于与角色属性系统集成
        """
        buffs = asyncio.run(self._get_buffs(user_id))
        
        total_modifier = 0.0
        for buff in buffs:
            if buff.get('attribute') == attribute:
                total_modifier += buff.get('value', 0)
        
        return total_modifier


# 用于存储正在等待保存的角色数据（避免并发问题）
_pending_character_saves: Dict[str, asyncio.Lock] = {}


def remove_expired_buff(user_id: str, attribute: str, buff_type: str, buff_value: float) -> bool:
    """
    模块级函数，用于移除过期的buff
    由战斗系统在定时事件触发时调用
    
    修改为从角色的buffs字段中读取和保存数据，与老项目一致
    """
    from ..character.character import character_module
    
    # 获取角色模块
    char_module = character_module
    
    # 获取当前激活的角色
    active_char = char_module.get_active_character(user_id)
    if not active_char:
        return False
    
    buffs = active_char.get('buffs', [])
    
    if not buffs:
        return False
    
    # 查找并移除匹配的buff
    original_count = len(buffs)
    buffs = [b for b in buffs if not (
        b.get('attribute') == attribute and 
        b.get('type') == buff_type and 
        b.get('value') == buff_value
    )]
    
    if len(buffs) < original_count:
        # 更新并保存角色数据
        active_char['buffs'] = buffs
        
        # 保存角色数据
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            characters = loop.run_until_complete(char_module._get_user_characters(user_id))
            for i, char in enumerate(characters):
                if char.get('name') == active_char.get('name'):
                    characters[i] = active_char
                    break
            loop.run_until_complete(char_module._save_characters(user_id, characters))
        finally:
            loop.close()
        
        return True
    
    return False


# 创建模块实例
buff_module = BuffModule()
