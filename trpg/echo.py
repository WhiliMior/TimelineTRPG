"""
最简单的业务模块示例：echo 功能
演示如何使用 adapter 层，完全不接触 AstrBot API。
"""
from ..adapter.reply import ReplyManager
from ..adapter.command_context import CommandContext
from ..adapter.help import HelpEntry, HelpRegistry


class EchoModule:
    """
    Echo 模块：接收消息并返回相同的消息（回显）
    
    使用 adapter 层的示例：
    1. 使用 ReplyManager 从 JSON 配置加载模板
    2. 通过 CommandContext 的 send() 方法添加回复
    3. 完全不涉及 AstrBot API，完全解耦
    """
    
    def __init__(self):
        self.reply = ReplyManager("echo")
    
    @property
    def help_entry(self) -> HelpEntry:
        """返回模块的标准帮助条目，由 HelpRegistry 自动收集。"""
        return HelpEntry(
            module="echo",
            usage="<消息>",  # 不包含前缀 "echo"，前缀会动态显示
            summary="回显消息",
            detail=(
                ".echo <消息>\n"
                "将收到的消息原样返回。\n"
                "\n"
                "示例:\n"
                "  .echo 你好世界  → 收到消息: 你好世界"
            ),
        )
    
    async def echo(self, ctx: CommandContext) -> bool:
        """
        echo 指令处理函数
        
        使用示例: .echo 你好，世界！
        返回: "收到消息: 你好，世界！"
        """
        if not ctx.args:
            help_text = self.reply.render("help")
            ctx.send(help_text)
            return True
        
        message = " ".join(ctx.args)
        result_text = self.reply.render("echo_result", message=message)
        ctx.send(result_text)
        return True


# 创建模块实例（供 main.py 导入）
echo_module = EchoModule()
