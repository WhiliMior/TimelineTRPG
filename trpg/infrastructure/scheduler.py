"""
定时事件调度器 - 管理战斗中的定时事件
迁移自老项目 Game/Runtime/Battle/BattleSystem.py 中的定时事件功能

功能：
- 调度带持续时间的buff事件
- 调度带持续时间的护盾事件
- 调度带持续时间的资源修饰事件
- 执行到期的定时事件回调

使用方式：
- 每个业务模块在调用 schedule_event 时传入 callback_path（模块路径字符串）
- 回调函数会被持久化存储在 battle json 中
- 执行时根据 callback_path 动态计算相对导入层级并调用回调函数
- infrastructure 层统一处理异步事件循环问题，各模块回调函数只需同步执行
"""

import asyncio
import time

from ..adapter.message import ReplyManager
from .storage import StorageBackend


def _execute_callback(callback_path: str, callback_args: dict):
    """
    执行回调函数（统一处理异步事件循环）

    Args:
        callback_path: 回调函数路径，格式如 "trpg.service.buff.buff.remove_expired_buff"
        callback_args: 回调函数参数
    """
    import importlib
    import sys

    # 解析模块路径和函数名
    parts = callback_path.rsplit(".", 1)
    if len(parts) != 2:
        return

    module_path, function_name = parts

    # 首先尝试直接导入模块路径
    full_module_path = module_path

    # 使用 importlib 动态导入模块和函数
    try:
        module = importlib.import_module(full_module_path)
        callback_func = getattr(module, function_name)

        # 检查是否为协程函数
        if asyncio.iscoroutinefunction(callback_func):
            # 统一处理异步函数的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 已有运行中的loop，使用 ensure_future 在后台调度
                asyncio.ensure_future(callback_func(**callback_args), loop=loop)
                return
            except RuntimeError:
                # 没有运行中的loop，可以安全使用 run_until_complete
                pass

            # 没有运行中的loop
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    loop.run_until_complete(callback_func(**callback_args))
                    return
            except RuntimeError:
                pass

            # 创建新的事件循环
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(callback_func(**callback_args))
            finally:
                new_loop.close()
        else:
            # 同步函数直接调用
            callback_func(**callback_args)
    except Exception as e:
        print(f"Error executing callback {callback_path}: {e}")


