"""
资源记录模块 - 记录资源变化
迁移自老项目 Game/Runtime/Resource/
"""
from typing import Dict, List
from datetime import datetime

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry
from ..adapter.storage import StorageBackend, StorageType


class ResourceRecordModule:
    """
    资源记录模块
    
    支持的指令格式：
    - .rc - 显示资源记录
    - .rc add <资源名> <数值> - 添加资源
    - .rc set <资源名> <数值> - 设置资源值
    - .rc del <资源名> - 删除资源记录
    """
    
    def __init__(self):
        self.reply = ReplyManager("resource_record")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="rc",
            usage="[hp/mp|护盾] [变化值] [持续时间] [f]",
            summary="资源记录",
            detail=(
                "{hp/mp} {变化值} (持续时间) (f) - 修改资源，f标记允许修改超过上限\n"
                "护盾/s {变化值} (覆盖范围) (持续时间) (f) - 修改护盾资源\n"
                "reset - 重置资源到最大值并清除护盾\n"
                "show - 显示当前资源状态\n"
                "\n"
                "示例:\n"
                "  rc hp +10 → hp增加10\n"
                "  rc hp -20 → hp减少20\n"
                "  rc s +5 → 护盾增加5\n"
                "  rc reset → 重置资源"
            ),
        )
    
    async def rc(self, ctx: CommandContext) -> bool:
        user_id = ctx.sender_id or "default"
        
        if not ctx.args:
            result = self._list_resources(user_id)
            ctx.send(result)
            return True
        
        command = ctx.args[0].lower()
        
        if command == 'add':
            if len(ctx.args) < 3:
                response = self.reply.render("need_params")
                ctx.send(response)
                return True
            name = ctx.args[1]
            try:
                value = int(ctx.args[2])
                result = self._add_resource(user_id, name, value)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("invalid_value")
                ctx.send(response)
        
        elif command == 'set':
            if len(ctx.args) < 3:
                response = self.reply.render("need_params")
                ctx.send(response)
                return True
            name = ctx.args[1]
            try:
                value = int(ctx.args[2])
                result = self._set_resource(user_id, name, value)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("invalid_value")
                ctx.send(response)
        
        elif command == 'del':
            if len(ctx.args) < 2:
                response = self.reply.render("need_resource_name")
                ctx.send(response)
                return True
            name = ctx.args[1]
            result = self._del_resource(user_id, name)
            ctx.send(result)
        
        else:
            result = self._list_resources(user_id)
            ctx.send(result)
        
        return True
    
    def _get_resources(self, user_id: str) -> Dict:
        return StorageBackend.load_resources(user_id)
    
    def _save_resources(self, user_id: str, resources: Dict):
        StorageBackend.save_resources(user_id, resources)
    
    def _list_resources(self, user_id: str) -> str:
        resources = self._get_resources(user_id)
        
        if not resources:
            return self.reply.render("no_resources")
        
        lines = [self.reply.render("resource_header")]
        for name, data in resources.items():
            value = data.get('value', 0)
            lines.append(f"{name}: {value}")
        
        return "\n".join(lines)
    
    def _add_resource(self, user_id: str, name: str, value: int) -> str:
        resources = self._get_resources(user_id)
        
        if name in resources:
            resources[name]['value'] = resources[name].get('value', 0) + value
        else:
            resources[name] = {'value': value, 'created_at': datetime.now().isoformat()}
        
        self._save_resources(user_id, resources)
        return self.reply.render("resource_added", name=name, value=value)
    
    def _set_resource(self, user_id: str, name: str, value: int) -> str:
        resources = self._get_resources(user_id)
        
        resources[name] = {'value': value, 'created_at': datetime.now().isoformat()}
        self._save_resources(user_id, resources)
        return self.reply.render("resource_set", name=name, value=value)
    
    def _del_resource(self, user_id: str, name: str) -> str:
        resources = self._get_resources(user_id)
        
        if name in resources:
            del resources[name]
            self._save_resources(user_id, resources)
            return self.reply.render("resource_deleted", name=name)
        
        return self.reply.render("resource_not_found", name=name)


resource_record_module = ResourceRecordModule()
