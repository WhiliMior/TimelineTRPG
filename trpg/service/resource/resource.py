"""
资源记录模块 - 记录资源变化
迁移自老项目 Game/Runtime/Resource/
"""

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.config.game_config import game_config
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend


class ResourceRecordModule:
    """
    资源记录模块

    支持的指令格式：
    - .rc {hp/mp} {变化值} (变化类型/f) - 修改资源
    - .rc 护盾/s {变化值} (覆盖范围) (持续时间) - 添加护盾
    - .rc reset - 重置资源到最大值
    - .rc show - 显示当前资源状态
    """

    # 资源类型映射
    RESOURCE_TYPE_MAPPING = {
        "hp": "hp",
        "体力": "hp",
        "mp": "mp",
        "意志": "mp",
        "s": "shield",
        "护盾": "shield",
    }

    # 覆盖类型映射
    COVERAGE_TYPE_MAPPING = {
        "hp": "hp",
        "体力": "hp",
        "physical": "hp",
        "物理": "hp",
        "mp": "mp",
        "意志": "mp",
        "mental": "mp",
        "精神": "mp",
        "all": "all",
        "所有": "all",
    }

    def __init__(self):
        self.reply = ReplyManager("resource_record")
        self.system_reply = ReplyManager("system")

    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="rc",
            usage="[hp/mp|护盾|reset|show] [变化值] [变化类型|f]",
            summary="资源记录",
            detail=(
                "- 显示当前资源状态\n"
                "{hp/mp} {变化值} (持续时间) (f) - 修改资源\n"
                "护盾/s {变化值} (覆盖范围) (持续时间) - 添加护盾\n"
                "reset - 重置资源到最大值并清除护盾\n"
                "show - 显示当前资源状态\n"
                "\n"
                "f 标记: 允许修改超过上限/下限"
            ),
        )

    async def rc(self, ctx: CommandContext) -> bool:
        """
        处理资源记录命令

        指令格式：
        - .rc {hp/mp} {变化值} (持续时间) (f) - 修改资源
        - .rc 护盾/s {变化值} (覆盖范围) (持续时间) - 添加护盾
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
        if command == "reset":
            result = await self._reset_resources(user_id)
            ctx.send(result)
            return True

        # 显示资源状态
        if command == "show":
            result = await self._get_resource_status(user_id)
            ctx.send(result)
            return True

        # 检查是否是资源类型 (hp/mp/体力/意志)
        if command in self.RESOURCE_TYPE_MAPPING:
            resource_type = self.RESOURCE_TYPE_MAPPING[command]
            if resource_type == "shield":
                # 护盾: .rc 护盾/s {变化值} (覆盖范围) (持续时间) (f)
                conversation_id = ctx.group_id or ctx.session_id or user_id
                result = await self._handle_shield(
                    user_id, conversation_id, ctx.args[1:]
                )
                ctx.send(result)
            else:
                # HP/MP: .rc hp/mp {变化值} (持续时间) (f)
                result = await self._handle_resource(
                    user_id, resource_type, ctx.args[1:]
                )
                ctx.send(result)
            return True

        # 检查是否是 s 或 护盾
        if command == "s" or command == "护盾":
            conversation_id = ctx.group_id or ctx.session_id or user_id
            result = await self._handle_shield(user_id, conversation_id, ctx.args[1:])
            ctx.send(result)
            return True

        # 无效命令
        response = self.system_reply.render("command_not_found", command=ctx.command)
        ctx.send(response)
        return True

    async def _get_active_character(self, user_id: str) -> dict | None:
        """获取用户当前激活的角色"""
        from ..character.character import character_module

        return await character_module.get_active_character(user_id)

    async def _get_resource_data(self, user_id: str, initialize: bool = True) -> dict:
        """获取角色资源数据"""
        character = await self._get_active_character(user_id)
        if not character:
            return {"current_hp": 0, "current_mp": 0, "shields": []}

        # 直接返回角色的resources字典引用，确保修改能保存
        if "resources" not in character:
            if initialize:
                # 初始化资源
                resources = await self._initialize_resources(user_id)
                return resources
            else:
                return {"current_hp": 0, "current_mp": 0, "shields": []}

        return character["resources"]

    async def _initialize_resources(self, user_id: str) -> dict:
        """
        初始化角色资源数据
        使用角色的最终属性（经过buff修正）作为最大值
        """
        character = await self._get_active_character(user_id)
        if not character:
            return {"current_hp": 0, "current_mp": 0, "shields": []}

        # 使用CharacterReader获取最终属性（包含buff修正）
        from ...infrastructure.character_reader import CharacterReader

        final_attributes = CharacterReader.get_character_final_attributes(user_id)

        if not final_attributes:
            return {"current_hp": 0, "current_mp": 0, "shields": []}

        # 体质决定体力最大值，意志决定意志最大值
        max_hp = final_attributes.get("体质", 0)
        max_mp = final_attributes.get("意志", 0)

        # 初始化资源
        resources = {"current_hp": max_hp, "current_mp": max_mp, "shields": []}

        # 保存到角色数据中
        character["resources"] = resources
        StorageBackend.update_character(user_id, character.get("name"), character)

        return resources

    async def _save_resource_data(self, user_id: str, resources: dict) -> bool:
        """保存角色资源数据 - 通过StorageBackend保存到角色resources字段中"""
        character = await self._get_active_character(user_id)
        if not character:
            return False

        # 更新角色的resources字段
        character["resources"] = resources

        # 通过StorageBackend保存整个角色数据
        return StorageBackend.update_character(
            user_id, character.get("name"), character
        )

    async def _get_max_resources(
        self, user_id: str
    ) -> tuple[float | None, float | None]:
        """获取角色的HP和MP最大值（使用最终属性，经过buff修正）"""
        # 使用CharacterReader获取最终属性（包含buff修正）
        from ...infrastructure.character_reader import CharacterReader

        final_attributes = CharacterReader.get_character_final_attributes(user_id)

        if not final_attributes:
            return None, None

        # 体质决定体力最大值，意志决定意志最大值
        max_hp = final_attributes.get("体质")
        max_mp = final_attributes.get("意志")

        return max_hp, max_mp

    def _parse_value_with_percentage(
        self, value_str: str, max_value: float | None
    ) -> float | None:
        """解析数值，支持百分比格式"""
        value_str = value_str.strip()

        if value_str.endswith("%"):
            if max_value is None:
                return None
            try:
                percentage = float(value_str[:-1])
                return game_config.round_value(
                    max_value * percentage / 100.0, "resource"
                )
            except ValueError:
                return None
        else:
            try:
                return float(value_str)
            except ValueError:
                return None

    def _parse_duration(self, duration: str) -> float:
        """解析持续时间，返回数值用于比较"""
        if not duration or duration == "0t" or duration == "0":
            return float("inf")  # 永久护盾排最后
        try:
            return float(duration[:-1]) if duration.endswith("t") else float(duration)
        except (ValueError, IndexError):
            return float("inf")

    async def _apply_shield_protection(
        self, user_id: str, resources: dict, resource_type: str, value_change: float
    ) -> tuple[float, str]:
        """
        应用护盾保护，返回实际的资源变化值和操作结果信息

        护盾消耗优先级：
        1. 同类型护盾优先于全类型护盾（如：体力伤害优先消耗体力护盾）
        2. 同类型/同覆盖范围：持续时间短的优先扣除
        3. 相同持续时间：更早创建的优先扣除
        """
        if value_change >= 0:
            # 正值不需要护盾保护
            return value_change, ""

        shields = resources.get("shields", [])

        if not shields:
            # 没有护盾，直接返回原变化值
            return value_change, ""

        damage_to_absorb = abs(value_change)  # 需要吸收的伤害量
        remaining_damage = damage_to_absorb
        shield_info = []

        # 根据资源类型确定特定类型
        specific_coverage_types = []
        if resource_type == "hp":
            specific_coverage_types = ["hp", "体力"]
        elif resource_type == "mp":
            specific_coverage_types = ["mp", "意志"]

        # 分类护盾并添加排序优先级
        # 优先级：同类型(0) > 全类型(1)，持续时间短 > 持续时间长，创建时间早 > 创建时间晚
        def get_priority(shield):
            coverage = shield.get("coverage_type", "all")
            # 特定类型优先：特定类型=0，全类型=1
            is_specific = 0 if coverage in specific_coverage_types else 1
            duration = self._parse_duration(shield.get("duration", "0t"))
            created_at = shield.get("created_at", 0)
            return (is_specific, duration, created_at)

        # 按优先级排序：同类型优先，持续时间短优先，创建时间早优先
        sorted_shields = sorted(shields, key=get_priority)

        # 记录每种类型护盾的总消耗和调整前后值
        shield_damage_before = damage_to_absorb  # 承伤前

        # 处理护盾消耗
        for shield in sorted_shields:
            if remaining_damage <= 0:
                break

            shield_absorb = min(shield["value"], remaining_damage)
            shield_before = shield.get("value", 0)
            shield["value"] = game_config.round_value(
                shield["value"] - shield_absorb, "resource"
            )
            shield_after = shield["value"]
            remaining_damage -= shield_absorb

            coverage_name = shield.get("coverage_type", "all")
            if coverage_name in ["all", "所有"]:
                shield_info.append(
                    f"全类型护盾: {game_config.format_value(shield_absorb, 'resource')} (调整: {game_config.format_value(shield_before, 'resource')}→{game_config.format_value(shield_after, 'resource')})"
                )
            else:
                shield_info.append(
                    f"{coverage_name}护盾: {game_config.format_value(shield_absorb, 'resource')} (调整: {game_config.format_value(shield_before, 'resource')}→{game_config.format_value(shield_after, 'resource')})"
                )

        # 移除值为0的护盾
        resources["shields"] = [
            shield for shield in sorted_shields if shield.get("value", 0) > 0
        ]

        # 返回剩余伤害（负值）
        actual_change = -remaining_damage

        # 承伤量（承伤前→承伤后）
        damage_after_shield = remaining_damage

        if shield_info:
            # 每种护盾分开显示，换行
            shield_msg = "\n".join(shield_info)
            return (
                actual_change,
                f"\n承伤: {game_config.format_value(damage_to_absorb, 'resource')}→{game_config.format_value(damage_after_shield, 'resource')}\n护盾保护:\n{shield_msg}",
            )
        else:
            return value_change, ""

    async def _apply_modifiers(
        self,
        user_id: str,
        resource_type: str,
        value_change: float,
        change_type: str | None = None,
    ) -> tuple[float, str]:
        """
        应用资源修饰到资源变化值上

        修饰范围规则：
        - +hp/+mp/+all : 仅对资源增加时生效（增伤/增疗）
        - -hp/-mp/-all : 仅对资源减少时生效（减伤/减疗）
        - +和-范围不互通

        数值类型（优先级顺序）：
        1. 百分比 (如 15%): 先结算百分比修饰
        2. 纯数字 (如 15): 固定减/固定增，后结算
        3. 防御值 (如 15d): 转换为百分比后结算

        修饰类型匹配：
        - rc中的变化类型需匹配dr中的修饰类型
        - 省略或为空时，应用所有类型（默认"所有"）
        - "所有"类型在任何情况下都生效

        Args:
            user_id: 用户ID
            resource_type: 资源类型 ('hp' 或 'mp')
            value_change: 原始变化值（正值为增加，负值为减少）
            change_type: 变化类型（物理、魔法、bp等），用于匹配修饰类型

        Returns:
            (应用修饰后的变化值, 修饰信息字符串)
        """
        character = await self._get_active_character(user_id)
        if not character:
            return value_change, ""

        modifiers = character.get("resource_modifiers", [])
        if not modifiers:
            return value_change, ""

        # 变化类型直接使用原始字符串比较（用户输入什么就匹配什么）
        normalized_change_type = change_type.strip() if change_type else None

        if normalized_change_type and normalized_change_type.lower() in [
            "f",
            "F",
            "bypass",
        ]:
            # bypass 完全绕过所有修饰
            return value_change, ""

        # 确定操作方向：正值为增加(+)，负值为减少(-)
        is_increase = value_change > 0
        sign = "+" if is_increase else "-"

        # 根据资源类型和操作方向确定目标范围
        # +范围只对增加资源生效，-范围只对减少资源生效
        if resource_type == "hp":
            if is_increase:
                target_ranges = ["+hp", "+all"]
            else:
                target_ranges = ["-hp", "-all"]
        else:  # mp
            if is_increase:
                target_ranges = ["+mp", "+all"]
            else:
                target_ranges = ["-mp", "-all"]

        # 筛选适用的修饰
        # 1. 范围匹配
        # 2. 修饰类型匹配（变化类型匹配修饰类型，或者修饰类型为"所有"/空）
        applicable_modifiers = []
        for mod in modifiers:
            mod_range = mod.get("range", "")
            if mod_range not in target_ranges:
                continue

            # 检查修饰类型匹配 - 直接比较原始字符串
            raw_mod_type = mod.get("type", "所有")
            # 空字符串、"所有"、"通用"都视为通配符类型
            if not raw_mod_type or raw_mod_type in ["所有", "通用"]:
                # 通配符类型，匹配任何变化类型
                if normalized_change_type is None:
                    applicable_modifiers.append(mod)
                else:
                    continue  # 通配符对具体类型不做匹配，继续
            else:
                # 精确匹配：用户输入什么就匹配什么
                if normalized_change_type is None:
                    # 没有指定变化类型，不应用具体类型的修饰
                    continue
                elif raw_mod_type == normalized_change_type:
                    applicable_modifiers.append(mod)

        if not applicable_modifiers:
            return value_change, ""

        # 获取角色数据用于计算防御值
        character_data = character.get("data", {})

        # 分离百分比修饰和固定值修饰
        percentage_modifiers = []  # 百分比修饰
        fixed_modifiers = []  # 固定值修饰

        for mod in applicable_modifiers:
            value_data = mod.get("value", {})
            if isinstance(value_data, dict):
                value_type = value_data.get("type", "percentage")
            else:
                value_type = "percentage"

            if value_type == "fixed":
                fixed_modifiers.append(mod)
            else:
                percentage_modifiers.append(mod)

        # 计算最终修饰值
        result_value = abs(value_change)  # 使用绝对值计算
        original_abs_value = result_value  # 记录原始绝对值
        modifier_details = []
        calculation_steps = []  # 计算过程步骤

        # 1. 先应用百分比修饰（包括防御值）
        for mod in percentage_modifiers:
            mod_value_data = mod.get("value", {})
            mod_value = self._calculate_modifier_value_from_raw(
                mod_value_data, character_data, mod.get("range", "")
            )

            mod_source = mod.get("source", "")
            mod_range = mod.get("range", "")

            # 获取原始值用于显示
            raw_display = mod_value_data.get("raw", "0")
            value_type = mod_value_data.get("type", "percentage")
            if value_type == "defense":
                display_val = f"{raw_display}({mod_value * 100:.0f}%)"
            else:
                display_val = f"{mod_value * 100:.0f}%"

            if mod_range.startswith("+"):
                # 增益：增加百分比
                before_value = result_value
                increase = before_value * mod_value
                result_value = result_value * (1 + mod_value)
                modifier_details.append(f"{mod_source}: +{display_val}")
                calculation_steps.append(
                    f"{mod_source}: {before_value:.1f} + {increase:.1f}({display_val}) = {result_value:.1f}"
                )
            else:
                # 减伤：减少百分比
                before_value = result_value
                reduction = before_value * mod_value
                result_value = result_value * (1 - mod_value)
                modifier_details.append(f"{mod_source}: -{display_val}")
                calculation_steps.append(
                    f"{mod_source}: {before_value:.1f} - {reduction:.1f}({display_val}) = {result_value:.1f}"
                )

        # 2. 再应用固定值修饰
        for mod in fixed_modifiers:
            mod_value_data = mod.get("value", {})
            raw = mod_value_data.get("raw", "0")
            try:
                mod_value = float(raw)
            except ValueError:
                mod_value = 0

            mod_source = mod.get("source", "")
            mod_range = mod.get("range", "")

            if mod_range.startswith("+"):
                # 增益：增加固定值
                before_value = result_value
                result_value = result_value + mod_value
                modifier_details.append(f"{mod_source}: +{mod_value:.1f}")
                calculation_steps.append(
                    f"{mod_source}: {before_value:.1f} + {mod_value:.1f} = {result_value:.1f}"
                )
            else:
                # 减伤：减少固定值
                before_value = result_value
                result_value = result_value - mod_value
                modifier_details.append(f"{mod_source}: -{mod_value:.1f}")
                calculation_steps.append(
                    f"{mod_source}: {before_value:.1f} - {mod_value:.1f} = {result_value:.1f}"
                )

        # 恢复原始符号
        final_value = result_value if is_increase else -result_value

        # 格式化修饰信息
        modifier_info = ""
        if modifier_details:
            # 计算总变化
            total_change = abs(final_value) - original_abs_value
            change_sign = "+" if total_change > 0 else ""

            # 简化的计算过程
            if calculation_steps:
                calc_text = " → ".join(calculation_steps)
                modifier_info = f" (修正: {original_abs_value:.1f}{change_sign}{total_change:.1f} = {abs(final_value):.1f})\n  {calc_text}"
            else:
                modifier_info = f" (修正: {' '.join(modifier_details)})"

        return final_value, modifier_info

    def _calculate_modifier_value_from_raw(
        self, value_data: dict, character_data: dict, range_val: str
    ) -> float:
        """
        根据保存的原始值计算实际的修饰数值
        """
        raw = value_data.get("raw", "0")
        value_type = value_data.get("type", "percentage")

        if value_type == "percentage":
            try:
                return float(raw.rstrip("%")) / 100.0
            except ValueError:
                return 0.0

        elif value_type == "defense":
            try:
                defense = float(raw.rstrip("dD"))
                level = character_data.get("等级", 1)

                if range_val.startswith("-"):
                    return defense / (defense + (level * 10))
                else:
                    return defense / (level * 10)
            except ValueError:
                return 0.0

        else:  # fixed
            try:
                return float(raw)
            except ValueError:
                return 0.0

    async def _handle_resource(
        self, user_id: str, resource_type: str, args: list[str]
    ) -> str:
        """处理HP/MP资源变化"""
        if len(args) < 1:
            return self.reply.render("need_params")

        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        # 获取最大值
        max_hp, max_mp = await self._get_max_resources(user_id)
        max_value = max_hp if resource_type == "hp" else max_mp

        if max_value is None:
            attr_name = "体质" if resource_type == "hp" else "意志"
            return self.reply.render("no_attribute_for_resource", attribute=attr_name)

        # 解析变化值
        value_str = args[0]
        value_change = self._parse_value_with_percentage(value_str, max_value)

        if value_change is None:
            return self.reply.render("invalid_value")

        # 解析变化类型参数（第二个参数，可能是物理、魔法、f等）
        # 格式: .rc hp +10 物理  或  .rc hp -15 f
        change_type = None
        if len(args) >= 2:
            potential_type = args[1].lower()
            if potential_type not in ["f", "F"]:
                change_type = potential_type

        # 应用资源修饰（对正值和负值都应用，只是范围不同）
        original_change = value_change
        if resource_type in ["hp", "mp"]:
            value_change, modifier_info = await self._apply_modifiers(
                user_id, resource_type, value_change, change_type
            )
        else:
            modifier_info = ""

        # 检查是否有f标记（允许溢出）
        allow_overflow = "f" in [arg.lower() for arg in args[1:]]

        # 获取当前值
        resources = await self._get_resource_data(user_id)
        current_attr = f"current_{resource_type}"
        current_value = resources.get(current_attr, 0)

        # 应用护盾保护（仅对负值，即减少操作）
        original_change = value_change
        if resource_type in ["hp", "mp"] and value_change < 0:
            value_change, shield_info = await self._apply_shield_protection(
                user_id, resources, resource_type, value_change
            )
        else:
            shield_info = ""

        # 计算新值
        new_value = current_value + value_change

        # 验证范围（除非允许溢出）
        overflow_msg = ""
        if not allow_overflow:
            if new_value < 0:
                new_value = 0
            elif new_value > max_value:
                new_value = max_value

        # 更新资源
        resources[current_attr] = new_value

        if await self._save_resource_data(user_id, resources):
            # 格式化显示：调整前值→调整后值/上限
            attr_name = "HP" if resource_type == "hp" else "MP"

            # 使用统一精确度格式化
            display = f"{game_config.format_value(current_value, 'resource')}→{game_config.format_value(new_value, 'resource')}/{game_config.format_value(max_value, 'resource')}"

            # 添加资源修饰信息
            if modifier_info:
                display += modifier_info

            # 添加护盾保护信息
            if shield_info:
                display += shield_info

            if allow_overflow:
                display += " (已启用溢出模式)"

            if resource_type == "hp":
                return self.reply.render("hp_changed", change="", value=display)
            else:
                return self.reply.render("mp_changed", change="", value=display)
        else:
            return self.reply.render("save_failed")

    async def _handle_shield(
        self, user_id: str, conversation_id: str, args: list[str]
    ) -> str:
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

        # 智能解析覆盖类型和持续时间
        # 格式: .rc s <值> [覆盖类型|持续时间] [持续时间|覆盖类型] [覆盖类型]
        # 示例: rc s 10       -> 值=10, 覆盖=all, 持续=0
        #       rc s 10 all   -> 值=10, 覆盖=all, 持续=0
        #       rc s 10 5t    -> 值=10, 覆盖=all, 持续=5t
        #       rc s 10 5     -> 值=10, 覆盖=all, 持续=5t
        #       rc s 10 all 5t-> 值=10, 覆盖=all, 持续=5t
        #       rc s 10 5t 物理-> 值=10, 覆盖=物理, 持续=5t
        #       rc s 10 物理 5t-> 值=10, 覆盖=物理, 持续=5t
        coverage_type = "all"
        duration = "0t"

        def is_duration(s: str) -> bool:
            """检查字符串是否为持续时间格式"""
            if not s:
                return False
            # 纯数字 或 以t结尾的数字 (如 5t)
            s_lower = s.lower()
            if s_lower.isdigit():
                return True
            if s_lower.endswith("t") and s_lower[:-1].isdigit():
                return True
            return False

        def is_coverage_type(s: str) -> bool:
            """检查字符串是否为覆盖类型"""
            return s.lower() in self.COVERAGE_TYPE_MAPPING

        # 分析 args[1] 的类型
        if len(args) > 1:
            arg1 = args[1]
            if is_coverage_type(arg1):
                # args[1] 是覆盖类型
                coverage_type = self.COVERAGE_TYPE_MAPPING[arg1.lower()]
                if len(args) > 2 and is_duration(args[2]):
                    duration = args[2]
            elif is_duration(arg1):
                # args[1] 是持续时间
                duration = arg1
                if len(args) > 2 and is_coverage_type(args[2]):
                    coverage_type = self.COVERAGE_TYPE_MAPPING[args[2].lower()]
            else:
                # 未知参数，视为无效
                return self.reply.render("invalid_value")

        # 创建护盾
        resources = await self._get_resource_data(user_id)

        # 获取添加前的该类型护盾总值
        shields = resources.get("shields", [])
        shields_before = sum(
            s.get("value", 0)
            for s in shields
            if s.get("coverage_type") == coverage_type
        )

        # 使用 ISO 格式的时间戳作为唯一标识
        from datetime import datetime

        shield_created_at = datetime.now().isoformat()

        shield = {
            "value": shield_value,
            "coverage_type": coverage_type,
            "duration": duration,
            "created_at": shield_created_at,
        }

        shields = resources.get("shields", [])
        shields.append(shield)
        resources["shields"] = shields

        # 如果有持续时间，调度护盾到期事件
        if duration and duration != "0t" and duration != "0":
            await self._schedule_shield_event(
                conversation_id,
                user_id,
                shield_created_at,
                duration,
                coverage_type,
                shield_value,
            )

        if await self._save_resource_data(user_id, resources):
            # 计算添加后的该类型护盾总值
            shields_after = shields_before + shield_value

            # 获取覆盖类型的中文名称
            coverage_name = coverage_type
            if coverage_type == "all":
                coverage_name = "全类型"
            elif coverage_type == "hp":
                coverage_name = "体力"
            elif coverage_type == "mp":
                coverage_name = "意志"

            # 显示格式：先前值→添加后总值
            display = f"{game_config.format_value(shields_before, 'resource')}→{game_config.format_value(shields_after, 'resource')}"

            return self.reply.render("shield_added", value=display, type=coverage_name)
        else:
            return self.reply.render("save_failed")

    async def _get_resource_status(self, user_id: str) -> str:
        """获取资源状态"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        resources = await self._get_resource_data(user_id)
        max_hp, max_mp = await self._get_max_resources(user_id)

        current_hp = resources.get("current_hp", 0)
        current_mp = resources.get("current_mp", 0)
        shields = resources.get("shields", [])

        # 构建状态信息
        lines = []

        # HP
        if max_hp is not None:
            lines.append(
                f"体力：{game_config.format_value(current_hp, 'resource')}/{game_config.format_value(max_hp, 'resource')}"
            )
        else:
            lines.append(
                f"体力：{game_config.format_value(current_hp, 'resource')}/未知"
            )

        # MP
        if max_mp is not None:
            lines.append(
                f"意志：{game_config.format_value(current_mp, 'resource')}/{game_config.format_value(max_mp, 'resource')}"
            )
        else:
            lines.append(
                f"意志：{game_config.format_value(current_mp, 'resource')}/未知"
            )

        # 护盾
        if shields:
            lines.append("")
            lines.append("护盾：")

            # 统计不同类型护盾的总值
            hp_shield = 0
            mp_shield = 0
            all_shield = 0

            for shield in shields:
                cov = shield.get("coverage_type", "all")
                val = shield.get("value", 0)
                if cov in ["hp", "体力"]:
                    hp_shield += val
                elif cov in ["mp", "意志"]:
                    mp_shield += val
                elif cov in ["all", "所有"]:
                    all_shield += val

            if hp_shield > 0:
                lines.append(
                    f"体力类型： {game_config.format_value(hp_shield, 'resource')}"
                )
            if mp_shield > 0:
                lines.append(
                    f"意志类型：{game_config.format_value(mp_shield, 'resource')}"
                )
            if all_shield > 0:
                lines.append(
                    f"全类型：{game_config.format_value(all_shield, 'resource')}"
                )
        else:
            lines.append("护盾：无")

        return self.reply.render(
            "resource_show",
            hp=lines[0],
            mp=lines[1],
            shield="\n".join(lines[2:]) if len(lines) > 2 else "无",
        )

    async def _reset_resources(self, user_id: str) -> str:
        """重置资源到最大值"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        max_hp, max_mp = await self._get_max_resources(user_id)

        if max_hp is None:
            return self.reply.render("no_constitution_attribute")

        if max_mp is None:
            return self.reply.render("no_willpower_attribute")

        # 重置资源
        resources = {"current_hp": max_hp, "current_mp": max_mp, "shields": []}

        if await self._save_resource_data(user_id, resources):
            return self.reply.render("resource_reset")
        else:
            return self.reply.render("save_failed")

    async def _schedule_shield_event(
        self,
        conversation_id: str,
        user_id: str,
        shield_created_at: str,
        duration: str,
        coverage_type: str,
        shield_value: float,
    ):
        """
        调度护盾到期事件
        """
        # 使用 infrastructure scheduler 避免循环引用
        from ...infrastructure.scheduler import schedule_event

        # 获取角色名
        character = await self._get_active_character(user_id)

        if not character:
            return
        character_name = character.get("name", "未知角色")

        # 确定模式
        mode = (
            "time_based"
            if (isinstance(duration, str) and duration.endswith("t"))
            else "count_based"
        )
        duration_value = (
            float(duration[:-1])
            if (isinstance(duration, str) and duration.endswith("t"))
            else float(duration)
        )

        # 构建描述
        action_desc = f"{character_name} {coverage_type}护盾 {shield_value}"
        callback_msg = f"{character_name} {coverage_type}护盾 {shield_value} 到期"

        # 调用 scheduler 调度事件
        schedule_event(
            conversation_id=conversation_id,
            user_id=user_id,
            character_name=character_name,
            action_description=action_desc,
            duration_or_count=duration_value,
            callback_path="trpg.service.resource.resource.remove_expired_shield",
            callback_args={"user_id": user_id, "shield_created_at": shield_created_at},
            callback_message=callback_msg,
            mode=mode,
            event_type="shield",
        )


async def remove_expired_shield(user_id: str, shield_created_at: str) -> bool:
    """
    模块级函数，用于移除到期的护盾
    由战斗系统在定时事件触发时调用

    infrastructure 层会统一处理事件循环
    """
    from ..character.character import character_module

    character = await character_module.get_active_character(user_id)
    if not character:
        return False

    resources = character.get("resources", {})
    shields = resources.get("shields", [])

    if not shields:
        return False

    # 查找并移除指定 created_at 的护盾
    original_count = len(shields)
    shields = [s for s in shields if s.get("created_at") != shield_created_at]

    if len(shields) < original_count:
        resources["shields"] = shields

        # 保存角色数据
        characters = await character_module._get_user_characters(user_id)
        for i, char in enumerate(characters):
            if char.get("name") == character.get("name"):
                characters[i] = character
                break

        await character_module._save_characters(user_id, characters)
        return True

    return False


resource_record_module = ResourceRecordModule()
