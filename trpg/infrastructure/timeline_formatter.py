"""
时间线格式化器 - 统一管理时间线显示格式

提供统一的时间轴显示功能，供 battle.py 和 timeline.py 使用。
"""

from .config.game_config import game_config
from .text_style import DIVIDER, clip_lines, title, wrap


class TimelineFormatter:
    """
    时间线格式化器

    紧凑版（适配手机屏幕）：每个行动两行，定时事件按到期时间排序并标注剩余时间。

        【森林遭遇】当前2t/最大8t
        ──────
        5t [游侠] 长弓 影响12
          2.5t起 前摇2.5t 齐射
        ──────
        【定时】
        5t 勇者 力量+5（剩3t）
        ×2 法师 护甲15%
    """

    @staticmethod
    def format_timeline(
        battle: dict,
        attribute_label: str = "属性",
        extra_info: dict | None = None,
    ) -> str:
        """
        格式化时间轴显示

        Args:
            battle: 战斗数据字典（current_time / max_time 需由调用方实时计算后填入）
            attribute_label: 保留参数，武器行动会自动显示武器名
            extra_info: 额外信息字典，用于显示弹药等（如 {"ammo": "当前/总数"}）

        Returns:
            str: 格式化后的时间轴字符串
        """
        reply = _reply()
        current_time = battle.get("current_time", 0)
        lines = [
            reply.render(
                "timeline_header",
                name=battle.get("name", "未知战斗"),
                current=_time(current_time),
                max=_time(battle.get("max_time", 0)),
            )
        ]

        action_lines = TimelineFormatter._format_actions(battle, current_time)
        if action_lines:
            lines.append(DIVIDER)
            lines.extend(
                clip_lines(action_lines, more_hint=reply.render("timeline_more_hint"))
            )
        else:
            lines.append(reply.render("empty_timeline"))

        event_lines = TimelineFormatter._format_scheduled_events(
            battle.get("scheduled_events", []), current_time
        )
        if event_lines:
            lines.append(DIVIDER)
            lines.append(title(reply.render("scheduled_events_title")))
            lines.extend(event_lines)

        if extra_info:
            extra = TimelineFormatter._format_extra_info(extra_info)
            if extra:
                lines.append(extra)

        return wrap("\n".join(lines))

    @staticmethod
    def _format_actions(battle: dict, current_time: float) -> list[str]:
        """每个参与中角色的最新未完成行动，按结束时间排序，每个行动两行"""
        participants = battle.get("participants", {})
        latest: dict[tuple[str, str], tuple[float, dict]] = {}
        for key, actions in (battle.get("timeline") or {}).items():
            time_point = float(key)
            if time_point < current_time:
                continue
            for action in actions:
                owner = (action.get("user_id", ""), action.get("character_name", ""))
                if owner not in latest or time_point > latest[owner][0]:
                    latest[owner] = (time_point, action)

        lines: list[str] = []
        for (user_id, char_name), (time_point, action) in sorted(
            latest.items(), key=lambda kv: kv[1][0]
        ):
            status = participants.get(user_id, {}).get(char_name, {}).get("status")
            if status != "参与中":
                continue
            lines.extend(TimelineFormatter._format_action(time_point, action))
        return lines

    @staticmethod
    def _format_action(time_point: float, action: dict) -> list[str]:
        """
        单个行动两行：
            5t [游侠] 长弓 影响12
              2.5t起 前摇2.5t 齐射
        """
        used = (
            action.get("weapon", "")
            if action.get("using_weapon")
            else action.get("attribute_used", "")
        )
        impact = game_config.round_value(action.get("impact_value", 0) or 0, "impact")
        first = (
            f"{_time(time_point)}t [{action.get('character_name', '未知')}] "
            f"{used} 影响{impact}"
        )
        second = (
            f"  {_time(action.get('start_time', 0) or 0)}t起 "
            f"前摇{_time(action.get('lead_time', 0) or 0)}t"
        )
        if action.get("notes"):
            second += f" {action['notes']}"
        return [first, second]

    @staticmethod
    def _event_text(event: dict) -> str:
        return event.get("action_description") or event.get("callback_message", "")

    @staticmethod
    def _format_scheduled_events(
        scheduled_events: list[dict], current_time: float
    ) -> list[str]:
        """时间模式按到期时间排序并标注剩余时间；次数模式显示剩余次数"""
        reply = _reply()
        timed = sorted(
            (
                e
                for e in scheduled_events
                if e.get("mode") == "time_based"
                and e.get("end_time") is not None
                and current_time < e["end_time"]
            ),
            key=lambda e: e["end_time"],
        )
        counted = [
            e
            for e in scheduled_events
            if e.get("mode") == "count_based" and (e.get("remaining_count") or 0) > 0
        ]

        lines = [
            reply.render(
                "scheduled_time_event",
                time=_time(e["end_time"]),
                desc=TimelineFormatter._event_text(e),
                remaining=_time(e["end_time"] - current_time),
            )
            for e in timed
        ]
        lines.extend(
            reply.render(
                "scheduled_count_event",
                count=e["remaining_count"],
                desc=TimelineFormatter._event_text(e),
            )
            for e in counted
        )
        return lines

    @staticmethod
    def _format_extra_info(extra_info: dict) -> str:
        """格式化额外信息（如弹药）"""
        ammo = extra_info.get("ammo")
        if isinstance(ammo, dict):
            return f"弹药：{ammo.get('current', 0)}/{ammo.get('max', 0)}"
        if isinstance(ammo, str):
            return ammo
        return ""


def _reply():
    from ..adapter.message import ReplyManager

    return ReplyManager("battle")


def _time(value: float) -> int | float:
    return game_config.round_value(float(value), "time")


def describe_expiry(event: dict | None) -> str:
    """
    描述定时事件何时失效，用于添加 buff/资源修正/护盾后的回显

    Args:
        event: scheduler.schedule_event 的返回值；None 表示没有进行中的战斗、未调度
    """
    from ..adapter.message import ReplyManager

    schedule_reply = ReplyManager("schedule")
    if not event:
        return schedule_reply.render("not_scheduled")
    if event.get("mode") == "count_based":
        return schedule_reply.render(
            "expires_after_count", count=event.get("remaining_count")
        )
    return schedule_reply.render(
        "expires_at", time=game_config.round_value(event.get("end_time", 0), "time")
    )


# 全局格式化器实例
timeline_formatter = TimelineFormatter()
