"""
Help 注册表模块，提供统一的帮助信息管理和查询。

每个子模块通过 HelpRegistry.register() 注册自身的帮助信息，
支持：
  - .help         → 显示所有已注册模块的帮助总览
  - .help <module> → 显示指定模块的详细帮助
  - .<cmd> help   → 调用对应模块的 help 字段

设计特点：
  - 自动搜集指令前缀并显示
  - 如果更改指令前缀，help 显示的前缀也会动态更改
  - 支持从 Router 动态获取可用命令列表
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class HelpEntry:
    """
    单个模块的帮助条目。

    Attributes:
        module:     模块标识（与指令名对应，如 "echo"）
        usage:      简短用法说明（不包含前缀），如 "<消息>" 而不是 "echo <消息>"
        summary:    一句话简介，如 "回显消息"
        detail:     详细帮助文本（支持换行），可包含用法示例
    """
    module: str
    usage: str
    summary: str
    detail: str = ""


class HelpRegistry:
    """
    帮助信息注册表，集中管理所有子模块的帮助条目。

    设计目标：动态获取指令前缀，使帮助信息与实际路由配置同步。

    使用示例:
        registry = HelpRegistry(header="=== TimelineTRPG ===", footer="使用 .help <模块> 查看详细帮助")
        registry.register(HelpEntry("echo", "<消息>", "回显消息", "..."))
    """

    def __init__(self, header: str = "", footer: str = "", router=None):
        self._entries: dict[str, HelpEntry] = {}
        self.header: str = header
        self.footer: str = footer
        self._router = router  # 可选的 Router 实例，用于动态获取指令前缀

    def register(self, entry: HelpEntry) -> None:
        """注册一个帮助条目，module 相同时覆盖旧条目。"""
        self._entries[entry.module] = entry

    def unregister(self, module: str) -> None:
        """移除指定模块的帮助条目。"""
        self._entries.pop(module, None)

    def get(self, module: str) -> HelpEntry | None:
        """查询指定模块的帮助条目。"""
        return self._entries.get(module)

    def has(self, module: str) -> bool:
        return module in self._entries

    def list_modules(self) -> list[str]:
        """返回所有已注册模块名列表。"""
        return list(self._entries.keys())

    def set_router(self, router):
        """设置 Router 实例，用于动态获取指令前缀。"""
        self._router = router

    def get_available_commands(self) -> List[str]:
        """
        获取当前可用的指令列表。
        优先从 Router 获取，如果没有设置 Router 则从注册的帮助条目获取。
        """
        if self._router and hasattr(self._router, 'list_commands'):
            # 从 Router 获取实际可用的命令列表
            return self._router.list_commands()
        else:
            # 返回注册的帮助模块列表
            return self.list_modules()

    # ── 格式化输出 ──────────────────────────────────────

    def format_summary(self) -> str:
        """
        生成总帮助概览文本，每个模块一行。
        动态获取指令前缀，确保与实际配置同步。

        格式:
            .echo <消息>    - 回显消息
            .r <表达式>     - 掷骰子
        """
        available_commands = self.get_available_commands()
        if not available_commands:
            return "暂无可用指令。"

        lines: list[str] = []
        if self.header:
            lines.append(self.header)
        
        # 首先显示所有已注册且有帮助的指令
        for command in sorted(available_commands):
            entry = self._entries.get(command)
            if entry:
                # 动态添加前缀
                lines.append(f"  .{command} {entry.usage:<20} - {entry.summary}")
        
        if self.footer:
            lines.append(self.footer)
        return "\n".join(lines)

    def format_detail(self, module: str) -> str | None:
        """
        生成指定模块的详细帮助文本。

        如果模块未注册，返回 None。
        """
        # 首先检查是否有 help 条目
        entry = self._entries.get(module)
        if entry is None:
            return None
        
        # 构建详细帮助，动态添加前缀
        if entry.detail:
            # 如果有详细帮助，直接使用，但确保格式正确
            return f".{module}\n{entry.detail}"
        else:
            # 如果没有详细帮助，使用总结信息
            return f".{module} {entry.usage} - {entry.summary}"

    def format_all(self) -> str:
        """
        生成完整帮助文本（概览 + 所有模块的详细帮助）。
        """
        if not self._entries:
            return "暂无可用指令。"

        parts: list[str] = [self.format_summary()]
        for entry in self._entries.values():
            # 显示每个模块的详细帮助，动态添加前缀
            if entry.detail:
                parts.append(f"\n--- .{entry.module} ---\n{entry.detail}")
            else:
                parts.append(f"\n--- .{entry.module} ---\n{entry.summary}")
        return "\n".join(parts)