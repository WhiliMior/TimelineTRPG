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

# 乘算类型（需要转换为小数存储）
MULTIPLY_TYPES = {"直接乘算", "最终乘算"}


def parse_buff_value(value_str: str, buff_type: str) -> float:
    """
    解析buff数值字符串
    - 处理百分号：将20%转换为0.2
    - 处理正负号：允许+20或-20格式
    - 乘算类型：自动将百分比转换为小数
    - 加算类型：保持原值
    
    Args:
        value_str: 数值字符串，如 "20%", "+20%", "-20%", "20"
        buff_type: buff类型，用于决定是否转换百分比
    
    Returns:
        解析后的浮点数值
    """
    value_str = value_str.strip()
    
    # 检测是否包含百分号
    has_percent = '%' in value_str
    
    # 移除百分号和空格
    value_str = value_str.replace('%', '').strip()
    
    # 解析数值（支持正负号）
    try:
        value = float(value_str)
    except ValueError:
        raise ValueError(f"无效的数值: {value_str}")
    
    # 如果包含百分号且是乘算类型，转换为小数
    if has_percent and buff_type in MULTIPLY_TYPES:
        value = value / 100
    
    return value


def format_buff_value(value: float, buff_type: str) -> str:
    """
    格式化buff数值用于显示
    - 乘算类型：显示为百分比（如 +20%, -10%）
    - 加算类型：显示为带正负号的数值（如 +30, -15）
    
    Args:
        value: buff数值
        buff_type: buff类型
    
    Returns:
        格式化后的字符串
    """
    if buff_type in MULTIPLY_TYPES:
        # 乘算类型显示为百分比
        percent_value = value * 100
        return f"{percent_value:+.0f}%"
    else:
        # 加算类型显示为数值
        return f"{value:+.0f}"


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
                value = parse_buff_value(value_str, buff_type)
            except ValueError as e:
                response = str(e)
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
                # 支持多个数字输入，如 del 1 4 5
                indices = [int(x) - 1 for x in ctx.args[1:] if x.isdigit()]
                if not indices:
                    response = self.reply.render("invalid_number")
                    ctx.send(response)
                elif len(indices) == 1:
                    result = await self._remove_buff_by_index(user_id, indices[0])
                    ctx.send(result)
                else:
                    result = await self._remove_multiple_buffs(user_id, indices)
                    ctx.send(result)
        
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
        # 特殊范围（如物理、思维、所有）不需要检查角色数据
        from ...infrastructure.attribute_resolver import AttributeResolver
        if not AttributeResolver.is_scope(resolved_attribute):
            if resolved_attribute not in char_data:
                return self.reply.render("attribute_not_found", attribute=resolved_attribute)
        
        buffs = await self._get_buffs(user_id)
        
        created_at = datetime.now().isoformat()
        
        buff = {
            "name": buff_name,
            "attribute": resolved_attribute,
            "type": buff_type,
            "value": value,
            "duration": duration,
            "created_at": created_at
        }
        
        buffs.append(buff)
        await self._save_buffs(user_id, buffs)
        
        # 如果有持续时间，调度战斗事件
        if duration is not None:
            # 构建描述
            action_desc = f"{character_name} Buff{buff_type} {resolved_attribute}{value:+g}"
            callback_message = f"{character_name} Buff{buff_type} {resolved_attribute}{value:+g}"
            
            # 直接调用 scheduler 调度事件
            from ...infrastructure.scheduler import schedule_event
            
            mode = 'time_based' if (isinstance(duration, str) and duration.endswith('t')) else 'count_based'
            duration_value = float(duration[:-1]) if (isinstance(duration, str) and duration.endswith('t')) else float(duration)
            
            schedule_event(
                conversation_id=conversation_id,
                user_id=user_id,
                character_name=character_name,
                action_description=action_desc,
                duration_or_count=duration_value,
                callback_path="trpg.service.buff.buff.remove_expired_buff",
                callback_args={
                    "user_id": user_id,
                    "created_at": created_at,
                    "attribute": resolved_attribute,
                    "buff_type": buff_type,
                    "buff_value": value
                },
                callback_message=callback_message,
                mode=mode,
                event_type='buff'
            )
        
        duration_str = "永久" if duration is None else str(duration)
        value_display = format_buff_value(value, buff_type)
        return self.reply.render("buff_added", name=buff_name, attribute=resolved_attribute, type=buff_type, value=value_display, duration=duration_str)
    
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

    async def _remove_multiple_buffs(self, user_id: str, indices: List[int]) -> str:
        """删除多个buff"""
        buffs = await self._get_buffs(user_id)
        
        if not buffs:
            return self.reply.render("no_buffs")

        # 验证序号
        invalid_indices = []
        valid_indices = []

        for idx in indices:
            if 0 <= idx < len(buffs):
                valid_indices.append(idx)
            else:
                invalid_indices.append(idx + 1)

        if not valid_indices:
            return self.reply.render("invalid_index")

        # 从后往前删除，避免索引偏移
        for idx in sorted(valid_indices, reverse=True):
            buffs.pop(idx)

        if await self._save_buffs(user_id, buffs):
            if invalid_indices:
                return self.reply.render(
                    "buff_multi_deleted_partial",
                    valid=len(valid_indices),
                    invalid=len(invalid_indices)
                )
            else:
                return self.reply.render("buff_multi_deleted", count=len(valid_indices))
        else:
            return self.reply.render("save_failed")
    
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
            # 格式化数值显示
            val_display = format_buff_value(val, btype)
            lines.append(f"[{i + 1}] {name} {attr} {btype} {val_display} 持续: {dur}")
        
        return "\n".join(lines)
    
    def get_buff_modifier(self, user_id: str, attribute: str) -> float:
        """
        获取角色指定属性的Buff修正值（同步版本）
        用于与角色属性系统集成
        """
        buffs = asyncio.run(self._get_buffs(user_id))
        
        total_modifier = 0.0
        for buff in buffs:
            if buff.get('attribute') == attribute:
                total_modifier += buff.get('value', 0)
        
        return total_modifier
    
    async def get_buff_modifier_async(self, user_id: str, attribute: str) -> float:
        """
        获取角色指定属性的Buff修正值（异步版本）
        用于与战斗系统集成
        """
        buffs = await self._get_buffs(user_id)
        
        total_modifier = 0.0
        for buff in buffs:
            if buff.get('attribute') == attribute:
                total_modifier += buff.get('value', 0)
        
        return total_modifier


