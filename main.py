"""
TimelineTRPG 插件主入口
基于 adapter 层架构，实现配置表驱动的指令路由和回复模板系统。
业务模块完全不接触 AstrBot API，完全解耦。
"""
import re
from typing import Generator

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入 adapter 层（使用相对导入，与 qq_group_daily_analysis 保持一致）
from .trpg.adapter.command_context import CommandContext
from .adapter.router import Router
from .trpg.adapter.message import ReplyManager
from .trpg.infrastructure.help import HelpEntry, HelpRegistry

# 导入业务模块（使用新的服务层路径）
from .trpg.service.dice.dice import roll_dice_module
from .trpg.service.examination.examination import examination_module
from .trpg.service.examination.target import target_module
from .trpg.service.character.character import character_module
from .trpg.service.buff.buff import buff_module
from .trpg.service.resource.modifier import resource_modifier_module
from .trpg.service.negotiation.negotiation import negotiation_module
from .trpg.service.battle.timeline import timeline_module
from .trpg.service.battle.battle import battle_module
from .trpg.service.inventory.inventory import inventory_module
from .trpg.service.resource.resource import resource_record_module
from .trpg.service.weapon.weapon import weapon_module
from .trpg.service.level.level import level_module

# 插件信息
PLUGIN_NAME = "TimelineTRPG"
PLUGIN_VERSION = "v0.1"
PLUGIN_AUTHOR = "WhiliMior"


