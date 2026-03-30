"""
背包模块 - 管理物品/资源
迁移自老项目 Game/Runtime/Inventory/
"""

import re
from typing import Dict, List, Optional
from datetime import datetime

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend, StorageType
from ...infrastructure.config.game_config import game_config


class InventoryModule:
    """
    背包模块

    支持的指令格式：
    - .i - 显示背包内容和状态
    - .i cash +/-{数值} (描述) - 记录现金变动
    - .i cash - 显示当前现金和消费记录
    - .i {物品名} +/-{数量} (单个重量) - 记录物品变动
    - .i {序号}/all - 删除物品或清空背包
    """

    def __init__(self):
        self.reply = ReplyManager("inventory")
        self.system_reply = ReplyManager("system")

    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="i",
            usage="[cash|物品名|del|all] [参数]",
            summary="背包管理",
            detail=(
                "- 显示背包内容和状态\n"
                "cash +/-{数值} (描述) - 记录现金变动\n"
                "cash - 显示当前现金和消费记录\n"
                "{物品名} +/-{数量} (单个重量) - 记录物品变动\n"
                "del {序号}/all - 删除物品或清空背包"
            ),
        )

    async def i(self, ctx: CommandContext) -> bool:
        """
        处理背包命令

        指令格式：
        - .i - 显示背包内容和状态
        - .i cash +/-{数值} (描述) - 记录现金变动
        - .i cash - 显示当前现金和消费记录
        - .i {物品名} +/-{数量} (单个重量) - 记录物品变动
        - .i {序号}/all - 删除物品或清空背包
        """
        user_id = ctx.sender_id or "default"

        if not ctx.args:
            # 显示背包内容和状态
            result = await self._get_inventory_status(user_id)
            ctx.send(result)
            return True

        # 获取原始命令文本（用于解析带空格的物品名）
        raw_args = " ".join(ctx.args)

        # 检查是否是 cash 命令
        if ctx.args[0].lower() == "cash":
            if len(ctx.args) == 1:
                # 显示当前现金和消费记录
                result = await self._show_cash_records(user_id)
                ctx.send(result)
            else:
                # 解析现金变动: +/-数值 (描述)
                cash_arg = ctx.args[1]
                description = " ".join(ctx.args[2:]) if len(ctx.args) > 2 else ""

                # 解析数值和符号
                match = re.match(r"^([+-])(\d+\.?\d*)$", cash_arg)
                if not match:
                    response = self.reply.render("invalid_number")
                    ctx.send(response)
                    return True

                sign = match.group(1)
                amount = float(match.group(2))
                if sign == "-":
                    amount = -amount

                result = await self._update_cash(user_id, amount, description)
                ctx.send(result)
            return True

        # 检查是否是删除命令
        first_arg = ctx.args[0]
        if first_arg.isdigit():
            # 数字序号：删除指定物品
            try:
                index = int(first_arg) - 1
                result = await self._del_item(user_id, index)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("invalid_index")
                ctx.send(response)
            return True
        elif first_arg.lower() == "all":
            # 删除所有物品
            result = await self._clear_inventory(user_id)
            ctx.send(result)
            return True

        # 检查是否是删除命令: del {序号} 或 del all 或 del 1 4 5
        if first_arg.lower() == "del":
            if len(ctx.args) == 1:
                response = self.reply.render("need_item_index")
                ctx.send(response)
                return True

            second_arg = ctx.args[1]
            if second_arg.lower() == "all":
                result = await self._clear_inventory(user_id)
                ctx.send(result)
            else:
                # 支持多个数字输入，如 del 1 4 5
                indices = [int(x) - 1 for x in ctx.args[1:] if x.isdigit()]
                if not indices:
                    response = self.reply.render("invalid_index")
                    ctx.send(response)
                elif len(indices) == 1:
                    result = await self._del_item(user_id, indices[0])
                    ctx.send(result)
                else:
                    result = await self._del_multiple_items(user_id, indices)
                    ctx.send(result)
            return True

        # 检查是否是清空命令: all
        if first_arg.lower() == "all":
            result = await self._clear_inventory(user_id)
            ctx.send(result)
            return True

        # 去掉 "add" 关键字（如果存在）
        # 用户可能输入 .i add 苹果 +2 3
        args_for_parse = ctx.args
        if first_arg.lower() == "add":
            args_for_parse = ctx.args[1:]

        if not args_for_parse:
            response = self.reply.render("need_item_name")
            ctx.send(response)
            return True

        raw_args_for_parse = " ".join(args_for_parse)

        # 解析物品变动: {物品名} +/-{数量} (单个重量)
        # 格式: 物品名 +/-数量 单个重量 或 物品名+/-数量 单个重量
        # 尝试匹配: 物品名 +/-数量 单个重量
        item_match = re.match(
            r"^(.+?)\s*([+-])(\d+\.?\d*)\s+(\d+\.?\d*)$", raw_args_for_parse
        )
        if item_match:
            item_name = item_match.group(1).strip()
            sign = item_match.group(2)
            quantity = float(item_match.group(3))
            weight = float(item_match.group(4))
            if sign == "-":
                quantity = -quantity

            result = await self._update_item(
                user_id, item_name, int(quantity), weight, ctx
            )
            ctx.send(result)
            return True

        # 尝试匹配: 物品名 +/-数量（没有重量）
        item_match = re.match(r"^(.+?)\s*([+-])(\d+\.?\d*)$", raw_args_for_parse)
        if item_match:
            item_name = item_match.group(1).strip()
            sign = item_match.group(2)
            quantity = float(item_match.group(3))
            if sign == "-":
                quantity = -quantity

            result = await self._update_item(
                user_id, item_name, int(quantity), None, ctx
            )
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

    async def _get_inventory_data(self, user_id: str) -> Dict:
        """获取角色背包数据"""
        character = await self._get_active_character(user_id)
        if not character:
            return {"items": [], "cash": 0, "cash_records": []}

        # 如果没有inventory数据，返回空数据
        if "inventory" not in character:
            return {"items": [], "cash": 0, "cash_records": []}

        inventory = character.get("inventory", {})

        # 使用 CharacterReader 计算当前现金（初始现金 + 变动记录）
        from ...infrastructure.character_reader import CharacterReader

        current_cash = CharacterReader.calculate_current_cash(inventory, character)

        return {
            "items": inventory.get("items", []),
            "cash": current_cash,
            "cash_records": inventory.get("cash_records", []),
        }

    async def _initialize_inventory(self, user_id: str, character: Dict) -> bool:
        """
        初始化角色背包数据
        仅在 inventory 不存在时创建，使用 CharacterReader 计算初始现金
        """
        # 如果已经有 inventory 数据，不需要初始化（保留之前的现金变动）
        if "inventory" in character:
            return True

        # 使用 CharacterReader 计算初始现金
        from ...infrastructure.character_reader import CharacterReader

        initial_cash = CharacterReader._calculate_cash(character)

        # 创建初始背包数据
        character["inventory"] = {"items": [], "cash": initial_cash, "cash_records": []}

        # 通过StorageBackend保存
        from ...infrastructure.storage import StorageBackend

        return StorageBackend.update_character(
            user_id, character.get("name"), character
        )

    async def _save_inventory_data(self, user_id: str, inventory_data: Dict) -> bool:
        """保存角色背包数据 - 通过StorageBackend保存到角色inventory字段中"""
        from ...infrastructure.storage import StorageBackend

        character = await self._get_active_character(user_id)
        if not character:
            return False

        # 更新角色的inventory字段（只存储 items 和 cash_records，不存储 cash）
        if "inventory" not in character:
            character["inventory"] = {}

        character["inventory"]["items"] = inventory_data.get("items", [])
        character["inventory"]["cash_records"] = inventory_data.get("cash_records", [])

        # 通过StorageBackend保存整个角色数据
        return StorageBackend.update_character(
            user_id, character.get("name"), character
        )

    async def _get_inventory_status(self, user_id: str) -> str:
        """获取背包状态"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        # 首次调用时初始化背包
        await self._initialize_inventory(user_id, character)

        inventory_data = await self._get_inventory_data(user_id)
        items = inventory_data.get("items", [])
        cash = inventory_data.get("cash", 0)

        # 使用 CharacterReader 获取角色的最大负重和当前负重
        from ...infrastructure.character_reader import CharacterReader

        max_weight = CharacterReader.get_character_full_weight(
            user_id, character.get("name")
        )
        total_weight = CharacterReader.get_character_current_weight(
            user_id, character.get("name")
        )
        if total_weight is None:
            total_weight = 0.0

        lines = [self.reply.render("inventory_header")]

        if items:
            for i, item in enumerate(items):
                name = item.get("name", "未知")
                quantity = item.get("quantity", 1)
                weight = item.get("weight", 0)
                if weight > 0:
                    lines.append(f"[{i + 1}] {name} x{quantity} (负重:{weight})")
                else:
                    lines.append(f"[{i + 1}] {name} x{quantity}")
        else:
            lines.append(self.reply.render("empty_inventory"))

        # 总是显示总负重和现金
        lines.append(f"\n总负重: {total_weight}/{max_weight}")
        lines.append(f"现金: {cash}")

        return "\n".join(lines)

    async def _show_cash_records(self, user_id: str) -> str:
        """显示现金和消费记录"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        # 首次调用时初始化背包
        await self._initialize_inventory(user_id, character)

        inventory_data = await self._get_inventory_data(user_id)
        cash = inventory_data.get("cash", 0)
        cash_records = inventory_data.get("cash_records", [])

        lines = [f"当前现金: {cash}"]

        if cash_records:
            lines.append("\n消费记录:")
            # 显示最近的10条记录
            for record in cash_records[-10:]:
                amount = record.get("amount", 0)
                desc = record.get("description", "")
                time_str = record.get("time", "")[:19]  # 只显示日期时间
                if amount >= 0:
                    lines.append(f"+{amount} {desc} ({time_str})")
                else:
                    lines.append(f"{amount} {desc} ({time_str})")

        return "\n".join(lines)

    async def _update_cash(
        self, user_id: str, amount: float, description: str = ""
    ) -> str:
        """更新现金并记录变动"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        # 首次调用时初始化背包
        await self._initialize_inventory(user_id, character)

        inventory_data = await self._get_inventory_data(user_id)

        # 更新现金（通过添加变动记录实现）
        old_cash = inventory_data.get("cash", 0)
        new_cash = old_cash + amount

        # 添加记录
        record = {
            "amount": amount,
            "description": description,
            "time": datetime.now().isoformat(),
        }
        cash_records = inventory_data.get("cash_records", [])
        cash_records.append(record)
        inventory_data["cash_records"] = cash_records

        # 保存（不存储 cash 字段，只存储 cash_records）
        if await self._save_inventory_data(user_id, inventory_data):
            if amount >= 0:
                return self.reply.render(
                    "cash_added",
                    value=f"+{amount}",
                    old_cash=old_cash,
                    new_cash=new_cash,
                )
            else:
                return self.reply.render(
                    "cash_removed",
                    value=str(amount),
                    old_cash=old_cash,
                    new_cash=new_cash,
                )
        else:
            return self.reply.render("save_failed")

    async def _update_item(
        self,
        user_id: str,
        item_name: str,
        quantity: int,
        weight: float = None,
        ctx: CommandContext = None,
    ) -> str:
        """更新物品（添加或减少）"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        # 首次调用时初始化背包
        await self._initialize_inventory(user_id, character)

        inventory_data = await self._get_inventory_data(user_id)
        items = inventory_data.get("items", [])

        # 使用 game_config 处理重量精度
        weight_value = (
            game_config.round_value(weight, "weight") if weight is not None else None
        )

        # 确定是添加还是减少
        is_removal = quantity < 0

        # 如果有重量参数，自动记录到存储中
        if weight_value is not None and ctx is not None:
            conversation_id = ctx.group_id or ctx.sender_id or user_id
            is_group = ctx.group_id is not None
            from ...infrastructure.storage import StorageBackend

            weights = StorageBackend.load_inventory_weights(conversation_id, is_group)
            weights[item_name] = weight_value
            StorageBackend.save_inventory_weights(conversation_id, weights, is_group)

        # 如果没有重量参数，尝试从存储中自动获取
        if weight_value is None and ctx is not None:
            conversation_id = ctx.group_id or ctx.sender_id or user_id
            is_group = ctx.group_id is not None
            from ...infrastructure.storage import StorageBackend

            weights = StorageBackend.load_inventory_weights(conversation_id, is_group)
            if item_name in weights:
                weight_value = weights[item_name]

        # 查找物品
        found = False
        for item in items:
            if item.get("name") == item_name:
                new_quantity = item.get("quantity", 1) + quantity
                if new_quantity <= 0:
                    # 数量为0或负数，移除物品
                    items.remove(item)
                else:
                    item["quantity"] = new_quantity
                    if weight_value is not None:
                        item["weight"] = weight_value
                found = True
                break

        if not found and quantity > 0:
            # 新增物品
            new_item = {"name": item_name, "quantity": quantity}
            if weight_value is not None:
                new_item["weight"] = weight_value
            items.append(new_item)

        inventory_data["items"] = items

        if await self._save_inventory_data(user_id, inventory_data):
            # 返回正确的消息
            if is_removal:
                return self.reply.render(
                    "item_removed", name=item_name, quantity=abs(quantity)
                )
            else:
                # 如果自动获取了重量，提示用户
                if weight_value is not None and weight is None and ctx is not None:
                    conversation_id = ctx.group_id or ctx.sender_id or user_id
                    is_group = ctx.group_id is not None
                    from ...infrastructure.storage import StorageBackend

                    weights = StorageBackend.load_inventory_weights(
                        conversation_id, is_group
                    )
                    if item_name in weights:
                        return self.reply.render(
                            "item_weight_auto", name=item_name, weight=weight_value
                        )
                return self.reply.render(
                    "item_added", name=item_name, quantity=abs(quantity)
                )
        else:
            return self.reply.render("save_failed")

    async def _del_item(self, user_id: str, index: int) -> str:
        """删除指定索引的物品"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        # 首次调用时初始化背包
        await self._initialize_inventory(user_id, character)

        inventory_data = await self._get_inventory_data(user_id)
        items = inventory_data.get("items", [])

        if not items:
            return self.reply.render("empty_inventory")

        if index < 0 or index >= len(items):
            return self.reply.render("invalid_index")

        removed = items.pop(index)
        inventory_data["items"] = items

        if await self._save_inventory_data(user_id, inventory_data):
            return self.reply.render("item_deleted", name=removed.get("name", "未知"))
        else:
            return self.reply.render("save_failed")

    async def _del_multiple_items(self, user_id: str, indices: List[int]) -> str:
        """删除多个物品"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        # 首次调用时初始化背包
        await self._initialize_inventory(user_id, character)

        inventory_data = await self._get_inventory_data(user_id)
        items = inventory_data.get("items", [])

        if not items:
            return self.reply.render("empty_inventory")

        # 验证序号
        invalid_indices = []
        valid_indices = []

        for idx in indices:
            if 0 <= idx < len(items):
                valid_indices.append(idx)
            else:
                invalid_indices.append(idx + 1)

        if not valid_indices:
            return self.reply.render("invalid_index")

        # 从后往前删除，避免索引偏移
        for idx in sorted(valid_indices, reverse=True):
            items.pop(idx)

        inventory_data["items"] = items

        if await self._save_inventory_data(user_id, inventory_data):
            if invalid_indices:
                return self.reply.render(
                    "item_multi_deleted_partial",
                    valid=len(valid_indices),
                    invalid=len(invalid_indices)
                )
            else:
                return self.reply.render("item_multi_deleted", count=len(valid_indices))
        else:
            return self.reply.render("save_failed")

    async def _clear_inventory(self, user_id: str) -> str:
        """清空背包"""
        character = await self._get_active_character(user_id)
        if not character:
            return self.reply.render("no_character")

        # 首次调用时初始化背包
        await self._initialize_inventory(user_id, character)

        inventory_data = await self._get_inventory_data(user_id)
        inventory_data["items"] = []

        if await self._save_inventory_data(user_id, inventory_data):
            return self.reply.render("inventory_cleared")
        else:
            return self.reply.render("save_failed")


inventory_module = InventoryModule()