# 用于存储正在等待保存的角色数据（避免并发问题）
_pending_character_saves: Dict[str, asyncio.Lock] = {}


async def remove_expired_buff(user_id: str, created_at: str, attribute: str = None, buff_type: str = None, buff_value: float = None) -> bool:
    """
    模块级函数，用于移除过期的buff
    由战斗系统在定时事件触发时调用
    
    直接使用 created_at 精确匹配要删除的buff
    infrastructure 层会统一处理事件循环
    """
    from ..character.character import character_module
    
    # 获取角色模块
    char_module = character_module
    
    # 获取当前激活的角色
    active_char = await char_module.get_active_character(user_id)
    if not active_char:
        return False
    
    buffs = active_char.get('buffs', [])
    
    if not buffs:
        return False
    
    # 查找并移除匹配的buff（使用唯一标识：created_at）
    original_count = len(buffs)
    buffs = [b for b in buffs if b.get('created_at') != created_at]
    
    if len(buffs) < original_count:
        # 更新并保存角色数据
        active_char['buffs'] = buffs
        
        # 保存角色数据
        characters = await char_module._get_user_characters(user_id)
        for i, char in enumerate(characters):
            if char.get('name') == active_char.get('name'):
                characters[i] = active_char
                break
        await char_module._save_characters(user_id, characters)
        
        return True
    
    return False


# 创建模块实例
buff_module = BuffModule()
