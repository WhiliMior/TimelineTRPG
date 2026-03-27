"""
角色管理模块 - 处理角色相关功能
迁移自老项目 Game/Character/
"""
from typing import Dict, List, Optional

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry


# 角色数据存储
_character_storage: Dict[str, List[Dict]] = {}


class CharacterModule:
    """
    角色管理模块
    
    支持的指令格式：
    - .chr - 显示角色列表
    - .chr [序号] - 选择角色
    - .chr show - 显示角色详细信息
    - .chr del [序号] - 删除角色
    - .chr del all - 删除所有角色
    
    注意：此模块需要与角色创建系统配合使用
    """
    
    def __init__(self):
        self.reply = ReplyManager("character")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="chr",
            usage="[序号|show|del]",
            summary="角色管理",
            detail=(
                "- 显示角色列表\n"
                "show - 查看角色参数\n"
                "{序号} - 切换角色\n"
                "del {序号} - 删除角色\n"
                "\n"
                "示例:\n"
                "  chr → 显示角色列表\n"
                "  chr 1 → 选择第1个角色\n"
                "  chr show → 显示角色详情\n"
                "  chr del 2 → 删除第2个角色"
            ),
        )
    
    async def chr(self, ctx: CommandContext) -> bool:
        """
        处理角色管理命令
        """
        user_id = ctx.sender_id or "default"
        
        if not ctx.args:
            # 没有参数，显示角色列表
            response = await self._get_character_list(user_id)
            ctx.send(response)
            return True
        
        cmd = ctx.args[0].lower()
        
        if cmd == 'show':
            # 显示角色详细信息
            response = await self._show_character(user_id)
            ctx.send(response)
        elif cmd == 'del':
            # 删除角色
            if len(ctx.args) < 2:
                response = self.reply.render("specify_delete_index")
                ctx.send(response)
                return True
            
            if ctx.args[1].lower() == 'all':
                # 删除所有角色
                result = await self._delete_all_characters(user_id)
                ctx.send(result['message'])
            else:
                # 删除指定序号
                try:
                    indices = [int(x) - 1 for x in ctx.args[1:] if x.isdigit()]
                    if not indices:
                        response = self.reply.render("invalid_number")
                        ctx.send(response)
                        return True
                    result = await self._delete_multiple_characters(user_id, indices)
                    ctx.send(result['message'])
                except ValueError:
                    response = self.reply.render("index_must_be_number")
                    ctx.send(response)
        elif cmd.isdigit():
            # 选择角色
            try:
                index = int(cmd) - 1
                result = await self._select_character(user_id, index)
                ctx.send(result['message'])
            except ValueError:
                response = self.reply.render("index_must_be_number")
                ctx.send(response)
        else:
            response = self.reply.render("unknown_character_command")
            ctx.send(response)
        
        return True
    
    async def _get_user_characters(self, user_id: str) -> List[Dict]:
        """获取用户所有角色"""
        return _character_storage.get(user_id, [])
    
    async def _save_characters(self, user_id: str, characters: List[Dict]) -> bool:
        """保存角色列表"""
        _character_storage[user_id] = characters
        return True
    
    async def _get_character_list(self, user_id: str) -> str:
        """获取角色列表"""
        characters = await self._get_user_characters(user_id)
        
        if not characters:
            return self.reply.render("no_character")
        
        lines = [self.reply.render("character_list_header", count=str(len(characters)))]
        
        for i, character in enumerate(characters):
            active_status = "●" if character.get('active', False) else "  "
            name = character.get('name', self.reply.render("default_character_name", index=str(i + 1)))
            level = character.get('data', {}).get('等级', character.get('level', 1))
            
            line = f"[{i + 1}] [{active_status}] {name} lv{level}"
            lines.append(line)
        
        lines.append(self.reply.render("character_list_footer"))
        return "\n".join(lines)
    
    async def _select_character(self, user_id: str, index: int) -> Dict[str, str]:
        """选择启用角色"""
        characters = await self._get_user_characters(user_id)
        
        if not characters:
            return {
                'status': 'error',
                'message': self.reply.render("no_character")
            }
        
        if index < 0 or index >= len(characters):
            return {
                'status': 'error',
                'message': self.reply.render("invalid_index")
            }
        
        # 取消所有角色的激活状态
        for character in characters:
            character['active'] = False
        
        # 激活选中的角色
        characters[index]['active'] = True
        
        # 保存更改
        if await self._save_characters(user_id, characters):
            character_name = characters[index].get('name', self.reply.render("default_character_name", index=str(index + 1)))
            return {
                'status': 'success',
                'message': self.reply.render("character_selected", name=character_name)
            }
        else:
            return {
                'status': 'error',
                'message': self.reply.render("save_failed")
            }
    
    async def _delete_character(self, user_id: str, index: int) -> Dict[str, str]:
        """删除单个角色"""
        characters = await self._get_user_characters(user_id)
        
        if not characters:
            return {
                'status': 'error',
                'message': self.reply.render("no_character")
            }
        
        if index < 0 or index >= len(characters):
            return {
                'status': 'error',
                'message': self.reply.render("invalid_index")
            }
        
        deleted_character = characters.pop(index)
        
        # 如果删除的是当前激活的角色，激活第一个角色
        if not any(c.get('active', False) for c in characters) and characters:
            characters[0]['active'] = True
        
        if await self._save_characters(user_id, characters):
            character_name = deleted_character.get('name', self.reply.render("default_character_name", index=str(index + 1)))
            return {
                'status': 'success',
                'message': self.reply.render("character_deleted", name=character_name)
            }
        else:
            return {
                'status': 'error',
                'message': self.reply.render("save_failed")
            }
    
    async def _delete_multiple_characters(self, user_id: str, indices: List[int]) -> Dict[str, str]:
        """删除多个角色"""
        characters = await self._get_user_characters(user_id)
        
        if not characters:
            return {
                'status': 'error',
                'message': self.reply.render("no_character")
            }
        
        # 验证序号
        invalid_indices = []
        valid_indices = []
        
        for idx in indices:
            if 0 <= idx < len(characters):
                valid_indices.append(idx)
            else:
                invalid_indices.append(idx + 1)
        
        # 按降序删除
        valid_indices.sort(reverse=True)
        
        for idx in valid_indices:
            characters.pop(idx)
        
        # 重新设置激活状态
        if not any(c.get('active', False) for c in characters) and characters:
            characters[0]['active'] = True
        
        if await self._save_characters(user_id, characters):
            if invalid_indices:
                return {
                    'status': 'success',
                    'message': self.reply.render("character_multi_deleted_partial", valid=len(valid_indices), invalid=len(invalid_indices))
                }
            else:
                return {
                    'status': 'success',
                    'message': self.reply.render("character_multi_deleted", count=len(valid_indices))
                }
        else:
            return {
                'status': 'error',
                'message': self.reply.render("save_failed")
            }
    
    async def _delete_all_characters(self, user_id: str) -> Dict[str, str]:
        """删除所有角色"""
        characters = await self._get_user_characters(user_id)
        
        if not characters:
            return {
                'status': 'error',
                'message': self.reply.render("no_character")
            }
        
        characters.clear()
        
        if await self._save_characters(user_id, characters):
            return {
                'status': 'success',
                'message': self.reply.render("all_characters_deleted")
            }
        else:
            return {
                'status': 'error',
                'message': self.reply.render("save_failed")
            }
    
    async def _show_character(self, user_id: str) -> str:
        """显示当前激活角色详细信息"""
        characters = await self._get_user_characters(user_id)
        
        active_char = None
        for char in characters:
            if char.get('active', False):
                active_char = char
                break
        
        if not active_char:
            return self.reply.render("no_active_character")
        
        name = active_char.get('name', '未知')
        data = active_char.get('data', {})
        
        lines = [f"=== {name} ==="]
        for key, value in data.items():
            lines.append(f"{key}: {value}")
        
        return "\n".join(lines)
    
    async def get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取当前激活角色"""
        characters = await self._get_user_characters(user_id)
        for char in characters:
            if char.get('active', False):
                return char
        return None
    
    async def has_character(self, user_id: str) -> bool:
        """检查用户是否有角色"""
        return len(await self._get_user_characters(user_id)) > 0
    
    async def add_character(self, user_id: str, character: Dict) -> bool:
        """添加角色"""
        characters = await self._get_user_characters(user_id)
        
        # 如果是第一个角色，自动激活
        if not characters:
            character['active'] = True
        
        characters.append(character)
        return await self._save_characters(user_id, characters)


# 创建模块实例
character_module = CharacterModule()
