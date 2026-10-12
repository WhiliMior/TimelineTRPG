from timeline_trpg.trpg.infrastructure import scheduler
from timeline_trpg.trpg.infrastructure.storage import StorageBackend
from timeline_trpg.trpg.service.battle.battle import battle_module
from timeline_trpg.trpg.service.battle.timeline import timeline_module
from timeline_trpg.trpg.service.buff.buff import buff_module
from timeline_trpg.trpg.service.resource.modifier import resource_modifier_module

CALLS: list[dict] = []


async def record_async(**kwargs):
    CALLS.append(kwargs)


def _active_battle(conversation_id="g1", is_group=True):
    data = StorageBackend.load_battle_timeline(conversation_id, is_group)
    return StorageBackend.get_active_battle(data)


def _setup_battle(make_ctx, run, create_character):
    create_character()
    run(timeline_module.tl(make_ctx("tl", "new", "森林遭遇")))
    run(battle_module.bt(make_ctx("bt", "in")))


def _schedule(run, end_offset, current_time=0.0, **kwargs):
    return run(
        scheduler.schedule_event(
            "g1",
            "u1",
            "勇者",
            "测试",
            end_offset,
            f"{__name__}.record_async",
            {"tag": kwargs.pop("tag", "x")},
            "测试到期",
            current_time=current_time,
            **kwargs,
        )
    )


def test_schedule_without_battle_returns_none(run):
    assert _schedule(run, 5) is None


def test_time_based_event_expires_at_end_time(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    CALLS.clear()
    event = _schedule(run, 5, current_time=2)
    assert event["end_time"] == 7

    assert run(scheduler.execute_scheduled_events("g1", 6.9)) == []
    assert CALLS == []

    assert run(scheduler.execute_scheduled_events("g1", 7)) == ["测试到期"]
    assert CALLS == [{"tag": "x"}]
    assert _active_battle()["scheduled_events"] == []


def test_execute_only_for_given_user(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    _schedule(run, 1)
    assert run(scheduler.execute_scheduled_events("g1", 10, user_id="u2")) == []
    assert len(_active_battle()["scheduled_events"]) == 1


def test_failing_callback_still_removes_event(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    run(
        scheduler.schedule_event(
            "g1",
            "u1",
            "勇者",
            "测试",
            1,
            "trpg.service.does_not_exist.func",
            {},
            "坏回调",
            current_time=0,
        )
    )
    assert run(scheduler.execute_scheduled_events("g1", 5)) == ["坏回调"]
    assert _active_battle()["scheduled_events"] == []


def test_time_based_buff_expires_after_actions(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    run(
        buff_module.buff(make_ctx("buff", "add", "战吼", "力量", "直接加算", "5", "4t"))
    )
    assert _active_battle()["scheduled_events"][0]["end_time"] == 4

    run(battle_module.bt(make_ctx("bt", "力量", "3t")))
    assert len(StorageBackend.get_character("u1", "勇者")["buffs"]) == 1

    ctx = make_ctx("bt", "力量", "1t")
    run(battle_module.bt(ctx))
    assert StorageBackend.get_character("u1", "勇者")["buffs"] == []
    assert "战吼" in ctx.get_reply_texts()[0] or "力量" in ctx.get_reply_texts()[0]


def test_expired_modifier_removed_after_switching_character(
    make_ctx, run, create_character
):
    _setup_battle(make_ctx, run, create_character)
    run(
        resource_modifier_module.dr(
            make_ctx("dr", "add", "铠甲", "hp", "5", "所有", "2t")
        )
    )
    assert StorageBackend.get_character("u1", "勇者")["resource_modifiers"]

    create_character(spec="名称:法师,等级:1,物理思维比值:500,体质:40,意志:60")
    current_time = 2
    run(scheduler.execute_scheduled_events("g1", current_time))
    assert StorageBackend.get_character("u1", "勇者")["resource_modifiers"] == []
