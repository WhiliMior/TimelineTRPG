"""
指令上下文模块，提供 CommandContext 类封装指令执行的上下文信息。
业务模块通过 ctx.send() 方法添加回复载荷，不实际发送消息。

迁移自 adapter/command_context.py -> trpg/adapter/command_context.py
"""

import logging
from dataclasses import dataclass, field

from .message import ReplyPayload

# 创建 adapter 层专用的 logger
logger = logging.getLogger("TimelineTRPG.adapter")


@dataclass
class CommandContext:
    """
    指令上下文，封装指令执行的上下文信息。

    包含：
    - 原始指令（如 "ex"）
    - 指令参数列表（如 ["力量", "30"]）
    - 发送者信息
    - 会话/群组信息
    - 收集的回复载荷列表

    业务模块调用 ctx.send(text) 时，消息被添加到 reply_payloads 列表，
    最后由 main.py 统一转换为 AstrBot 消息发送。
    """

    command: str
    args: list[str] = field(default_factory=list)
    sender_id: str | None = None
    sender_name: str | None = None
    session_id: str | None = None
    group_id: str | None = None
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    # 收集的回复载荷
    reply_payloads: list[ReplyPayload] = field(default_factory=list, init=False)

    def send(
        self,
        text: str,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        """
        添加回复消息（不实际发送）

        Args:
            text: 回复消息文本
            metadata: 附加元数据，如消息类型、格式等
        """
        if metadata is None:
            metadata = {}

        payload = ReplyPayload(text=text, metadata=metadata)
        self.reply_payloads.append(payload)

        # 记录回复内容
        logger.debug(
            f"[{self.command}] Reply: {text[:100]}{'...' if len(text) > 100 else ''}"
        )

    def send_payload(self, payload: ReplyPayload) -> None:
        """
        直接添加 ReplyPayload 对象

        Args:
            payload: ReplyPayload 实例
        """
        self.reply_payloads.append(payload)

    def send_image(
        self,
        image_path: str,
        delete_after_send: bool = True,
        text: str = "",
    ) -> None:
        """
        发送图片消息

        Args:
            image_path: 图片文件路径
            delete_after_send: 发送成功后是否删除图片文件
            text: 附带说明文本（可选）
        """
        payload = ReplyPayload(
            text=text,
            metadata={"type": "image"},
            image_path=image_path,
            image_delete_after_send=delete_after_send,
        )
        self.reply_payloads.append(payload)
        logger.debug(f"[{self.command}] Image: {image_path}")

    def get_reply_texts(self) -> list[str]:
        """
        获取所有回复消息的文本列表

        Returns:
            回复消息文本列表
        """
        return [payload.text for payload in self.reply_payloads]

    def has_reply(self) -> bool:
        """检查是否有回复消息"""
        return len(self.reply_payloads) > 0

    def clear_replies(self) -> None:
        """清空所有回复消息"""
        self.reply_payloads.clear()

    def get_arg(self, index: int, default: str | None = None) -> str | None:
        """
        获取指定位置的参数，支持默认值

        Args:
            index: 参数索引（从0开始）
            default: 默认值，如果索引越界

        Returns:
            参数值或默认值
        """
        if 0 <= index < len(self.args):
            return self.args[index]
        return default

    def get_args_after(self, start_index: int) -> list[str]:
        """
        获取从指定索引开始的所有参数

        Args:
            start_index: 起始索引

        Returns:
            参数列表
        """
        if start_index < 0:
            start_index = 0
        if start_index >= len(self.args):
            return []
        return self.args[start_index:]

    def get_all_text(self) -> str:
        """
        获取完整的指令+参数文本（模拟原始消息）

        Returns:
            如 ".ex 力量 30"
        """
        if not self.args:
            return f".{self.command}"
        return f".{self.command} {' '.join(self.args)}"

    def to_dict(
        self,
    ) -> dict[
        str,
        str
        | int
        | float
        | bool
        | None
        | list[str]
        | list[ReplyPayload]
        | dict[str, str | int | float | bool | None],
    ]:
        """转换为字典格式，便于序列化或调试"""
        return {
            "command": self.command,
            "args": self.args,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "session_id": self.session_id,
            "group_id": self.group_id,
            "metadata": self.metadata,
            "has_reply": self.has_reply(),
            "reply_count": len(self.reply_payloads),
        }
