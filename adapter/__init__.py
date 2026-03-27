"""
Adapter 层 - TimelineTRPG 插件的适配器中间件
提供配置表驱动的指令路由和回复模板系统，使业务层完全解耦于 AstrBot API。
"""
from .command_context import CommandContext
from .reply import ReplyManager, ReplyPayload
from .router import Router
from .help import HelpEntry, HelpRegistry
from .storage import StorageBackend, StorageType

__all__ = [
    "CommandContext",
    "ReplyManager",
    "ReplyPayload",
    "Router",
    "HelpEntry",
    "HelpRegistry",
    "StorageBackend",
    "StorageType",
]