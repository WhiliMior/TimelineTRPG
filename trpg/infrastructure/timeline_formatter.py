"""
时间线格式化器 - 统一管理时间线显示格式

提供统一的时间轴显示功能，供 battle.py 和 timeline.py 使用。
"""

from typing import Dict, List, Optional, Any
from .config.game_config import game_config


class TimelineFormatter:
    """
    时间线格式化器

    提供统一的时间轴显示方法，支持属性/武器/时间线三种模式的格式化。
    """

    @staticmethod
    def format_timeline(
        battle: Dict,
        attribute_label: str = "属性",
        extra_info: Optional[Dict] = None,
    ) -> str:
        """
        格式化时间轴显示

        Args:
            battle: 战斗数据字典
            attribute_label: 属性列的显示标签（默认"属性"，wp模式为"武器"）
            extra_info: 额外信息字典，用于显示弹药等（如 {"ammo": "当前/总数"}）

        Returns:
            str: 格式化后的时间轴字符串
        """
        timeline = battle.get("timeline", {})
        if not timeline:
            return TimelineFormatter._get_empty_message()

        # 按时间点排序
        sorted_times = sorted([float(t) for t in timeline.keys()])

        current_time = battle.get("current_time", 0)
        max_time = battle.get("max_time", 0)

        lines = [
            TimelineFormatter._get_header(battle.get("name", "未知战斗")),
            TimelineFormatter._get_time_info(current_time, max_time),
        ]

        for time_point in sorted_times:
            if time_point < current_time:
                continue

            time_str = TimelineFormatter._format_time_str(time_point)
            actions = timeline.get(time_str, [])

            if actions:
                # 过滤：只显示每个角色在该时间点的最新行动
                latest_actions_by_character = {}
                for action in actions:
                    key = (action["user_id"], action["character_name"])
                    latest_actions_by_character[key] = action

                # 时间分隔符
                dashes = "—" * 5
                lines.append(f"\n{dashes} {time_str}t {dashes}")

                for (user_id, char_name), action in latest_actions_by_character.items():
                    # 检查角色状态
                    user_participants = battle["participants"].get(user_id, {})
                    char_info = user_participants.get(char_name, {})

                    if char_info.get("status") != "参与中":
                        continue

                    # 获取行动详情
                    action_lines = TimelineFormatter._format_action(
                        action, attribute_label
                    )
                    lines.extend(action_lines)

        # 显示定时事件
        scheduled_events = battle.get("scheduled_events", [])
        if scheduled_events:
            event_lines = TimelineFormatter._format_scheduled_events(
                scheduled_events, current_time
            )
            lines.extend(event_lines)

        # 添加额外信息（如弹药）
        if extra_info:
            lines.append(TimelineFormatter._format_extra_info(extra_info))

        return "\n".join(lines)

    @staticmethod
    def _get_empty_message() -> str:
        """获取空时间线消息"""
        from ..adapter.message import ReplyManager

        reply = ReplyManager("battle")
        return reply.render("empty_timeline")

    @staticmethod
    def _get_header(name: str) -> str:
        """获取时间线头部"""
        from ..adapter.message import ReplyManager

        reply = ReplyManager("battle")
        return reply.render("timeline_header", name=name)

    @staticmethod
    def _get_time_info(current_time: float, max_time: float) -> str:
        """获取时间信息"""
        from ..adapter.message import ReplyManager

        reply = ReplyManager("battle")
        current = game_config.round_value(current_time, "time")
        max_val = game_config.round_value(max_time, "time")
        return reply.render("timeline_current_max_time", current=current, max=max_val)

    @staticmethod
    def _format_time_str(time_point: float) -> str:
        """格式化时间点字符串"""
        return (
            f"{time_point:.1f}" if time_point.is_integer() else f"{time_point}"
        )

    @staticmethod
    def _format_action(action: Dict, attribute_label: str) -> List[str]:
        """
        格式化单个行动

        Args:
            action: 行动字典
            attribute_label: 属性标签（"属性"或"武器"）

        Returns:
            List[str]: 格式化后的行列表
        """
        lines = []

        # 基础信息
        start_time = game_config.round_value(action.get("start_time", 0), "time")
        lead_time = game_config.round_value(action.get("lead_time", 0), "time")
        impact_value = game_config.round_value(action.get("impact_value", 0), "impact")

        char_name = action.get("character_name", "未知")
        lines.append(f"  [{char_name}]")
        lines.append(f"    起始: {start_time}t | 前摇: {lead_time}t")

        # 属性/武器显示
        if action.get("using_weapon"):
            # 武器模式
            weapon_name = action.get("weapon", "")
            lines.append(f"    武器: {weapon_name} | 影响: {impact_value}")
        else:
            # 普通属性模式
            attr_used = action.get("attribute_used", "")
            lines.append(f"    {attribute_label}: {attr_used} | 影响: {impact_value}")

        # 备注
        if action.get("notes"):
            lines.append(f"    {action['notes']}")

        return lines

    @staticmethod
    def _format_scheduled_events(
        scheduled_events: List[Dict], current_time: float
    ) -> List[str]:
        """格式化定时事件"""
        lines = []

        time_based_events = [
            e
            for e in scheduled_events
            if e.get("mode") == "time_based"
            and e.get("end_time")
            and current_time < e.get("end_time", 0)
        ]

        if time_based_events:
            lines.append("\n【定时事件】")
            for event in time_based_events:
                # 优先显示回调消息，否则显示行动描述
                event_desc = event.get("callback_message") or event.get(
                    "action_description", ""
                )
                end_time = game_config.round_value(event.get("end_time", 0), "time")
                lines.append(f"  {end_time}t - {event_desc}")

        return lines

    @staticmethod
    def _format_extra_info(extra_info: Dict) -> str:
        """格式化额外信息（如弹药）"""
        lines = []

        # 弹药信息
        if "ammo" in extra_info:
            ammo = extra_info["ammo"]
            if isinstance(ammo, dict):
                current = ammo.get("current", 0)
                max_ammo = ammo.get("max", 0)
                lines.append(f"\n[弹药: {current}/{max_ammo}]")
            elif isinstance(ammo, str):
                lines.append(f"\n[{ammo}]")

        return "\n".join(lines)


# 全局格式化器实例
timeline_formatter = TimelineFormatter()
