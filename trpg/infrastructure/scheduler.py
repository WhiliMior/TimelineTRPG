"""
定时事件调度器 - 管理战斗中的定时事件
迁移自老项目 Game/Runtime/Battle/BattleSystem.py 中的定时事件功能

功能：
- 调度带持续时间（time_based）或生效次数（count_based）的事件
- 结算到期事件并执行回调（buff / 护盾 / 资源修饰的移除）

使用方式：
- 业务模块调用 schedule_event 时传入 callback_path（模块路径字符串）与当前时间点
- 回调路径持久化在 battle json 中，到期时动态导入并 await 执行
- 当前时间点由调用方（service 层的 TimelineCore）计算后传入，
  本模块不依赖 service 层
"""

import importlib
import inspect
import logging
import uuid

from .storage import StorageBackend

logger = logging.getLogger("TimelineTRPG.scheduler")

TIME_BASED = "time_based"
COUNT_BASED = "count_based"

# 本模块位于 <插件包>.trpg.infrastructure.scheduler，
# AstrBot 以 data.plugins.<插件目录> 的形式加载插件，"trpg" 并不是顶层包
_TRPG_PACKAGE = __name__.rsplit(".", 2)[0]


def _resolve_module_path(module_path: str) -> str:
    """把持久化的 "trpg.xxx" 回调路径映射到实际加载的包路径"""
    if module_path == "trpg" or module_path.startswith("trpg."):
        return _TRPG_PACKAGE + module_path[len("trpg") :]
    return module_path


async def _run_callback(event: dict) -> bool:
    """执行事件回调（同步或异步函数均可），失败时记录日志并返回 False"""
    callback_path = event.get("callback_path")
    if not callback_path:
        return True

    module_path, _, function_name = callback_path.rpartition(".")
    if not module_path:
        logger.error("定时事件回调路径无效: %s", callback_path)
        return False

    try:
        module = importlib.import_module(_resolve_module_path(module_path))
        result = getattr(module, function_name)(**(event.get("callback_args") or {}))
        if inspect.isawaitable(result):
            await result
        return True
    except Exception:
        logger.exception("定时事件回调执行失败: %s", callback_path)
        return False


async def _run_callbacks(events: list[dict]) -> list[str]:
    """依次执行回调，返回需要提示给玩家的到期消息"""
    messages = []
    for event in events:
        await _run_callback(event)
        message = event.get("callback_message")
        if message:
            messages.append(message)
    return messages


def _load_active_battle(conversation_id: str, is_group: bool) -> dict | None:
    data = StorageBackend.load_battle_timeline(conversation_id, is_group)
    return StorageBackend.get_active_battle(data)


def _is_due(event: dict, current_time: float, user_id: str | None) -> bool:
    if user_id is not None and event.get("user_id") != user_id:
        return False
    end_time = event.get("end_time")
    return (
        event.get("mode") == TIME_BASED
        and end_time is not None
        and current_time >= end_time
    )


def _is_counted_for(event: dict, user_id: str, character_name: str) -> bool:
    return (
        event.get("mode") == COUNT_BASED
        and event.get("remaining_count") is not None
        and event.get("user_id") == user_id
        and event.get("character_name") == character_name
    )


async def schedule_event(
    conversation_id: str,
    user_id: str,
    character_name: str,
    action_description: str,
    duration_or_count: float,
    callback_path: str,
    callback_args: dict,
    callback_message: str,
    *,
    current_time: float,
    mode: str = TIME_BASED,
    event_type: str = "general",
    is_group: bool = True,
) -> dict | None:
    """
    调度一个定时事件

    Args:
        current_time: 战斗当前时间点（由调用方实时计算）
        mode: 'time_based'（持续 duration_or_count 时间）或 'count_based'（生效次数）
        event_type: 'general' / 'buff' / 'shield' / 'modifier'

    Returns:
        dict | None: 创建的事件；会话中没有进行中的战斗或参数无效时返回 None
    """
    if mode not in (TIME_BASED, COUNT_BASED):
        return None
    if _load_active_battle(conversation_id, is_group) is None:
        return None

    event = {
        "id": uuid.uuid4().hex,
        "event_type": event_type,
        "action_description": action_description,
        "start_time": current_time,
        "user_id": user_id,
        "character_name": character_name,
        "callback_path": callback_path,
        "callback_args": callback_args,
        "callback_message": callback_message,
        "mode": mode,
    }
    if mode == TIME_BASED:
        event["end_time"] = current_time + duration_or_count
        event["remaining_count"] = None
    else:
        event["remaining_count"] = int(duration_or_count)
        event["end_time"] = None

    async with StorageBackend.edit_battle_timeline(conversation_id, is_group) as data:
        battle = StorageBackend.get_active_battle(data)
        if battle is None:
            return None
        battle.setdefault("scheduled_events", []).append(event)
    return event


async def execute_scheduled_events(
    conversation_id: str,
    current_time: float,
    user_id: str | None = None,
    is_group: bool = True,
) -> list[str]:
    """
    结算到期（current_time >= end_time）的时间模式事件

    Args:
        current_time: 战斗当前时间点（由调用方实时计算）
        user_id: 指定时只结算该用户的事件

    Returns:
        list[str]: 到期提示消息
    """
    battle = _load_active_battle(conversation_id, is_group)
    if battle is None or not any(
        _is_due(e, current_time, user_id) for e in battle.get("scheduled_events", [])
    ):
        return []

    async with StorageBackend.edit_battle_timeline(conversation_id, is_group) as data:
        battle = StorageBackend.get_active_battle(data) or {}
        events = battle.get("scheduled_events", [])
        due = [e for e in events if _is_due(e, current_time, user_id)]
        battle["scheduled_events"] = [
            e for e in events if not _is_due(e, current_time, user_id)
        ]

    # 回调会修改角色存档，在释放战斗文件锁之后执行
    return await _run_callbacks(due)


async def decrement_count_based_events(
    conversation_id: str, user_id: str, character_name: str, is_group: bool = True
) -> list[str]:
    """
    指定角色行动一次：其次数模式事件剩余次数减 1，耗尽的事件执行回调并移除

    Returns:
        list[str]: 次数耗尽的事件提示消息
    """
    battle = _load_active_battle(conversation_id, is_group)
    if battle is None or not any(
        _is_counted_for(e, user_id, character_name)
        for e in battle.get("scheduled_events", [])
    ):
        return []

    async with StorageBackend.edit_battle_timeline(conversation_id, is_group) as data:
        battle = StorageBackend.get_active_battle(data) or {}
        remaining, exhausted = [], []
        for event in battle.get("scheduled_events", []):
            if _is_counted_for(event, user_id, character_name):
                event["remaining_count"] -= 1
                if event["remaining_count"] <= 0:
                    exhausted.append(event)
                    continue
            remaining.append(event)
        battle["scheduled_events"] = remaining

    return await _run_callbacks(exhausted)


async def restore_count_based_events(
    conversation_id: str, user_id: str, character_name: str, is_group: bool = True
) -> None:
    """撤销行动时，把指定角色次数模式事件的剩余次数加回 1"""
    battle = _load_active_battle(conversation_id, is_group)
    if battle is None or not any(
        _is_counted_for(e, user_id, character_name)
        for e in battle.get("scheduled_events", [])
    ):
        return

    async with StorageBackend.edit_battle_timeline(conversation_id, is_group) as data:
        battle = StorageBackend.get_active_battle(data) or {}
        for event in battle.get("scheduled_events", []):
            if _is_counted_for(event, user_id, character_name):
                event["remaining_count"] += 1
