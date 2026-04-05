"""
指令转发器 - 实现层级间的指令转发功能

设计目的：
- 允许 batch_command 层注册指令处理函数
- service 层通过此转发器调用 batch_command，保持单向引用特性
- infrastructure 层作为中间层，不依赖任何业务层

使用方式：
1. batch_command 层注册指令: dispatcher.register("chr_reset", handler)
2. service 层通过转发器调用: dispatcher.dispatch("chr_reset", ctx)
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapter.command_context import CommandContext


class CommandDispatcher:
    """
    指令转发器

    提供指令注册和转发功能，用于层级间的解耦调用。
    """

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, command_key: str, handler: Callable) -> None:
        """
        注册指令处理函数

        Args:
            command_key: 指令标识符，如 "chr_reset"
            handler: 处理函数，接收 CommandContext 参数
        """
        self._handlers[command_key] = handler

    def dispatch(self, command_key: str, ctx: "CommandContext") -> bool | None:
        """
        转发指令到已注册的处理函数

        Args:
            command_key: 指令标识符
            ctx: 命令上下文

        Returns:
            处理函数的返回值，或 None（如果指令未注册）
        """
        handler = self._handlers.get(command_key)
        if handler is None:
            return None

        return handler(ctx)

    def has_command(self, command_key: str) -> bool:
        """检查指令是否已注册"""
        return command_key in self._handlers

    def unregister(self, command_key: str) -> bool:
        """取消注册指令"""
        if command_key in self._handlers:
            del self._handlers[command_key]
            return True
        return False


# 全局转发器实例
command_dispatcher = CommandDispatcher()
