"""
批处理指令层 - 组合多个 service 功能的高级指令
该层单向引用 service 层，不反向依赖。

指令转发通过 infrastructure 层的 CommandDispatcher 实现。
"""

from .character_reset import character_reset_module

__all__ = ["character_reset_module"]
