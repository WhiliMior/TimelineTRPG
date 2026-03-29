"""
资源记录模块 - 记录资源变化
迁移自老项目 Game/Runtime/Resource/
"""
import re
import time
from typing import Dict, List, Optional, Tuple

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend


class ResourceRecordModule:
    """
    资源记录模块
    
    支持的指令格式：
    - .rc {hp/mp} {变化值} (持续时间) (f) - 修改资源
    - .rc 护盾/s {变化值} (覆盖范围) (持续时间) (f) - 修改护盾资源
    - .rc reset - 重置资源到最大值
    - .rc show - 显示当前资源状态
    """
    
    # 资源类型映射
    RESOURCE_TYPE_MAPPING = {
        'hp': 'hp',
        '体力': 'hp',
        'mp': 'mp',
        '意志': 'mp',
        's': 'shield',
        '护盾': 'shield'
    }
    
    # 覆盖类型映射
    COVERAGE_TYPE_MAPPING = {
        'hp': 'hp',
        '体力': 'hp',
        'mp': 'mp',
        '意志': 'mp',
        'all': 'all',
        '所有': 'all'
    }
    
    def __init__(self):
        self.reply = ReplyManager("resource_record")
        self.system_reply = ReplyManager("system")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="rc",
            usage="[hp/mp|护盾] [变化值] [持续时间] [f]",
            summary="资源记录",
            detail=(
                "{hp/mp} {变化值} (持续时间) (f) - 修改资源，f标记允许修改超过上限\n"
                "护盾/s {变化值} (覆盖范围) (持续时间) (f) - 添加护盾资源\n"
                "reset - 重置资源到最大值并清除护盾\n"
                "show - 显示当前资源状态"
            ),
        )
    
    async def rc(self, ctx: CommandContext) -> bool:
        """
        处理资源记录命令
        
        指令格式：
        - .rc {hp/mp} {变化值} (持续时间) (f) - 修改资源
        - .rc 护盾/s {变化值} (覆盖范围) (持续时间) (f) - 添加护盾
        - .rc reset - 重置资源到最大值
        - .rc show - 显示当前资源状态
        """
        user_id = ctx.sender_id or "default"
        
        if not ctx.args:
            # 显示资源状态
            result = await self._get_resource_status(user_id)
            ctx.send(result)
            return True
        
        command = ctx.args[0].lower()
        
        # 重置资源
        if command == 'reset':
            result = await self._reset_resources(user_id)
            ctx.send(result)
            return True
        
        # 显示资源状态
        if command == 'show':
            result = await self._get_resource_status(user_id)
            ctx.send(result)
            return True
        
        # 检查是否是资源类型 (hp/mp/体力/意志)
        if command in self.RESOURCE_TYPE_MAPPING:
            resource_type = self.RESOURCE_TYPE_MAPPING[command]
            if resource_type == 'shield':
                # 护盾: .rc 护盾/s {变化值} (覆盖范围) (持续时间) (f)
                conversation_id = ctx.group_id or ctx.session_id or user_id
                result = await self._handle_shield(user_id, conversation_id, ctx.args[1:])
                ctx.send(result)
            else:
                # HP/MP: .rc hp/mp {变化值} (持续时间) (f)
                result = await self._handle_resource(user_id, resource_type, ctx.args[1:])
                ctx.send(result)
            return True
        
        # 检查是否是 s 或 护盾
        if command == 's' or command == '护盾':
            conversation_id = ctx.group_id or ctx.session_id or user_id
            result = await self._handle_shield(user_id, conversation_id, ctx.args[1:])
            ctx.send(result)
            return True
        
        # 无效命令
        response = self.system_reply.render("command_not_found", command=ctx.command)
        ctx.send(response)
        return True
    
    async def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色"""
        from ..character.character import character_module
        return await character_module.get_active_character(user_id)
    
    async def _get_resource_data(self, user_id: str) -> Dict:
        """获取角色资源数据"""
        character = await self._get_active_character(user_id)
        if not character:
            return {"current_hp": 0, "current_mp": 0, "shields": []}
        
        resources = character.get('resources', {})
        return {
            "current_hp": resources.get('current_hp', 0),
            "current_mp": resources.get('current_mp', 0),
            "shields": resources.get('shields', [])
        }
    
    async def _save_resource_data(self, user_id: str, resources: Dict) -> bool:
        """保存角色资源数据 - 通过StorageBackend保存到角色resources字段中"""
        character = await self._get_active_character(user_id)
        if not character:
            return False
        
        # 更新角色的resources字段
        character['resources'] = resources
        
        # 通过StorageBackend保存整个角色数据
        return StorageBackend.update_character(user_id, character.get('name'), character)
    
    async def _get_max_resources(self, user_id: str) -> Tuple[Optional[float], Optional[float]]:
        """获取角色的HP和MP最大值"""
        character = await self._get_active_character(user_id)
        if not character:
            return None, None
        
        # 从角色数据中获取体质和意志作为最大值
        data = character.get('data', {})
        max_hp = data.get('体质')
        max_mp = data.get('意志')
        
        return max_hp, max_mp
    
    def _parse_value_with_percentage(self, value_str: str, max_value: Optional[float]) -> Optional[float]:
        """解析数值，支持百分比格式"""
        value_str = value_str.strip()
        
        if value_str.endswith('%'):
            if max_value is None:
                return None
            try:
                percentage = float(value_str[:-1])
                return round(max_value * percentage / 100.0, 1)
            except ValueError:
                return None
        else:
            try:
                return float(value_str)
            except ValueError:
                return None
    
    async def _handle_resource(self, user_id: str, resource_type: str, args: List[str]) -> str:
        """处理HP/MP资源变化"""
        if len(args) < 1:
            return self.reply.render("need_params")
        
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")
        
        # 获取最大值
        max_hp, max_mp = await self._get_max_resources(user_id)
        max_value = max_hp if resource_type == 'hp' else max_mp
        
        if max_value is None:
            attr_name = '体质' if resource_type == 'hp' else '意志'
            return f"未找到{attr_name}属性，请先设置角色属性"
        
        # 解析变化值
        value_str = args[0]
        value_change = self._parse_value_with_percentage(value_str, max_value)
        
        if value_change is None:
            return self.reply.render("invalid_value")
        
        # 检查是否有f标记（允许溢出）
        allow_overflow = 'f' in [arg.lower() for arg in args]
        
        # 获取当前值
        resources = await self._get_resource_data(user_id)
        current_attr = f'current_{resource_type}'
        current_value = resources.get(current_attr, 0)
        
        # 计算新值
        new_value = current_value + value_change
        
        # 验证范围（除非允许溢出）
        if not allow_overflow:
            if new_value < 0:
                new_value = 0
            elif new_value > max_value:
                new_value = max_value
        
        # 更新资源
        resources[current_attr] = new_value
        
        if await self._save_resource_data(user_id, resources):
            # 格式化显示
            change_str = f"+{value_change:.1f}" if value_change >= 0 else f"{value_change:.1f}"
            attr_name = 'HP' if resource_type == 'hp' else 'MP'
            
            if resource_type == 'hp':
                return self.reply.render("hp_changed", change=change_str, value=f"{new_value:.1f}/{max_value:.1f}")
            else:
                return self.reply.render("mp_changed", change=change_str, value=f"{new_value:.1f}/{max_value:.1f}")
        else:
            return self.reply.render("save_failed")
    
    async def _handle_shield(self, user_id: str, conversation_id: str, args: List[str]) -> str:
        """处理护盾资源"""
        if len(args) < 1:
            return self.reply.render("need_params")
        
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")
        
        # 获取HP最大值作为参考
        max_hp, _ = await self._get_max_resources(user_id)
        if max_hp is None:
            max_hp = 100  # 默认值
        
        # 解析护盾值
        value_str = args[0]
        shield_value = self._parse_value_with_percentage(value_str, max_hp)
        
        if shield_value is None:
            return self.reply.render("invalid_value")
        
        # 解析覆盖类型（可选，默认为all）
        coverage_type = 'all'
        if len(args) > 1:
            cov = args[1].lower()
            if cov in self.COVERAGE_TYPE_MAPPING:
                coverage_type = self.COVERAGE_TYPE_MAPPING[cov]
            else:
                return self.reply.render("invalid_value")
        
        # 解析持续时间（可选）
        duration = "0t"
        if len(args) > 2:
            duration = args[2]
        
        # 检查是否有f标记
        allow_overflow = 'f' in [arg.lower() for arg in args]
        
        # 创建护盾
        resources = await self._get_resource_data(user_id)
        
        shield_id = f"shield_{int(time.time())}_{hash(str(shield_value) + coverage_type + duration) % 10000}"
        
        shield = {
            'id': shield_id,
            'value': shield_value,
            'coverage_type': coverage_type,
            'duration': duration,
            'created_at': time.time()
        }
        
        shields = resources.get('shields', [])
        shields.append(shield)
        resources['shields'] = shields
        
        # 如果有持续时间，调度护盾到期事件
        if duration and duration != "0t" and duration != "0":
            self._schedule_shield_event(conversation_id, user_id, shield_id, duration, coverage_type, shield_value)
        
        if await self._save_resource_data(user_id, resources):
            return self.reply.render("shield_added", value=f"{shield_value:.1f}")
        else:
            return self.reply.render("save_failed")
    
    async def _get_resource_status(self, user_id: str) -> str:
        """获取资源状态"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")
        
        resources = await self._get_resource_data(user_id)
        max_hp, max_mp = await self._get_max_resources(user_id)
        
        current_hp = resources.get('current_hp', 0)
        current_mp = resources.get('current_mp', 0)
        shields = resources.get('shields', [])
        
        # 构建状态信息
        lines = []
        
        # HP
        if max_hp is not None:
            lines.append(f"体力：{current_hp:.1f}/{max_hp:.1f}")
        else:
            lines.append(f"体力：{current_hp:.1f}/未知")
        
        # MP
        if max_mp is not None:
            lines.append(f"意志：{current_mp:.1f}/{max_mp:.1f}")
        else:
            lines.append(f"意志：{current_mp:.1f}/未知")
        
        # 护盾
        if shields:
            lines.append("")
            lines.append("护盾：")
            
            # 统计不同类型护盾的总值
            hp_shield = 0
            mp_shield = 0
            all_shield = 0
            
            for shield in shields:
                cov = shield.get('coverage_type', 'all')
                val = shield.get('value', 0)
                if cov in ['hp', '体力']:
                    hp_shield += val
                elif cov in ['mp', '意志']:
                    mp_shield += val
                elif cov in ['all', '所有']:
                    all_shield += val
            
            if hp_shield > 0:
                lines.append(f"体力类型： {hp_shield:.1f}")
            if mp_shield > 0:
                lines.append(f"意志类型：{mp_shield:.1f}")
            if all_shield > 0:
                lines.append(f"全类型：{all_shield:.1f}")
        else:
            lines.append("护盾：无")
        
        return self.reply.render("resource_show", hp=lines[0], mp=lines[1], shield="\n".join(lines[2:]) if len(lines) > 2 else "无")
    
    async def _reset_resources(self, user_id: str) -> str:
        """重置资源到最大值"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")
        
        max_hp, max_mp = await self._get_max_resources(user_id)
        
        if max_hp is None:
            return "未找到体质属性，请先设置角色属性"
        
        if max_mp is None:
            return "未找到意志属性，请先设置角色属性"
        
        # 重置资源
        resources = {
            'current_hp': max_hp,
            'current_mp': max_mp,
            'shields': []
        }
        
        if await self._save_resource_data(user_id, resources):
            return self.reply.render("resource_reset")
        else:
            return self.reply.render("save_failed")


    def _schedule_shield_event(self, conversation_id: str, user_id: str, shield_id: str, 
                               duration: str, coverage_type: str, shield_value: float):
        """
        调度护盾到期事件
        """
        # 使用 infrastructure scheduler 避免循环引用
        from ...infrastructure.scheduler import schedule_event
        import asyncio
        
        # 获取角色名（同步方式）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            character = loop.run_until_complete(self._get_active_character(user_id))
        finally:
            loop.close()
        
        if not character:
            return
        character_name = character.get('name', '未知角色')
        
        # 确定模式
        mode = 'time_based' if (isinstance(duration, str) and duration.endswith('t')) else 'count_based'
        duration_value = float(duration[:-1]) if (isinstance(duration, str) and duration.endswith('t')) else float(duration)
        
        # 构建描述
        action_desc = f"{character_name} {coverage_type}护盾 {shield_value}"
        callback_msg = f"{character_name} {coverage_type}护盾 {shield_value} 已到期"
        
        # 调用 scheduler 调度事件
        schedule_event(
            conversation_id=conversation_id,
            user_id=user_id,
            character_name=character_name,
            action_description=action_desc,
            duration_or_count=duration_value,
            callback_path=f"trpg.service.resource.resource.remove_expired_shield",
            callback_args={
                "user_id": user_id,
                "shield_id": shield_id
            },
            callback_message=callback_msg,
            mode=mode,
            event_type='shield'
        )


def remove_expired_shield(user_id: str, shield_id: str) -> bool:
    """
    模块级函数，用于移除到期的护盾
    由战斗系统在定时事件触发时调用
    """
    import asyncio
    
    async def _do_remove():
        character_module = None
        
        # 获取角色模块
        from ..character.character import character_module as cm
        character = cm.get_active_character(user_id)
        if not character:
            return False
        
        resources = character.get('resources', {})
        shields = resources.get('shields', [])
        
        if not shields:
            return False
        
        # 查找并移除指定ID的护盾
        original_count = len(shields)
        shields = [s for s in shields if s.get('id') != shield_id]
        
        if len(shields) < original_count:
            resources['shields'] = shields
            
            # 保存角色数据
            characters = await cm._get_user_characters(user_id)
            for i, char in enumerate(characters):
                if char.get('name') == character.get('name'):
                    characters[i] = character
                    break
            
            await cm._save_characters(user_id, characters)
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
        print(f"Error removing expired shield: {e}")
        return False


resource_record_module = ResourceRecordModule()