@register("TimelineTRPG", PLUGIN_AUTHOR, "为时间线TRPG规则制作的骰子机器人", PLUGIN_VERSION)
class TimelineTRPG(Star):
    """
    Timeline TRPG 插件主类
    使用 adapter 层架构，业务模块完全解耦
    """
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.router = Router()
        self.system_reply = ReplyManager("system")
        self.help_registry = HelpRegistry(
            header="=== TimelineTRPG ===",
            footer="使用 .help <模块> 查看模块详细帮助",
            router=self.router  # 传递 Router 实例，用于动态获取指令前缀
        )
        self.module_instances: list = []
        self.module_instances.append(roll_dice_module)
        self.module_instances.append(examination_module)
        self.module_instances.append(target_module)
        self.module_instances.append(character_module)
        self.module_instances.append(buff_module)
        self.module_instances.append(resource_modifier_module)
        self.module_instances.append(negotiation_module)
        self.module_instances.append(timeline_module)
        self.module_instances.append(battle_module)
        self.module_instances.append(inventory_module)
        self.module_instances.append(resource_record_module)
        self.module_instances.append(weapon_module)
        self.module_instances.append(level_module)
        self._setup_routes()
        self._collect_help_entries()
        logger.info(f"[{PLUGIN_NAME}] 插件初始化完成，adapter 层架构已加载")
        logger.info(f"[{PLUGIN_NAME}] 路由表: {self.router.list_commands()}")
    
    def _setup_routes(self):
        """配置指令路由表"""
        # 注册子模块指令
        self.router.register("r", self._wrap_with_sub_help(roll_dice_module, "r"))
        self.router.register("ex", self._wrap_with_sub_help(examination_module, "ex"))
        self.router.register("tar", self._wrap_with_sub_help(target_module, "tar"))
        self.router.register("chr", self._wrap_with_sub_help(character_module, "chr"))
        self.router.register("char", self._wrap_with_sub_help(character_module, "chr"))  # 老项目别名
        self.router.register("buff", self._wrap_with_sub_help(buff_module, "buff"))
        self.router.register("dr", self._wrap_with_sub_help(resource_modifier_module, "dr"))
        self.router.register("resmod", self._wrap_with_sub_help(resource_modifier_module, "dr"))  # 老项目别名
        self.router.register("neg", self._wrap_with_sub_help(negotiation_module, "neg"))
        self.router.register("tl", self._wrap_with_sub_help(timeline_module, "tl"))
        self.router.register("bt", self._wrap_with_sub_help(battle_module, "bt"))
        self.router.register("i", self._wrap_with_sub_help(inventory_module, "i"))
        self.router.register("rc", self._wrap_with_sub_help(resource_record_module, "rc"))
        self.router.register("wp", self._wrap_with_sub_help(weapon_module, "wp"))
        self.router.register("setupWP", self._wrap_with_sub_help(weapon_module, "wp_setup"))
        self.router.register("lv", self._wrap_with_sub_help(level_module, "lv"))
        
        # 注册角色创建指令
        self.router.register("tlsetup", self._wrap_with_sub_help(character_module, "tlsetup"))
        self.router.register("TLsetup", self._wrap_with_sub_help(character_module, "tlsetup"))  # 大写别名
        
        # 注册 help 指令
        self.router.register("help", self._handle_help)
        
        # 注册默认处理函数
        self.router.register_default(self._handle_unknown_command)
        
        logger.info(f"[{PLUGIN_NAME}] 路由表配置完成: {self.router.list_commands()}")
    
    def _collect_help_entries(self):
        """
        自动收集所有子模块的 help_entry 并注册到 HelpRegistry。
        子模块需要暴露 help_entry 属性（返回 HelpEntry 实例）。
        """
        for module in self.module_instances:
            entry = getattr(module, "help_entry", None)
            if isinstance(entry, HelpEntry):
                self.help_registry.register(entry)
        logger.info(f"[{PLUGIN_NAME}] 帮助系统已加载: {self.help_registry.list_modules()}")
    
    def _wrap_with_sub_help(self, module, command: str):
        """
        包装子模块处理函数，拦截 args 中的 "help" 参数。

        当用户输入 .<cmd> help 时，调用 HelpRegistry 显示该模块的帮助信息；
        否则将 ctx 原样传递给子模块的原始处理函数。
        """
        handler = getattr(module, command, None)
        if handler is None:
            raise AttributeError(f"模块 {module!r} 没有方法 '{command}'")
        
        # 保存 self 的引用以便在 wrapped 中使用
        self_ref = self

        async def wrapped(ctx: CommandContext) -> bool:
            # 如果参数是 "help" 或以 "help" 开头，显示该模块的帮助
            if ctx.args and ctx.args[0].lower() == "help":
                entry = self_ref.help_registry.get(command)
                if entry:
                    ctx.send(entry.detail or entry.summary)
                    return True
                # 没有注册 help_entry，回退到子模块自行处理
                ctx.args = ctx.args[1:]  # 去掉 "help"
                return await handler(ctx)
            
            return await handler(ctx)
        
        return wrapped
    
    async def _handle_help(self, ctx: CommandContext) -> bool:
        """
        处理 .help 指令
        
        .help         → 显示总帮助概览
        .help <模块>  → 显示指定模块的详细帮助
        """
        if not ctx.args:
            ctx.send(self.help_registry.format_summary())
            return True
        
        module_name = ctx.args[0].lower()
        detail = self.help_registry.format_detail(module_name)
        
        if detail is None:
            ctx.send(self.system_reply.render("help_not_found", module=module_name))
            ctx.send(self.help_registry.format_summary())
            return True
        
        ctx.send(detail)
        return True
    
    @filter.regex(r"^[.。#/](\w+)\b")
    async def trpg_command_handler(self, event: AstrMessageEvent) -> Generator[MessageEventResult, None, None]:
        """
        TRPG 指令统一入口
        匹配所有 .。#/ 开头的指令，如 .help, 。r, #bt 等
        
        数据流：
        1. 匹配 ".指令" 格式（支持 . 。 # / 四种前缀）
        2. 创建 CommandContext
        3. 通过 Router 分发到对应业务模块
        4. 将 ReplyPayload 转换为 event.plain_result()
        """
        message_str = event.message_str.strip()
        
        match = re.match(r"^[.。#/](\w+)\b\s*(.*)$", message_str)
        if not match:
            yield event.plain_result("指令格式错误")
            return
        
        command = match.group(1)  # 保留原始大小写
        args_str = match.group(2).strip()
        args = await self._parse_args(args_str)
        
        ctx = CommandContext(
            command=command,
            args=args,
            sender_id=event.get_sender_id(),
            sender_name=event.get_sender_name(),
            session_id=event.get_session_id(),
            group_id=event.get_group_id() if hasattr(event, 'get_group_id') else None,
            metadata={
                "message_str": message_str,
                "raw_event": str(event)
            }
        )
        
        # 指令分发日志由 adapter 层统一输出
        
        try:
            success = await self.router.dispatch(ctx)
            
            if not success:
                # 记录指令处理失败的详细信息
                logger.warning(
                    f"[{PLUGIN_NAME}] 指令处理失败: command={command}, "
                    f"args={args}, sender={ctx.sender_name}, group={ctx.group_id}"
                )
                yield event.plain_result("指令处理失败")
                return
            
            if not ctx.has_reply():
                logger.debug(f"[{PLUGIN_NAME}] 指令无回复: command={command}")
                yield event.plain_result("指令执行完成")
                return

            for payload in ctx.reply_payloads:
                yield event.plain_result(payload.text)
                
        except Exception as e:
            import traceback
            error_msg = f"指令处理异常: {str(e)}"
            logger.error(
                f"[{PLUGIN_NAME}] {error_msg}\n"
                f"  command={command}, args={args}, sender={ctx.sender_name}\n"
                f"  traceback: {traceback.format_exc(limit=5)}"
            )
            yield event.plain_result(self.system_reply.render("internal_error", error=str(e)))
    
    async def _parse_args(self, args_str: str) -> list[str]:
        """解析参数字符串"""
        if not args_str:
            return []
        return args_str.split()
    
    async def _handle_unknown_command(self, ctx: CommandContext) -> bool:
        """处理未知指令"""
        ctx.send(self.system_reply.render("command_not_found", command=ctx.command))
        ctx.send(self.help_registry.format_summary())
        return True
    
    async def initialize(self):
        """插件初始化方法"""
        logger.info(f"[{PLUGIN_NAME}] {PLUGIN_VERSION} 初始化完成，adapter 层架构已就绪")
        logger.info(f"[{PLUGIN_NAME}] 可用指令: {', '.join(['.' + cmd for cmd in self.router.list_commands()])}")
    
    async def terminate(self):
        """插件销毁方法"""
        logger.info(f"[{PLUGIN_NAME}] 插件已卸载，adapter 层架构已清理")


__plugin_name__ = "TimelineTRPG"
__plugin_author__ = PLUGIN_AUTHOR
__plugin_version__ = PLUGIN_VERSION
__plugin_description__ = "为时间线TRPG规则制作的骰子机器人，基于 adapter 层架构"
