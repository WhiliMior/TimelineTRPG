"""
交涉模块 - 处理交涉检定相关功能
迁移自老项目 Game/Runtime/Examination/NegotiationCommandHandler.py
"""
import random
from typing import Dict, Optional

from ..adapter.command_context import CommandContext
from ..adapter.reply import ReplyManager
from ..adapter.help import HelpEntry


# 交涉目标存储
_negotiation_target_storage: Dict[str, Dict] = {}


class NegotiationModule:
    """
    交涉模块
    
    支持的指令格式：
    - .neg - 显示当前交涉对象
    - .neg <rp评分> - 进行交涉
    - .neg <对象等级> <对象智力%> - 设定交涉对象
    - .neg <rp评分> <对象等级> <对象智力%> - 设定并交涉
    """
    
    def __init__(self):
        self.reply = ReplyManager("negotiation")
    
    @property
    def help_entry(self) -> HelpEntry:
        return HelpEntry(
            module="neg",
            usage="[rp评分] [对象等级] [对象智力%]",
            summary="交涉检定",
            detail=(
                "{RP评分} - 进行交涉检定\n"
                "{对象等级} {对象智力%} - 设定交涉对象\n"
                "{RP评分} {对象等级} {对象智力%} - 设定交涉对象并交涉\n"
                "\n"
                "示例:\n"
                "  neg → 查看当前交涉对象\n"
                "  neg 80 → 使用80分进行交涉\n"
                "  neg 5 60 → 设定5级对象，智力60%\n"
                "  neg 80 5 60 → 设定对象并交涉"
            ),
        )
    
    async def neg(self, ctx: CommandContext) -> bool:
        """
        处理交涉命令
        """
        conversation_id = ctx.group_id or ctx.session_id or ctx.sender_id or "default"
        
        if not ctx.args:
            # 显示当前交涉对象
            target = self._get_negotiation_target(conversation_id)
            if target is None:
                response = self.reply.render("no_current_negotiation_target")
            else:
                target_level = target['level']
                target_intelligence = target['intelligence']
                response = self.reply.render("current_negotiation_target", level=target_level, intelligence=target_intelligence)
            ctx.send(response)
            return True
        
        arg_list = ctx.args
        
        if len(arg_list) == 1:
            # 一个参数：进行交涉
            try:
                rp_grade = float(arg_list[0])
                result = await self._perform_negotiation(ctx, conversation_id, rp_grade)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("invalid_rp_grade")
                ctx.send(response)
        
        elif len(arg_list) == 2:
            # 两个参数：设定交涉对象
            try:
                target_level = int(float(arg_list[0]))
                intelligence_str = arg_list[1]
                if intelligence_str.endswith('%'):
                    target_intelligence = int(float(intelligence_str[:-1]))
                else:
                    target_intelligence = int(float(intelligence_str))
                
                self._set_negotiation_target(conversation_id, target_level, target_intelligence)
                response = self.reply.render("negotiation_target_set")
                ctx.send(response)
            except ValueError:
                response = self.reply.render("invalid_target_params")
                ctx.send(response)
        
        elif len(arg_list) == 3:
            # 三个参数：设定并交涉
            try:
                rp_grade = float(arg_list[0])
                target_level = int(float(arg_list[1]))
                intelligence_str = arg_list[2]
                if intelligence_str.endswith('%'):
                    target_intelligence = int(float(intelligence_str[:-1]))
                else:
                    target_intelligence = int(float(intelligence_str))
                
                self._set_negotiation_target(conversation_id, target_level, target_intelligence)
                result = await self._perform_negotiation(ctx, conversation_id, rp_grade)
                ctx.send(result)
            except ValueError:
                response = self.reply.render("invalid_params")
                ctx.send(response)
        
        else:
            response = self.reply.render("invalid_command")
            ctx.send(response)
        
        return True
    
    def _get_negotiation_target(self, conversation_id: str) -> Optional[Dict]:
        return _negotiation_target_storage.get(conversation_id)
    
    def _set_negotiation_target(self, conversation_id: str, level: int, intelligence: int):
        _negotiation_target_storage[conversation_id] = {
            "level": level,
            "intelligence": intelligence
        }
    
    async def _perform_negotiation(self, ctx: CommandContext, conversation_id: str, rp_grade: float) -> str:
        """执行交涉检定"""
        target = self._get_negotiation_target(conversation_id)
        
        if target is None:
            return self.reply.render("no_current_negotiation_target")
        
        level = target['level']
        intelligence = target['intelligence']
        
        # 计算目标难度
        difficulty = level * 10 + (100 - intelligence)
        
        # 掷骰
        roll = random.randint(1, 100)
        
        # 计算最终结果
        final_result = roll + rp_grade
        
        if final_result >= difficulty:
            return self.reply.render("negotiation_success", roll=roll, rp=rp_grade, final=final_result, difficulty=difficulty)
        else:
            return self.reply.render("negotiation_failure", roll=roll, rp=rp_grade, final=final_result, difficulty=difficulty)


negotiation_module = NegotiationModule()
