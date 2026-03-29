"""
目标系统 - 管理检定的目标值
迁移自老项目 Game/Runtime/Examination/TargetManager.py
"""
import random
import re
from typing import Dict, Any, Optional

from ...adapter.command_context import CommandContext
from ...adapter.message import ReplyManager
from ...infrastructure.help import HelpEntry
from ...infrastructure.storage import StorageBackend


class TargetModule:
    """
    目标值模块
    
    支持的指令格式：
    - .tar - 查看当前目标值
    - .tar <数值> - 设置固定目标值
    - .tar <等级>d - 随机难度目标值
    - .tar <数字1> <数字2> - 计算目标值（两数相乘）
    """
    
    def __init__(self):
        self.reply = ReplyManager("examination")  # 使用 examination 的回复模板
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="tar",
            usage="[数值|等级d|数字1 数字2]",
            summary="设置/查看目标值",
            detail=(
                "- 查看当前目标数值\n"
                "{目标数值} - 直接设定\n"
                "{等级}d - 随机难度\n"
                "{等级} {难度} - 计算目标数值"
            ),
        )
    
    async def tar(self, ctx: CommandContext) -> bool:
        """
        处理目标值命令
        
        .tar {目标数值} 固定数值
        .tar {等级} {难度} 计算数值
        .tar {等级}d 随机难度
        """
        # 判断会话类型
        session_type = "group" if ctx.group_id else "private"
        conversation_id = ctx.group_id or ctx.session_id or ctx.sender_id or "default"
        
        if not ctx.args:
            # 没有参数，显示当前目标值
            target_value = await self._get_target(conversation_id, session_type)
            if target_value is None:
                response = self.reply.render("tar_none")
            else:
                response = self.reply.render("tar_is", value=target_value)
        elif len(ctx.args) == 1:
            cmd1 = ctx.args[0]
            
            # 随机难度 (Xd 格式)
            if 'd' in cmd1.lower():
                try:
                    number_list = re.findall(r'\d+', cmd1)
                    if number_list:
                        level = int(''.join(number_list))
                        result = await self._set_random_target(conversation_id, level, session_type)
                        if result['status'] == 'success':
                            response = self.reply.render(
                                "tar_ran",
                                random=result['random_number'],
                                value=result['target_value']
                            )
                        else:
                            response = self.reply.render("invalid_target_value")
                    else:
                        response = self.reply.render("invalid_target_value")
                except ValueError:
                    response = self.reply.render("invalid_target_value")
            else:
                # 单个数字
                try:
                    target_value = float(cmd1)
                    result = await self._set_target_value(conversation_id, target_value, session_type)
                    if result['status'] == 'success':
                        response = self.reply.render("tar_set", value=result['target_value'])
                    else:
                        response = self.reply.render("invalid_target_value")
                except ValueError:
                    response = self.reply.render("invalid_target_value")
        elif len(ctx.args) == 2:
            # 两个参数，计算数值
            cmd1, cmd2 = ctx.args[0], ctx.args[1]
            try:
                float_cmd1 = float(cmd1)
                float_cmd2 = float(cmd2)
                result = await self._calculate_target(conversation_id, float_cmd1, float_cmd2, session_type)
                if result['status'] == 'success':
                    response = self.reply.render("tar_set", value=result['target_value'])
                else:
                    response = self.reply.render("invalid_target_value")
            except ValueError:
                response = self.reply.render("invalid_target_value")
        else:
            response = self.reply.render("invalid_command_format")
        
        ctx.send(response)
        return True
    
    async def _get_target(self, conversation_id: str, session_type: str = "private") -> Optional[float]:
        """获取目标值"""
        data = StorageBackend.load_target(conversation_id, session_type)
        if data:
            return data.get("target_value")
        return None
    
    async def _set_target(self, conversation_id: str, target_value: float, session_type: str = "private"):
        """设置目标值"""
        data = {"target_value": int(target_value)}
        StorageBackend.save_target(conversation_id, data, session_type)
    
    async def _get_current_target(self, conversation_id: str, session_type: str = "private"):
        """获取当前目标值（返回元组）"""
        target_value = await self._get_target(conversation_id, session_type)
        if target_value is None:
            return None, {'status': 'no_target', 'message': None}
        else:
            return target_value, {'status': 'has_target', 'message': target_value}
    
    async def _set_target_value(self, conversation_id: str, target_value: float, session_type: str = "private") -> Dict[str, Any]:
        """设置目标值"""
        try:
            target_value = int(target_value)
            await self._set_target(conversation_id, target_value, session_type)
            return {'status': 'success', 'target_value': target_value}
        except (ValueError, TypeError):
            return {'status': 'error', 'target_value': None}
    
    async def _set_random_target(self, conversation_id: str, level: int, session_type: str = "private") -> Dict[str, Any]:
        """设置随机目标值"""
        try:
            level = int(level)
            random_number = random.randint(1, 20)
            target_value = int(level * random_number)
            await self._set_target(conversation_id, target_value, session_type)
            return {'status': 'success', 'target_value': target_value, 'random_number': random_number}
        except ValueError:
            return {'status': 'error', 'target_value': None, 'random_number': None}
    
    async def _calculate_target(self, conversation_id: str, value1: float, value2: float, session_type: str = "private") -> Dict[str, Any]:
        """计算目标值"""
        try:
            target_value = int(value1 * value2)
            await self._set_target(conversation_id, target_value, session_type)
            return {'status': 'success', 'target_value': target_value}
        except (ValueError, TypeError):
            return {'status': 'error', 'target_value': None}


# 创建模块实例
target_module = TargetModule()
