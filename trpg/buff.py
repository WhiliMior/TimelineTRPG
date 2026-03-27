"""
Buff模块 - 管理角色增益/减益效果
迁移自老项目 Game/Runtime/Buff/BuffManager.py

功能：
- 添加/移除 Buff
- 与战斗系统集成（定时事件）
- 与角色系统集成（属性修正）
"""
import re
from typing import Dict, List, Optional
from datetime import datetime

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry
from ..adapter.storage import StorageBackend, StorageType

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


class BuffModule:
    """
    Buff模块
    
    支持的指令格式：
    - .buff - 显示buff列表
    - .buff add <属性> <类型> <数值> [持续时间] - 添加buff
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
                "add {属性} {类型} {数值} (持续时间) - 添加buff\n"
                "show (覆盖范围) - 查看所有Buff或对范围生效的Buff\n"
                "del {序号}/all - 移除Buff\n"
                "\n"
                "示例:\n"
                "  buff add 力量 永久 5 → 添加力量属性永久buff，数值5\n"
                "  buff add 敏捷 临时 3 3t → 添加敏捷临时buff，数值3，持续3时间\n"
                "  buff del 1 → 删除第1个buff\n"
                "  buff del all → 删除所有buff"
            ),
        )
    
    async def buff(self, ctx: CommandContext) -> bool:
        """
        处理buff命令
        """
        user_id = ctx.sender_id or "default"
        conversation_id = ctx.group_id or ctx.session_id or user_id
        storage_key = f"{user_id}:{conversation_id}"
        
        if not ctx.args:
            # 没有参数，显示所有buff
            result = self._list_buffs(storage_key)
            ctx.send(result)
            return True
        
        command = ctx.args[0].lower()
        
        if command == 'add' and len(ctx.args) >= 4:
            # .buff add {属性} {类型} {数值} [持续时间]
            attribute = ctx.args[1]
            buff_type = ctx.args[2]
            value_str = ctx.args[3]
            
            duration = None
            if len(ctx.args) >= 5:
                duration_input = ctx.args[4]
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
            
            result = self._add_buff(storage_key, user_id, conversation_id, attribute, buff_type, value, duration)
            ctx.send(result)
        
        elif command == 'del' and len(ctx.args) >= 2:
            if ctx.args[1].lower() == 'all':
                result = self._remove_all_buffs(storage_key, user_id)
                ctx.send(result)
            else:
                try:
                    index = int(ctx.args[1])
                    result = self._remove_buff_by_index(storage_key, user_id, index)
                    ctx.send(result)
                except ValueError:
                    response = self.reply.render("invalid_number")
                    ctx.send(response)
        
        elif command == 'show':
            if len(ctx.args) >= 2:
                attribute = ctx.args[1]
                result = self._list_buffs(storage_key, attribute)
            else:
                result = self._list_buffs(storage_key)
            ctx.send(result)
        
        else:
            result = self._list_buffs(storage_key)
            ctx.send(result)
        
        return True
    
    def _resolve_attribute_name(self, attribute: str) -> str:
        """解析属性名称，使用别名映射"""
        return ATTRIBUTE_ALIASES.get(attribute, attribute)
    
    def _get_character_module(self):
        """获取角色模块"""
        from trpg.character import character_module
        return character_module
    
    def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色"""
        char_module = self._get_character_module()
        return char_module.get_active_character(user_id)
    
    def _get_buffs(self, storage_key: str) -> List[Dict]:
        """获取buff列表"""
        return StorageBackend.load(StorageType.USER, storage_key, default=[])
    
    def _save_buffs(self, storage_key: str, buffs: List[Dict]):
        """保存buff列表"""
        StorageBackend.save(StorageType.USER, storage_key, buffs)
    
    def _add_buff(self, storage_key: str, user_id: str, conversation_id: str, 
                  attribute: str, buff_type: str, value: float, duration) -> str:
        """添加buff"""
        # 检查角色
        active_char = self._get_active_character(user_id)
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
        
        buffs = self._get_buffs(storage_key)
        
        buff = {
            "attribute": resolved_attribute,
            "type": buff_type,
            "value": value,
            "duration": duration,
            "created_at": datetime.now().isoformat(),
            "character_name": character_name
        }
        
        buffs.append(buff)
        self._save_buffs(storage_key, buffs)
        
        # 如果有持续时间，调度战斗事件
        if duration is not None:
            # 通知战斗系统调度事件
            self._schedule_buff_event(conversation_id, user_id, character_name, 
                                    resolved_attribute, buff_type, value, duration)
        
        duration_str = "永久" if duration is None else str(duration)
        return self.reply.render("buff_added", attribute=resolved_attribute, value=value, duration=duration_str)
    
    def _schedule_buff_event(self, conversation_id: str, user_id: str, character_name: str,
                           attribute: str, buff_type: str, buff_value: float, duration):
        """
        调度buff事件
        """
        # 导入战斗模块
        from trpg.battle import battle_module
        
        # 确定模式
        mode = 'time_based' if (isinstance(duration, str) and duration.endswith('t')) else 'count_based'
        duration_value = float(duration[:-1]) if (isinstance(duration, str) and duration.endswith('t')) else float(duration)
        
        # 构建描述
        action_desc = f"{character_name} Buff{buff_type} {attribute}{buff_value:+g}"
        
        # 调用战斗系统调度事件
        battle_module.schedule_buff_event(
            conversation_id=conversation_id,
            user_id=user_id,
            character_name=character_name,
            action_description=action_desc,
            duration_or_count=duration_value,
            callback_path=f"trpg.buff.remove_expired_buff",
            callback_args={
                "user_id": user_id,
                "attribute": attribute,
                "buff_type": buff_type,
                "buff_value": buff_value
            },
            callback_message=f"{character_name} Buff{buff_type} {attribute}{buff_value:+g} 已到期",
            mode=mode
        )
    
    def _remove_buff(self, storage_key: str, attribute: Optional[str]) -> str:
        """删除buff（按属性名）"""
        buffs = self._get_buffs(storage_key)
        
        if not buffs:
            return self.reply.render("no_buffs")
        
        if attribute is None:
            # 删除所有
            self._save_buffs(storage_key, [])
            return self.reply.render("all_buffs_removed")
        
        # 删除指定属性的buff
        original_count = len(buffs)
        buffs = [b for b in buffs if b.get('attribute') != attribute]
        
        if len(buffs) == original_count:
            return self.reply.render("buff_not_found", attribute=attribute)
        
        self._save_buffs(storage_key, buffs)
        return self.reply.render("buff_removed", attribute=attribute)
    
    def _remove_buff_by_index(self, storage_key: str, user_id: str, index: int) -> str:
        """按索引删除buff"""
        buffs = self._get_buffs(storage_key)
        
        if not buffs:
            return self.reply.render("no_buffs")
        
        if index < 1 or index > len(buffs):
            return self.reply.render("invalid_index")
        
        removed = buffs.pop(index - 1)
        self._save_buffs(storage_key, buffs)
        
        return self.reply.render("buff_removed_by_index", index=index, attribute=removed.get('attribute', ''))
    
    def _remove_all_buffs(self, storage_key: str, user_id: str) -> str:
        """删除所有buff"""
        buffs = self._get_buffs(storage_key)
        
        if not buffs:
            return self.reply.render("no_buffs")
        
        self._save_buffs(storage_key, [])
        return self.reply.render("all_buffs_removed")
    
    def _list_buffs(self, storage_key: str, attribute: Optional[str] = None) -> str:
        """显示buff列表"""
        buffs = self._get_buffs(storage_key)
        
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
            attr = buff.get('attribute', '')
            btype = buff.get('type', '')
            val = buff.get('value', 0)
            dur = buff.get('duration', '永久')
            lines.append(f"[{i + 1}] {attr} {btype} {val} 持续: {dur}")
        
        return "\n".join(lines)
    
    def get_buff_modifier(self, user_id: str, attribute: str) -> float:
        """
        获取角色指定属性的Buff修正值
        用于与角色属性系统集成
        """
        storage_key = f"{user_id}"
        buffs = self._get_buffs(storage_key)
        
        total_modifier = 0.0
        for buff in buffs:
            if buff.get('attribute') == attribute:
                total_modifier += buff.get('value', 0)
        
        return total_modifier


def remove_expired_buff(user_id: str, attribute: str, buff_type: str, buff_value: float) -> bool:
    """
    模块级函数，用于移除过期的buff
    由战斗系统在定时事件触发时调用
    """
    storage_key = f"{user_id}"
    buffs = StorageBackend.load(StorageType.USER, storage_key, default=[])
    
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
        StorageBackend.save(StorageType.USER, storage_key, buffs)
        return True
    
    return False


# 创建模块实例
buff_module = BuffModule()
