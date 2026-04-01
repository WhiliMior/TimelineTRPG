"""
时间线核心计算模块 - 提供时间线的即时计算功能

此模块作为 battle.py 的共享层，承担对时间线数据的即时计算。
所有计算结果均通过方法获取，不依赖持久化存储。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..battle import BattleModule


class TimelineCore:
    """
    时间线核心计算器

    提供时间线的即时计算功能，供 BattleModule 内部使用。
    所有方法均为纯计算函数，根据传入的 battle 数据进行计算，不修改原始数据。
    """

    def __init__(self, battle_module: "BattleModule | None" = None):
        self._battle = battle_module

    def get_latest_action_end_time(
        self, battle: dict, user_id: str, character_name: str
    ) -> float:
        """
        获取指定角色最新行动的结束时间

        用于新增行动时计算起始时间。

        Args:
            battle: 战斗数据字典
            user_id: 用户ID
            character_name: 角色名

        Returns:
            float: 最新行动的结束时间（秒），如果没有行动则返回0
        """
        timeline = battle.get("timeline", {})
        if not timeline:
            return 0.0

        latest_end_time = 0.0
        for time_str, actions in timeline.items():
            end_time = float(time_str)
            for action in actions:
                if (
                    action.get("user_id") == user_id
                    and str(action.get("character_name")) == character_name
                ):
                    if end_time > latest_end_time:
                        latest_end_time = end_time

        return latest_end_time

    def get_current_time(self, battle: dict) -> float:
        """
        获取当前时间（所有角色最新行动结束时间的最小值）

        当前时间定义为：对于所有参与战斗的每个唯一角色，
        他们最新行动的结束时间的最小值。
        这表示下一个需要处理的角色。

        Args:
            battle: 战斗数据字典

        Returns:
            float: 当前时间（秒）
        """
        timeline = battle.get("timeline", {})
        participants = battle.get("participants", {})

        if not timeline:
            return 0.0

        # 按角色分组，获取每个角色的最新行动
        latest_action_by_character: dict[tuple[str, str], float] = {}

        for time_str, actions in timeline.items():
            end_time = float(time_str)
            for action in actions:
                user_id = action.get("user_id", "")
                char_name = action.get("character_name", "")
                key = (user_id, char_name)
                if key not in latest_action_by_character or end_time > latest_action_by_character[key]:
                    latest_action_by_character[key] = end_time

        # 收集所有"参与中"角色的最新行动结束时间
        end_times = []
        for (user_id, char_name), end_time in latest_action_by_character.items():
            char_info = participants.get(user_id, {}).get(char_name, {})
            if char_info.get("status") == "参与中":
                end_times.append(end_time)

        if end_times:
            return min(end_times)
        return 0.0

    def get_max_time(self, battle: dict) -> float:
        """
        获取时间线最大时间（所有角色最新行动结束时间的最大值）

        最大时间定义为：对于所有参与战斗的每个唯一角色，
        他们最新行动的结束时间的最大值。

        Args:
            battle: 战斗数据字典

        Returns:
            float: 最大时间（秒）
        """
        timeline = battle.get("timeline", {})
        participants = battle.get("participants", {})

        if not timeline:
            return 0.0

        # 按角色分组，获取每个角色的最新行动
        latest_action_by_character: dict[tuple[str, str], float] = {}

        for time_str, actions in timeline.items():
            end_time = float(time_str)
            for action in actions:
                user_id = action.get("user_id", "")
                char_name = action.get("character_name", "")
                key = (user_id, char_name)
                if key not in latest_action_by_character or end_time > latest_action_by_character[key]:
                    latest_action_by_character[key] = end_time

        # 收集所有"参与中"角色的最新行动结束时间
        end_times = []
        for (user_id, char_name), end_time in latest_action_by_character.items():
            char_info = participants.get(user_id, {}).get(char_name, {})
            if char_info.get("status") == "参与中":
                end_times.append(end_time)

        if end_times:
            return max(end_times)
        return 0.0


# 全局实例会在 BattleModule 初始化时创建
timeline_core: TimelineCore | None = None


def init_timeline_core(battle_module: "BattleModule") -> TimelineCore:
    """初始化 timeline_core 实例属性"""
    battle_module._timeline_core = TimelineCore(battle_module)
    return battle_module._timeline_core
