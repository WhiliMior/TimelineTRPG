"""
武器模块 - 管理角色武器
迁移自老项目 Game/Runtime/Weapon/

功能：
- 创建武器
- 武器列表管理
- 选择装备武器
- 武器详情查看
- 删除武器
"""
from typing import Dict, List, Optional

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry
from ..adapter.storage import StorageBackend, StorageType


class WeaponModule:
    """
    武器模块
    
    支持的指令格式：
    - .wp - 显示武器列表
    - .wp <序号> - 选择武器
    - .wp show <序号> - 查看武器详情
    - .wp del <序号> - 删除武器
    - .wp create <名称> <类型> <属性> - 创建武器（需要完整参数）
    """
    
    def __init__(self):
        self.reply = ReplyManager("weapon")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="wp",
            usage="[序号|show|del|create] [参数]",
            summary="武器管理",
            detail=(
                "- 显示武器列表\n"
                "{序号} - 选择武器\n"
                "show {序号} - 查看武器详情\n"
                "del {序号}/all - 删除武器\n"
                "create {名称} {类型} {属性} (伤害) (射程) - 创建武器\n"
                "\n"
                "示例:\n"
                "  wp → 显示武器列表\n"
                "  wp 1 → 选择第1把武器\n"
                "  wp show 1 → 查看第1把武器详情\n"
                "  wp create 弓箭 投射 敏捷 10 50 → 创建武器"
            ),
        )
    
    async def wp_setup(self, ctx: CommandContext) -> bool:
        """
        处理武器创建命令 (.WPsetup)
        格式: .WPsetup '名称':'值','类型':'值',...
        示例: .WPsetup '名称':'激光枪','类型':'火力','伤害':20,'负重':3.5
        """
        import re
        user_id = ctx.sender_id or "default"
        
        # 获取原始命令文本
        raw_args = ctx.raw_message or ""
        
        # 解析 '键':'值' 格式
        pattern = r"'([^']+)':[^,']+"
        matches = re.findall(pattern, raw_args)
        
        if not matches:
            # 尝试解析简单的键值对格式
            # 格式: 名称:值,类型:值
            simple_pattern = r"([^:,]+):([^,]+)"
            simple_matches = re.findall(simple_pattern, raw_args)
            
            if simple_matches:
                # 构建参数列表
                args = [m[1].strip() for m in simple_matches]
                result = await self._create_weapon(user_id, args)
                ctx.send(result)
            else:
                ctx.send("用法: .WPsetup '名称':'值','类型':'值',...\n示例: .WPsetup '名称':'激光枪','类型':'火力','伤害':20")
            return True
        
        # 使用匹配到的值列表
        # 需要手动解析获取值
        value_pattern = r"'([^']+)':'?([^',]*)'?"
        values = re.findall(value_pattern, raw_args)
        
        if values:
            # 将值转换为列表
            args = [v[1] if v[1] else v[0] for v in values]
            result = await self._create_weapon(user_id, args)
            ctx.send(result)
        else:
            ctx.send("用法: .WPsetup '名称':'值','类型':'值',...\n示例: .WPsetup '名称':'激光枪','类型':'火力','伤害':20")
        
        return True
    
    async def wp(self, ctx: CommandContext) -> bool:
        """
        处理武器命令
        """
        user_id = ctx.sender_id or "default"
        
        if not ctx.args:
            # 显示武器列表
            result = await self._list_weapons(user_id)
            ctx.send(result)
            return True
        
        command = ctx.args[0].lower()
        
        if command == 'create':
            # 创建武器
            result = await self._create_weapon(user_id, ctx.args[1:])
            ctx.send(result)
        
        elif command == 'show':
            if len(ctx.args) < 2:
                result = await self._list_weapons(user_id)
            else:
                try:
                    index = int(ctx.args[1])
                    result = await self._show_weapon(user_id, index)
                except ValueError:
                    result = self.reply.render("invalid_number")
            ctx.send(result)
        
        elif command == 'del':
            if len(ctx.args) < 2:
                result = self.reply.render("need_item_index")
                ctx.send(result)
            elif ctx.args[1].lower() == 'all':
                result = await self._delete_all_weapons(user_id)
                ctx.send(result)
            else:
                try:
                    index = int(ctx.args[1])
                    result = await self._delete_weapon(user_id, index)
                except ValueError:
                    result = self.reply.render("invalid_number")
                ctx.send(result)
        
        elif command.isdigit():
            try:
                index = int(command)
                result = await self._select_weapon(user_id, index)
                ctx.send(result)
            except ValueError:
                result = self.reply.render("invalid_number")
                ctx.send(result)
        
        else:
            result = await self._list_weapons(user_id)
            ctx.send(result)
        
        return True
    
    async def _get_character_module(self):
        """获取角色模块"""
        from trpg.character import character_module
        return character_module
    
    async def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色"""
        char_module = await self._get_character_module()
        return await char_module.get_active_character(user_id)
    
    async def _get_weapons(self, user_id: str) -> List[Dict]:
        """获取武器列表"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return []
        
        char_name = active_char.get('name', '')
        storage_key = f"{user_id}:{char_name}"
        
        return StorageBackend.load_weapons(storage_key)
    
    async def _save_weapons(self, user_id: str, weapons: List[Dict]):
        """保存武器列表"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return
        
        char_name = active_char.get('name', '')
        storage_key = f"{user_id}:{char_name}"
        StorageBackend.save_weapons(storage_key, weapons)
    
    async def _create_weapon(self, user_id: str, args: List[str]) -> str:
        """创建武器"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")
        
        if len(args) < 3:
            return "用法: wp create {名称} {类型} {属性} (伤害) (射程)\n类型: 斩击/打击/投射/火力/其他\n属性: 力量/敏捷/智力等"
        
        name = args[0]
        weapon_type = args[1]
        attribute = args[2]
        
        damage = 0
        if len(args) >= 4:
            try:
                damage = float(args[3])
            except ValueError:
                pass
        
        range_val = 0
        if len(args) >= 5:
            try:
                range_val = float(args[4])
            except ValueError:
                pass
        
        weapon = {
            "name": name,
            "type": weapon_type,
            "attribute": attribute,
            "damage": damage,
            "range": range_val,
            "equipped": False
        }
        
        weapons = await self._get_weapons(user_id)
        
        # 如果是第一把武器，自动装备
        if len(weapons) == 0:
            weapon["equipped"] = True
        
        weapons.append(weapon)
        await self._save_weapons(user_id, weapons)
        
        return self.reply.render("weapon_created", name=active_char.get('name', ''), weapon=name)
    
    async def _list_weapons(self, user_id: str) -> str:
        """显示武器列表"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")
        
        weapons = await self._get_weapons(user_id)
        
        if not weapons:
            return self.reply.render("weapon_list_empty")
        
        lines = [self.reply.render("weapon_list_header", count=len(weapons))]
        
        for i, weapon in enumerate(weapons):
            equipped = "●" if weapon.get('equipped', False) else f"{i+1}"
            lines.append(f"[{equipped}] {weapon.get('name', '未命名')} - {weapon.get('type', '其他')} ({weapon.get('attribute', '')})")
        
        return "\n".join(lines)
    
    async def _show_weapon(self, user_id: str, index: int) -> str:
        """显示武器详情"""
        weapons = await self._get_weapons(user_id)
        
        if not weapons:
            return self.reply.render("weapon_list_empty")
        
        if index < 1 or index > len(weapons):
            return self.reply.render("invalid_index")
        
        weapon = weapons[index - 1]
        
        lines = [
            f"=== {weapon.get('name', '未命名')} ===",
            f"类型: {weapon.get('type', '其他')}",
            f"属性: {weapon.get('attribute', '')}",
            f"伤害: {weapon.get('damage', 0)}",
            f"射程: {weapon.get('range', 0)}",
            f"装备: {'是' if weapon.get('equipped', False) else '否'}"
        ]
        
        return "\n".join(lines)
    
    async def _select_weapon(self, user_id: str, index: int) -> str:
        """选择武器"""
        weapons = await self._get_weapons(user_id)
        
        if not weapons:
            return self.reply.render("weapon_list_empty")
        
        if index < 1 or index > len(weapons):
            return self.reply.render("invalid_index")
        
        # 先取消所有武器的装备状态
        for weapon in weapons:
            weapon['equipped'] = False
        
        # 装备选中的武器
        weapons[index - 1]['equipped'] = True
        await self._save_weapons(user_id, weapons)
        
        return self.reply.render("weapon_selected", name=weapons[index - 1].get('name', ''))
    
    async def _delete_weapon(self, user_id: str, index: int) -> str:
        """删除武器"""
        weapons = await self._get_weapons(user_id)
        
        if not weapons:
            return self.reply.render("weapon_list_empty")
        
        if index < 1 or index > len(weapons):
            return self.reply.render("invalid_index")
        
        removed = weapons.pop(index - 1)
        await self._save_weapons(user_id, weapons)
        
        return self.reply.render("weapon_deleted", name=removed.get('name', ''))
    
    async def _delete_all_weapons(self, user_id: str) -> str:
        """删除所有武器"""
        weapons = await self._get_weapons(user_id)
        
        if not weapons:
            return self.reply.render("weapon_list_empty")
        
        await self._save_weapons(user_id, [])
        
        return self.reply.render("all_weapons_deleted")
    
    async def get_equipped_weapon(self, user_id: str) -> Optional[Dict]:
        """获取当前装备的武器"""
        weapons = await self._get_weapons(user_id)
        
        for weapon in weapons:
            if weapon.get('equipped', False):
                return weapon
        
        return None


# 创建模块实例
weapon_module = WeaponModule()