class SchedulerModule:
    """
    定时事件调度器模块

    提供统一的定时事件调度和执行功能，
    避免 service 模块之间的循环引用。
    """

    def __init__(self):
        self.system_reply = ReplyManager("system")

    def schedule_event(
        self,
        conversation_id: str,
        user_id: str,
        character_name: str,
        action_description: str,
        duration_or_count: float,
        callback_path: str,
        callback_args: dict,
        callback_message: str,
        mode: str = "time_based",
        event_type: str = "general",
        is_group: bool = True,
    ) -> bool:
        """
        调度一个定时事件

        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            character_name: 角色名
            action_description: 行动描述
            duration_or_count: 持续时间或生效次数
            callback_path: 回调函数路径
            callback_args: 回调函数参数
            callback_message: 回调执行提示
            mode: 模式 ('time_based' 或 'count_based')
            event_type: 事件类型 ('general', 'buff', 'shield', 'modifier')
            is_group: 是否为群聊

        Returns:
            bool: 是否成功调度
        """
        storage_key = conversation_id
        battle = self._get_battle(storage_key, is_group)

        if not battle.get("name"):
            return False

        # 获取当前时间点
        current_time = battle.get("current_time", 0)

        # 创建事件对象
        event = {
            "id": f"event_{int(time.time())}_{len(battle.get('scheduled_events', []))}",
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

        if mode == "time_based":
            # 持续时间模式：当前时间 + 持续时间 = 结束时间
            event["end_time"] = current_time + duration_or_count
            event["remaining_count"] = None
        elif mode == "count_based":
            # 生效次数模式：记录剩余次数
            event["remaining_count"] = int(duration_or_count)
            event["end_time"] = None
        else:
            return False

        # 添加到事件列表
        if "scheduled_events" not in battle:
            battle["scheduled_events"] = []
        battle["scheduled_events"].append(event)

        # 保存
        self._save_battle(storage_key, battle, is_group)
        return True

    def execute_scheduled_events(
        self, conversation_id: str, user_id: str = None, is_group: bool = True
    ) -> list[str]:
        """
        执行到期的定时事件

        Args:
            conversation_id: 会话ID
            user_id: 用户ID，如果指定则只执行该用户的到期事件
            is_group: 是否为群聊

        Returns:
            List[str]: 执行结果消息列表
        """
        storage_key = conversation_id
        battle = self._get_battle(storage_key, is_group)

        if not battle.get("name"):
            return []

        current_time = battle.get("current_time", 0)
        scheduled_events = battle.get("scheduled_events", [])

        executed_messages = []
        events_to_remove = []

        for i, event in enumerate(scheduled_events):
            # 检查是否为时间模式且已到期（大于结束时间，而非大于等于）
            if (
                event.get("mode") == "time_based"
                and event.get("end_time") is not None
                and current_time > event.get("end_time", 0)
            ):
                # 如果指定了用户ID，只执行该用户的事件
                if user_id is not None and event.get("user_id") != user_id:
                    continue

                # 执行回调
                if "callback_path" in event and event["callback_path"]:
                    try:
                        callback_path = event["callback_path"]
                        callback_args = event.get("callback_args", {})

                        _execute_callback(callback_path, callback_args)
                        executed_messages.append(event.get("callback_message", ""))
                    except Exception as e:
                        print(f"Error executing scheduled event callback: {e}")

                # 标记为删除
                events_to_remove.append(i)

        # 从后往前删除已执行的事件
        for i in reversed(events_to_remove):
            if i < len(scheduled_events):
                del scheduled_events[i]

        # 保存更新后的事件列表
        if events_to_remove:
            battle["scheduled_events"] = scheduled_events
            self._save_battle(storage_key, battle, is_group)

        return executed_messages

    def decrement_count_based_events(
        self,
        conversation_id: str,
        user_id: str,
        character_name: str,
        is_group: bool = True,
    ) -> list[str]:
        """
        递减指定角色的次数模式事件的剩余次数，并执行到期的回调

        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            character_name: 角色名
            is_group: 是否为群聊

        Returns:
            List[str]: 执行结果消息列表（次数耗尽时执行的回调消息）
        """
        storage_key = conversation_id
        battle = self._get_battle(storage_key, is_group)

        if not battle.get("name"):
            return []

        scheduled_events = battle.get("scheduled_events", [])
        executed_messages = []
        events_to_remove = []

        for i, event in enumerate(scheduled_events):
            # 检查是否为该用户和角色的次数模式事件
            if (
                event.get("user_id") == user_id
                and event.get("character_name") == character_name
                and event.get("mode") == "count_based"
                and event.get("remaining_count") is not None
            ):
                # 递减剩余次数
                event["remaining_count"] -= 1

                # 检查是否已达到次数限制
                if event["remaining_count"] <= 0:
                    # 执行回调
                    if "callback_path" in event and event["callback_path"]:
                        try:
                            callback_path = event["callback_path"]
                            callback_args = event.get("callback_args", {})

                            _execute_callback(callback_path, callback_args)
                            executed_messages.append(event.get("callback_message", ""))
                        except Exception as e:
                            print(f"Error executing count_based event callback: {e}")

                    # 标记为删除
                    events_to_remove.append(i)

        # 从后往前删除次数耗尽的事件
        for i in reversed(events_to_remove):
            if i < len(scheduled_events):
                del scheduled_events[i]

        # 保存更新后的事件列表
        # 无论是否有事件被删除，都需要保存递减后的数据
        self._save_battle(storage_key, battle, is_group)

        return executed_messages

    def _get_battle(self, storage_key: str, is_group: bool = True) -> dict:
        """获取战斗数据"""
        data = StorageBackend.load_battle_timeline(storage_key, is_group)
        if not data.get("battle_list"):
            data["battle_list"] = {}

        active_battle_id = data.get("active_battle_id")

        if active_battle_id and active_battle_id in data["battle_list"]:
            return data["battle_list"][active_battle_id]
        else:
            return {
                "name": None,
                "participants": {},
                "timeline": {},
                "current_time": 0,
                "max_time": 0,
                "scheduled_events": [],
            }

    def _save_battle(self, storage_key: str, battle: dict, is_group: bool = True):
        """保存战斗数据"""
        data = StorageBackend.load_battle_timeline(storage_key, is_group)

        if not data.get("battle_list"):
            data["battle_list"] = {}
        if "player" not in data:
            data["player"] = {}

        active_battle_id = data.get("active_battle_id")

        if active_battle_id:
            data["battle_list"][active_battle_id] = battle
        else:
            new_battle_id = str(int(time.time()))
            data["active_battle_id"] = new_battle_id
            data["battle_list"][new_battle_id] = battle

        StorageBackend.save_battle_timeline(storage_key, data, is_group)


# 创建模块实例
scheduler_module = SchedulerModule()


def execute_scheduled_events(
    conversation_id: str, user_id: str = None, is_group: bool = True
) -> list[str]:
    """
    执行到期的定时事件（便捷函数）
    """
    return scheduler_module.execute_scheduled_events(conversation_id, user_id, is_group)


def schedule_event(
    conversation_id: str,
    user_id: str,
    character_name: str,
    action_description: str,
    duration_or_count: float,
    callback_path: str,
    callback_args: dict,
    callback_message: str,
    mode: str = "time_based",
    event_type: str = "general",
    is_group: bool = True,
) -> bool:
    """
    调度一个定时事件（便捷函数）
    """
    return scheduler_module.schedule_event(
        conversation_id,
        user_id,
        character_name,
        action_description,
        duration_or_count,
        callback_path,
        callback_args,
        callback_message,
        mode,
        event_type,
        is_group,
    )


def decrement_count_based_events(
    conversation_id: str, user_id: str, character_name: str, is_group: bool = True
) -> list[str]:
    """
    递减指定角色的次数模式事件的剩余次数（便捷函数）

    Args:
        conversation_id: 会话ID
        user_id: 用户ID
        character_name: 角色名
        is_group: 是否为群聊

    Returns:
        List[str]: 执行结果消息列表
    """
    return scheduler_module.decrement_count_based_events(
        conversation_id, user_id, character_name, is_group
    )
