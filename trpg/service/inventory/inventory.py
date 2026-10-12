"""
背包模块 - 管理物品/资源
迁移自老项目 Game/Runtime/Inventory/
"""

import re
from datetime import datetime

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.config.game_config import game_config
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend
from ...infrastructure.text_style import (
    DIVIDER,
    clip_lines,
    item,
    kv,
    signed,
    wrap,
)
from ...infrastructure.text_style import num as _num


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

    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="i",
            usage="[cash|物品名|del|all] [参数]",
            summary="背包管理",
            detail=(
                ".i：查看背包和负重\n"
                ".i cash +/-数值 (描述)：现金变动\n"
                ".i cash：现金和消费记录\n"
                ".i 物品 +/-数量 (单重)：物品变动\n"
                ".i del 序号/all：删除物品"
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

        ctx.send(self.reply.render("unknown_input", input=raw_args_for_parse))
        return True

    async def _get_active_character(self, user_id: str) -> dict | None:
        """获取用户当前激活的角色"""
        from ..character.character import character_module

        return await character_module.get_active_character(user_id)

    async def _get_inventory_data(self, user_id: str) -> dict:
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

    async def _initialize_inventory(self, user_id: str, character: dict) -> bool:
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

        return StorageBackend.update_character(
            user_id, character.get("name"), character
        )

    async def _save_inventory_data(self, user_id: str, inventory_data: dict) -> bool:
        """保存角色背包数据 - 通过StorageBackend保存到角色inventory字段中"""

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

        lines = [
            self.reply.render(
                "inventory_header", name=character.get("name", ""), count=len(items)
            )
        ]

        if items:
            entries = []
            for i, entry in enumerate(items):
                text = f"{entry.get('name', '未知')}×{entry.get('quantity', 1)}"
                weight = entry.get("weight", 0)
                if weight > 0:
                    text += f" 负重{_num(weight)}"
                entries.append(item(i + 1, text))
            lines.extend(
                clip_lines(entries, more_hint=self.reply.render("list_more_hint"))
            )
        else:
            lines.append(self.reply.render("empty_inventory"))

        lines.append(DIVIDER)
        lines.append(kv("负重", f"{_num(total_weight)}/{_num(max_weight)}"))
        lines.append(kv("现金", _num(cash)))

        return wrap("\n".join(lines))

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

        lines = [self.reply.render("cash_balance", balance=_num(cash))]

        if cash_records:
            lines.append(self.reply.render("cash_records_title"))
            for record in cash_records[-10:]:
                # ISO 时间只保留「月-日 时:分」
                time_str = record.get("time", "")[5:16].replace("T", " ")
                parts = [
                    signed(_num(record.get("amount", 0))),
                    record.get("description", ""),
                    time_str,
                ]
                lines.append(" ".join(p for p in parts if p))
        else:
            lines.append(self.reply.render("no_cash_records"))

        return wrap("\n".join(lines))

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
            return self.reply.render(
                "cash_changed",
                value=signed(_num(amount)),
                old_cash=_num(old_cash),
                new_cash=_num(new_cash),
                description=f" {description}" if description else "",
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
        weight_auto_filled = False
        if ctx is not None:
            conversation_id, is_group = ctx.conversation_id, ctx.is_group
            weights = StorageBackend.load_inventory_weights(conversation_id, is_group)
            if weight_value is not None:
                weights[item_name] = weight_value
                StorageBackend.save_inventory_weights(
                    conversation_id, weights, is_group
                )
            elif item_name in weights:
                weight_value = weights[item_name]
                weight_auto_filled = True

        # 查找物品
        found = False
        remaining = max(quantity, 0)
        for entry in items:
            if entry.get("name") == item_name:
                new_quantity = entry.get("quantity", 1) + quantity
                if new_quantity <= 0:
                    # 数量为0或负数，移除物品
                    items.remove(entry)
                    remaining = 0
                else:
                    entry["quantity"] = new_quantity
                    remaining = new_quantity
                    if weight_value is not None:
                        entry["weight"] = weight_value
                found = True
                break

        if is_removal and not found:
            return self.reply.render("item_not_found", name=item_name)

        if not found and quantity > 0:
            # 新增物品
            new_item = {"name": item_name, "quantity": quantity}
            if weight_value is not None:
                new_item["weight"] = weight_value
            items.append(new_item)

        inventory_data["items"] = items

        if not await self._save_inventory_data(user_id, inventory_data):
            return self.reply.render("save_failed")

        key = "item_removed" if is_removal else "item_added"
        result = self.reply.render(
            key, name=item_name, quantity=abs(quantity), remaining=remaining
        )
        if weight_auto_filled and not is_removal:
            result += "\n" + self.reply.render(
                "item_weight_auto", weight=_num(weight_value)
            )
        return result

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

    async def _del_multiple_items(self, user_id: str, indices: list[int]) -> str:
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
                    invalid=len(invalid_indices),
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
