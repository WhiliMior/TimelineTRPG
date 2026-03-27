"""
背包模块 - 管理物品/资源
迁移自老项目 Game/Runtime/Inventory/
"""
from typing import Dict, List

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry
from ..adapter.storage import StorageBackend, StorageType


class InventoryModule:
    """
    背包模块
    
    支持的指令格式：
    - .i - 显示背包物品列表
    - .i add <物品名> [数量] - 添加物品
    - .i del <序号> - 删除物品
    - .i clear - 清空背包
    """
    
    def __init__(self):
        self.reply = ReplyManager("inventory")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="i",
            usage="[add|del|clear|cash] [参数]",
            summary="背包管理",
            detail=(
                "- 显示背包内容和状态\n"
                "cash/现金 +/-{数值} (描述) - 记录现金变动\n"
                "cash - 显示当前现金和消费记录\n"
                "{物品名} +/-{数量} (单个重量) - 记录物品变动\n"
                "del {序号}/all - 删除物品或清空背包\n"
                "\n"
                "示例:\n"
                "  i → 显示背包\n"
                "  i add 血药 5 → 添加5个血药\n"
                "  i del 1 → 删除第1个物品"
            ),
        )
    
    async def i(self, ctx: CommandContext) -> bool:
        """
        处理背包命令
        """
        user_id = ctx.sender_id or "default"
        
        if not ctx.args:
            result = await self._list_inventory(user_id)
            ctx.send(result)
            return True
        
        command = ctx.args[0].lower()
        
        if command == 'add':
            if len(ctx.args) < 2:
                response = self.reply.render("need_item_name")
                ctx.send(response)
                return True
            item_name = ctx.args[1]
            quantity = int(ctx.args[2]) if len(ctx.args) > 2 else 1
            result = await self._add_item(user_id, item_name, quantity)
            ctx.send(result)
        
        elif command == 'del':
            if len(ctx.args) < 2:
                response = self.reply.render("need_item_index")
                ctx.send(response)
                return True
            try:
                index = int(ctx.args[1]) - 1
                result = await self._del_item(user_id, index)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("invalid_index")
                ctx.send(response)
        
        elif command == 'clear':
            result = await self._clear_inventory(user_id)
            ctx.send(result)
        
        else:
            result = await self._list_inventory(user_id)
            ctx.send(result)
        
        return True
    
    async def _get_inventory(self, user_id: str) -> List[Dict]:
        return StorageBackend.load(StorageType.USER, user_id, filename="inventory.json", default=[])
    
    async def _save_inventory(self, user_id: str, items: List[Dict]):
        StorageBackend.save(StorageType.USER, user_id, items, filename="inventory.json")
    
    async def _list_inventory(self, user_id: str) -> str:
        items = await self._get_inventory(user_id)
        
        if not items:
            return self.reply.render("empty_inventory")
        
        lines = [self.reply.render("inventory_header")]
        for i, item in enumerate(items):
            name = item.get('name', '未知')
            quantity = item.get('quantity', 1)
            lines.append(f"[{i + 1}] {name} x{quantity}")
        
        return "\n".join(lines)
    
    async def _add_item(self, user_id: str, item_name: str, quantity: int) -> str:
        items = await self._get_inventory(user_id)
        
        # 检查是否已存在
        for item in items:
            if item.get('name') == item_name:
                item['quantity'] = item.get('quantity', 1) + quantity
                await self._save_inventory(user_id, items)
                return self.reply.render("item_added", name=item_name, quantity=quantity)
        
        items.append({'name': item_name, 'quantity': quantity})
        await self._save_inventory(user_id, items)
        return self.reply.render("item_added", name=item_name, quantity=quantity)
    
    async def _del_item(self, user_id: str, index: int) -> str:
        items = await self._get_inventory(user_id)
        
        if not items:
            return self.reply.render("empty_inventory")
        
        if index < 0 or index >= len(items):
            return self.reply.render("invalid_index")
        
        removed = items.pop(index)
        await self._save_inventory(user_id, items)
        return self.reply.render("item_deleted", name=removed.get('name', '未知'))
    
    async def _clear_inventory(self, user_id: str) -> str:
        await self._save_inventory(user_id, [])
        return self.reply.render("inventory_cleared")


inventory_module = InventoryModule()
