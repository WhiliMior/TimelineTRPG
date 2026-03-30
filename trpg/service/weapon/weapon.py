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

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry

# 武器类型中英文映射
WEAPON_TYPE_MAP = {
    "amplifier": "增幅",
    "artillery": "火力",
    "none": "无类型",
}


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

    def _get_type_display(self, weapon_type: str) -> str:
        """获取武器类型的中文显示"""
        if not weapon_type:
            return self.reply.render("weapon_type_none")
        return WEAPON_TYPE_MAP.get(weapon_type.lower(), weapon_type)

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
                "create {名称} {类型} {属性} (伤害) (射程) - 创建武器"
            ),
        )

    async def wp_setup(self, ctx: CommandContext) -> bool:
        """
        处理武器创建命令 (.setupWP)
        格式: .setupWP 名称:值,类型:值,...
        示例: .setupWP 名称:激光枪,类型:火力,伤害:20,负重:3.5
        """
        import re

        user_id = ctx.sender_id or "default"

        # 获取原始命令文本 (message_str 包含完整指令如 ".setupWP 名称:...")
        raw_args = ctx.metadata.get("message_str", "") or ""
        # 去掉前缀 ".setupWP"
        if raw_args.startswith((".", "。", "#", "/")):
            # 找到第一个空格的位置，去掉前缀和命令
            prefix_match = re.match(r"^[.。#/](\w+)\s*(.*)$", raw_args)
            if prefix_match:
                raw_args = prefix_match.group(2)

        # 解析参数
        weapon_data = self._parse_weapon_args(raw_args)

        if not weapon_data:
            ctx.send(
                "用法: .setupWP 名称:值,类型:值,...\n类型只支持: 增幅(amplifier)、火力(artillery)、无类型(none)\n示例: .setupWP 名称:激光枪,类型:火力,伤害:20,负重:3.5"
            )
            return True

        # 创建武器
        result = await self._create_weapon_from_data(user_id, weapon_data)
        ctx.send(result)

        return True

    def _parse_weapon_args(self, args: str) -> Optional[Dict]:
        """
        解析武器参数
        格式: 名称:值,类型:值,...
        """
        if not args.strip():
            return None

        # 预处理：将中文冒号替换为英文冒号
        args = args.replace("：", ":")

        # 解析键值对
        params = []
        current_param = ""
        in_key = True
        colon_found = False

        for char in args:
            if char == ":" and not colon_found:
                colon_found = True
                current_param += char
            elif char == "," and colon_found:
                # 值结束，添加参数
                params.append(current_param.strip())
                current_param = ""
                in_key = True
                colon_found = False
            else:
                current_param += char
                if char == ":":
                    in_key = False

        # 添加最后一个参数
        if current_param.strip():
            params.append(current_param.strip())

        # 解析每个参数为键值对
        weapon_data = {}
        for param in params:
            if ":" in param:
                key_val = param.split(":", 1)
                if len(key_val) == 2:
                    key = key_val[0].strip()
                    value = key_val[1].strip()

                    # 转换中文字段名为英文字段名
                    field_map = {
                        "名称": "name",
                        "名字": "name",
                        "类型": "type",
                        "增幅属性": "attribute",
                        "伤害": "damage",
                        "前摇": "cast",
                        "射程": "range",
                        "载弹量": "load",
                        "当前载弹": "current_load",
                        "装填时间": "reload_time",
                        "负重": "weight",
                        "备注": "note",
                    }

                    field_name = field_map.get(key, key)

                    # 尝试转换数值类型
                    if field_name in [
                        "damage",
                        "cast",
                        "range",
                        "reload_time",
                        "weight",
                    ]:
                        try:
                            weapon_data[field_name] = float(value) if value else 0
                        except ValueError:
                            weapon_data[field_name] = value
                    elif field_name in ["load", "current_load"]:
                        # 处理空字符串和None的情况
                        if value is None or (
                            isinstance(value, str) and not value.strip()
                        ):
                            weapon_data[field_name] = 0
                        else:
                            try:
                                weapon_data[field_name] = int(value)
                            except ValueError:
                                weapon_data[field_name] = value
                    else:
                        weapon_data[field_name] = value

        # 武器类型映射：只支持三种类型
        # amplifier=增幅, artillery=火力, none=无类型
        valid_types = {"amplifier", "artillery", "none", "增幅", "火力", "无类型"}
        type_map = {
            "增幅": "amplifier",
            "火力": "artillery",
            "无类型": "none",
            "无": "none",
            "": "none",
        }

        if "type" in weapon_data:
            input_type = weapon_data["type"].strip().lower()
            if input_type in valid_types:
                weapon_data["type"] = type_map.get(
                    weapon_data["type"], weapon_data["type"]
                )
            else:
                # 无效类型，返回None拒绝创建
                return None

        # 验证必填字段
        if "name" not in weapon_data or not weapon_data["name"]:
            return None

        return weapon_data

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

        if command == "create":
            # 创建武器
            result = await self._create_weapon(user_id, ctx.args[1:])
            ctx.send(result)

        elif command == "show":
            if len(ctx.args) < 2:
                result = await self._list_weapons(user_id)
            else:
                try:
                    index = int(ctx.args[1])
                    result = await self._show_weapon(user_id, index)
                except ValueError:
                    result = self.reply.render("invalid_number")
            ctx.send(result)

        elif command == "del":
            if len(ctx.args) < 2:
                result = self.reply.render("need_item_index")
                ctx.send(result)
            elif ctx.args[1].lower() == "all":
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
        from ..character.character import character_module

        return character_module

    async def _get_active_character(self, user_id: str) -> Optional[Dict]:
        """获取用户当前激活的角色"""
        char_module = await self._get_character_module()
        return await char_module.get_active_character(user_id)

    async def _get_weapons(self, user_id: str) -> List[Dict]:
        """获取武器列表 - 从角色weapons字段中获取"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return []

        # 从角色的weapons字段中获取武器列表
        weapons = active_char.get("weapons", [])
        return weapons

    async def _save_weapons(self, user_id: str, weapons: List[Dict]):
        """保存武器列表 - 通过StorageBackend保存到角色weapons字段中"""
        from ...infrastructure.storage import StorageBackend

        active_char = await self._get_active_character(user_id)
        if not active_char:
            return

        # 更新角色的weapons字段
        active_char["weapons"] = weapons

        # 通过StorageBackend保存整个角色数据
        StorageBackend.update_character(user_id, active_char.get("name"), active_char)

    async def _create_weapon_from_data(self, user_id: str, weapon_data: Dict) -> str:
        """从参数字典创建武器"""
        from ...infrastructure.config.game_config import game_config

        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        # 设置默认值
        weapon_type = weapon_data.get("type", "none")
        weapon = {
            "name": weapon_data.get("name", ""),
            "type": weapon_type,
            "attribute": weapon_data.get("attribute", ""),
            "damage": weapon_data.get("damage", 0),
            "cast": weapon_data.get("cast", 0),
            "range": weapon_data.get("range", 0),
            "load": weapon_data.get("load", 0),
            "reload_time": weapon_data.get("reload_time", 0),
            "weight": weapon_data.get("weight", 0),
            "note": weapon_data.get("note", ""),
            "equipped": False,
        }

        # 火力武器需要初始化当前弹药数，确保是整数类型
        if weapon_type == "artillery":
            weapon["current_load"] = int(weapon_data.get("load", 0))
        else:
            weapon["current_load"] = int(weapon_data.get("current_load", 0))

        # 处理重量精度
        if weapon["weight"]:
            weapon["weight"] = game_config.round_value(weapon["weight"], "weight")

        weapons = await self._get_weapons(user_id)

        # 如果是第一把武器，自动装备
        if len(weapons) == 0:
            weapon["equipped"] = True

        weapons.append(weapon)
        await self._save_weapons(user_id, weapons)

        return self.reply.render(
            "weapon_created", name=active_char.get("name", ""), weapon=weapon["name"]
        )

    async def _create_weapon(self, user_id: str, args: List[str]) -> str:
        """创建武器"""
        active_char = await self._get_active_character(user_id)
        if not active_char:
            return self.reply.render("no_character")

        if len(args) < 3:
            return self.reply.render("wp_create_usage")

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
            "equipped": False,
        }

        weapons = await self._get_weapons(user_id)

        # 如果是第一把武器，自动装备
        if len(weapons) == 0:
            weapon["equipped"] = True

        weapons.append(weapon)
        await self._save_weapons(user_id, weapons)

        return self.reply.render(
            "weapon_created", name=active_char.get("name", ""), weapon=name
        )

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
            equipped = "●" if weapon.get("equipped", False) else f"{i + 1}"
            type_display = self._get_type_display(weapon.get("type", ""))
            weight = weapon.get("weight", 0)
            lines.append(
                f"[{equipped}] {weapon.get('name', '未命名')} - {type_display} ({weapon.get('attribute', '')}) 负重:{weight}"
            )

        return "\n".join(lines)

    async def _show_weapon(self, user_id: str, index: int) -> str:
        """显示武器详情"""
        weapons = await self._get_weapons(user_id)

        if not weapons:
            return self.reply.render("weapon_list_empty")

        if index < 1 or index > len(weapons):
            return self.reply.render("invalid_index")

        weapon = weapons[index - 1]
        weapon_type = weapon.get("type", "")

        lines = [
            f"=== {weapon.get('name', '未命名')} ===",
            f"类型: {self._get_type_display(weapon_type)}",
            f"属性: {weapon.get('attribute', '')}",
            f"伤害: {weapon.get('damage', 0)}",
            f"前摇: {weapon.get('cast', 0)}",
            f"射程: {weapon.get('range', 0)}",
            f"负重: {weapon.get('weight', 0)}",
            f"装备: {'是' if weapon.get('equipped', False) else '否'}",
        ]

        # 火力武器显示弹药信息
        if weapon_type == "artillery":
            current_load = weapon.get("current_load", 0)
            max_load = weapon.get("load", 0)
            reload_time = weapon.get("reload_time", 0)
            lines.append(f"弹药: {current_load}/{max_load}")
            lines.append(f"装填时间: {reload_time}")

        # 显示备注
        note = weapon.get("note", "")
        if note:
            lines.append(f"备注: {note}")

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
            weapon["equipped"] = False

        # 装备选中的武器
        weapons[index - 1]["equipped"] = True
        await self._save_weapons(user_id, weapons)

        return self.reply.render(
            "weapon_selected", name=weapons[index - 1].get("name", "")
        )

    async def _delete_weapon(self, user_id: str, index: int) -> str:
        """删除武器"""
        weapons = await self._get_weapons(user_id)

        if not weapons:
            return self.reply.render("weapon_list_empty")

        if index < 1 or index > len(weapons):
            return self.reply.render("invalid_index")

        removed = weapons.pop(index - 1)
        await self._save_weapons(user_id, weapons)

        return self.reply.render("weapon_deleted", name=removed.get("name", ""))

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
            if weapon.get("equipped", False):
                return weapon

        return None


# 创建模块实例
weapon_module = WeaponModule()
