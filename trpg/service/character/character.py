"""
角色管理模块 - 处理角色相关功能
迁移自老项目 Game/Character/
"""
from datetime import datetime
from typing import Dict, List, Optional

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend
from ...infrastructure.character_picture import character_picture_generator


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
        self.system_reply = ReplyManager("system")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="chr",
            usage="[序号|show|del] [参数]",
            summary="角色管理",
            detail=(
                "- 显示角色列表\n"
                "show - 查看当前角色参数\n"
                "{序号} - 切换角色\n"
                "del {序号} - 删除指定角色\n"
                "del all - 删除所有角色\n"
                "\n"
                "创建角色: .tlsetup 名称:xxx,属性:值,..."
            ),
        )
    
    @property
    def help_entry_setup(self) -> HelpEntry:
        return HelpEntry(
            module="tlsetup",
            usage="名称:xxx,属性:值,...",
            summary="创建角色",
            detail=(
                "创建新角色\n"
                "格式: .tlsetup 名称:xxx,属性:值,..."
            ),
        )

    def _is_number(self, s: str) -> bool:
        """判断字符串是否为数字"""
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _parse_character_attributes(self, args_str: str) -> Dict[str, any]:
        """
        解析角色属性
        :param args_str: 命令参数字符串
        :return: 属性字典
        """
        if not args_str:
            return {}
        
        # 按逗号分割属性
        attribute_list = args_str.split(',')
        
        # 解析属性
        attribute_dict = {}
        for element in attribute_list:
            element = element.strip()
            if ':' in element:
                parts = element.split(':', 1)  # 只分割第一个冒号
                if len(parts) == 2:
                    attribute = parts[0].strip()
                    value = parts[1].strip()
                    # 属性为空则用0替代
                    if len(value) == 0:
                        value = 0
                    
                    # 对姓名/名称相关属性，不进行数字转换
                    name_attributes = ['姓名', '名称', 'name', '名称']
                    if attribute in name_attributes:
                        # 姓名属性始终为字符串
                        attribute_dict[attribute] = value
                    else:
                        # 其他属性按原逻辑处理
                        if self._is_number(value):
                            value = float(value)
                        attribute_dict[attribute] = value
        
        # 如果没有名称属性，设置默认名称
        if not any(key in attribute_dict for key in ['姓名', '名称', 'name']):
            attribute_dict['名称'] = "未命名角色"
        
        return attribute_dict

    def _organize_character_data(self, attributes: Dict[str, any], character_name: str) -> Dict[str, any]:
        """
        组织角色数据结构
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        character_data = {
            "name": character_name,
            "data": attributes,
            "active": True,  # 设置为当前使用
            "created_at": timestamp
        }
        
        return character_data

    async def tlsetup(self, ctx: CommandContext) -> bool:
        """
        处理 .tlsetup 命令 - 创建角色
        格式: .tlsetup 名称:xxx,属性:值,...
        示例: .tlsetup 名称:勇者,力量:10,敏捷:8,等级:1
        """
        user_id = ctx.sender_id or "default"
        
        if not ctx.args:
            ctx.send("用法: .tlsetup 名称:xxx,属性:值,...\n示例: .tlsetup 名称:勇者,力量:10,敏捷:8")
            return True
        
        # 合并所有参数（因为属性中可能包含空格）
        args_str = ' '.join(ctx.args)
        
        # 解析角色属性
        attributes = self._parse_character_attributes(args_str)
        
        if not attributes:
            ctx.send("角色数据格式错误，请使用 名称:xxx,属性:值 的格式")
            return True
        
        # 获取角色名称，支持多种名称字段
        character_name = attributes.get('姓名', attributes.get('名称', attributes.get('name', "未命名角色")))
        
        # 组织角色数据
        character_data = self._organize_character_data(attributes, character_name)
        
        # 获取现有角色列表
        existing_characters = await self._get_user_characters(user_id)
        
        # 检查是否存在同名角色
        existing_index = None
        for i, char in enumerate(existing_characters):
            if char.get('name') == character_name:
                existing_index = i
                break
        
        # 如果是新角色（非同名更新），则取消其他角色的激活状态
        if existing_index is None:
            for char in existing_characters:
                char['active'] = False
            # 新角色设为激活状态
            character_data['active'] = True
        else:
            # 如果是更新同名角色，保持其原有的激活状态
            original_active = existing_characters[existing_index].get('active', False)
            character_data['active'] = original_active
        
        # 更新或添加角色数据
        if existing_index is not None:
            existing_characters[existing_index] = character_data
        else:
            existing_characters.append(character_data)
        
        # 保存角色数据
        if await self._save_characters(user_id, existing_characters):
            ctx.send(f"角色 [{character_name}] 创建成功！")
        else:
            ctx.send("保存角色数据失败")
        
        return True

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
            # 显示角色详细信息（图片模式）
            image_path = character_picture_generator.generate_character_picture(user_id)
            if image_path:
                ctx.send_image(str(image_path), delete_after_send=True)
            else:
                # 如果图片生成失败，回退到文本模式
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
            response = self.system_reply.render("command_not_found", command=ctx.command)
            ctx.send(response)
        
        return True
    
    async def _get_user_characters(self, user_id: str) -> List[Dict]:
        """获取用户所有角色"""
        return StorageBackend.load_characters(user_id)
    
    async def _save_characters(self, user_id: str, characters: List[Dict]) -> bool:
        """保存角色列表"""
        return StorageBackend.save_characters(user_id, characters)
    
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
