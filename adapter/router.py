"""
路由器模块，提供配置表驱动的指令分发功能。
通过 ROUTES 字典注册指令到处理函数，新增指令只需加一行配置。

这是外部适配层 (adapter/)，仅负责消息路由
"""

import inspect
import logging
from collections.abc import Callable

from ..trpg.adapter.command_context import CommandContext

# 创建 adapter 层专用的 logger
logger = logging.getLogger("TimelineTRPG.adapter")


class Router:
    """
    指令路由器，根据配置表分发指令到对应的处理函数。

    使用示例:
        router = Router()
        router.register("ex", character_module.set_attribute)
        router.register("stat", character_module.show_status)

        # 分发指令
        await router.dispatch(ctx)
    """

    def __init__(self):
        self.routes: dict[str, Callable] = {}
        self.default_handler: Callable | None = None

    def register(self, command: str, handler: Callable) -> None:
        """
        注册指令处理函数

        Args:
            command: 指令名（如 "ex"）
            handler: 处理函数，接收 CommandContext 参数
        """
        if not callable(handler):
            raise ValueError(f"处理器必须是可调用对象: {handler}")

        # 检查处理函数签名
        try:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())

            if len(params) >= 1 and params[0].name == "self":
                # 实例方法，不需要额外参数检查
                pass
            elif len(params) < 1:
                raise ValueError(f"处理函数必须至少接收一个参数: {handler}")
        except Exception as e:
            logger.warning(f"[Router] 无法检查处理函数签名: {handler}, error: {e}")

        # 如果处理函数是协程函数，我们需要保持其异步性
        self.routes[command] = handler
        logger.debug(f"[Router] Registered command: {command} -> {handler.__name__}")

    def register_many(self, routes: dict[str, Callable]) -> None:
        """
        批量注册指令

        Args:
            routes: 指令名到处理函数的字典
        """
        for command, handler in routes.items():
            self.register(command, handler)

    def register_default(self, handler: Callable) -> None:
        """
        注册默认处理函数（当指令未找到时调用）

        Args:
            handler: 默认处理函数
        """
        if not callable(handler):
            raise ValueError(f"默认处理器必须是可调用对象: {handler}")
        self.default_handler = handler

    def has_route(self, command: str) -> bool:
        """检查指令是否已注册"""
        return command in self.routes

    def get_handler(self, command: str) -> Callable | None:
        """获取指令对应的处理函数"""
        return self.routes.get(command)

    async def dispatch(self, ctx: CommandContext) -> bool:
        """
        分发指令到对应的处理函数

        Args:
            ctx: 指令上下文

        Returns:
            bool: 指令是否成功分发和处理

        Raises:
            ValueError: 如果处理函数返回非预期值
        """
        command = ctx.command

        # 记录指令分发信息
        logger.info(
            f"[Dispatch] command={command}, args={ctx.args}, sender={ctx.sender_name}, group={ctx.group_id}"
        )

        if command not in self.routes:
            logger.warning(
                f"[Dispatch] Command '{command}' not found in routes: {list(self.routes.keys())}"
            )
            if self.default_handler is not None:
                logger.info(f"[Dispatch] Using default handler for command '{command}'")
                return await self._call_handler(self.default_handler, ctx)
            logger.error(
                f"[Dispatch] Command '{command}' not found and no default handler"
            )
            return False

        handler = self.routes[command]
        logger.debug(f"[Dispatch] Handler: {handler.__name__}")

        # 调用 handler 并记录结果
        result = await self._call_handler(handler, ctx)
        logger.info(
            f"[Dispatch] Handler result for '{command}': {result}, has_reply={ctx.has_reply()}, reply_count={len(ctx.reply_payloads)}"
        )
        return result

    async def _call_handler(self, handler: Callable, ctx: CommandContext) -> bool:
        """
        调用处理函数

        Args:
            handler: 处理函数
            ctx: 指令上下文

        Returns:
            bool: 是否成功调用
        """
        try:
            # 判断是否是协程函数
            if inspect.iscoroutinefunction(handler):
                result = await handler(ctx)
            else:
                result = handler(ctx)

            # 处理函数可以返回 bool 指示成功/失败，或者 None（表示成功）
            if result is None:
                return True
            elif isinstance(result, bool):
                return result
            else:
                # 非 bool/None 返回值视为成功
                return True

        except Exception as e:
            # 记录处理函数抛出的异常
            import traceback

            logger.error(
                f"[Handler Error] command={ctx.command}, handler={handler.__name__}, error={e}\n"
                f"  traceback: {traceback.format_exc(limit=5)}"
            )

            # 向上下文添加错误回复
            ctx.send(f"指令处理出错: {e}")
            return False

    def list_commands(self) -> list:
        """列出所有已注册的指令"""
        return list(self.routes.keys())

    def clear_routes(self) -> None:
        """清空所有路由"""
        self.routes.clear()
        self.default_handler = None

    def to_dict(self) -> dict[str, str]:
        """转换为字典格式，便于调试"""
        result = {}
        for command, handler in self.routes.items():
            result[command] = (
                handler.__name__ if hasattr(handler, "__name__") else str(handler)
            )
        return result
