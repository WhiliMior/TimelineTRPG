from timeline_trpg.trpg.infrastructure.storage import StorageBackend
from timeline_trpg.trpg.service.battle.battle import battle_module
from timeline_trpg.trpg.service.battle.timeline import timeline_module
from timeline_trpg.trpg.service.buff.buff import buff_module


def _active_battle(conversation_id="g1", is_group=True):
    data = StorageBackend.load_battle_timeline(conversation_id, is_group)
    return data["battle_list"][data["active_battle_id"]]


def _setup_battle(make_ctx, run, create_character):
    create_character()
    run(timeline_module.tl(make_ctx("tl", "new", "森林遭遇")))
    run(battle_module.bt(make_ctx("bt", "in")))


def test_insert_action_does_not_crash(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    run(battle_module.bt(make_ctx("bt", "力量", "10t")))

    ctx = make_ctx("bt", "4t", "力量", "2t", "闪避")
    run(battle_module.bt(ctx))

    reply = ctx.get_reply_texts()[0]
    assert "森林遭遇" in reply
    actions = [a for acts in _active_battle()["timeline"].values() for a in acts]
    assert any("[提前终止]" in a["notes"] for a in actions)


def test_count_based_buff_decrement_is_saved(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    run(buff_module.buff(make_ctx("buff", "add", "战吼", "力量", "直接加算", "5", "3")))
    events = _active_battle()["scheduled_events"]
    assert events[0]["remaining_count"] == 3

    run(battle_module.bt(make_ctx("bt", "力量", "2t")))
    assert _active_battle()["scheduled_events"][0]["remaining_count"] == 2

    run(battle_module.bt(make_ctx("bt", "力量", "2t")))
    assert _active_battle()["scheduled_events"][0]["remaining_count"] == 1


def test_undo_restores_count_and_keeps_it(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    run(buff_module.buff(make_ctx("buff", "add", "战吼", "力量", "直接加算", "5", "3")))
    run(battle_module.bt(make_ctx("bt", "力量", "2t")))
    assert _active_battle()["scheduled_events"][0]["remaining_count"] == 2

    run(battle_module.bt(make_ctx("bt", "undo")))
    battle = _active_battle()
    assert battle["timeline"] == {}
    assert battle["scheduled_events"][0]["remaining_count"] == 3


def test_count_based_buff_expires_and_is_removed(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    run(buff_module.buff(make_ctx("buff", "add", "战吼", "力量", "直接加算", "5", "1")))
    assert len(StorageBackend.get_character("u1", "勇者")["buffs"]) == 1

    ctx = make_ctx("bt", "力量", "2t")
    run(battle_module.bt(ctx))

    assert _active_battle()["scheduled_events"] == []
    assert StorageBackend.get_character("u1", "勇者")["buffs"] == []
    assert "战吼" in ctx.get_reply_texts()[0] or "力量" in ctx.get_reply_texts()[0]


def test_timeline_get_uses_live_max_time(make_ctx, run, create_character):
    _setup_battle(make_ctx, run, create_character)
    run(battle_module.bt(make_ctx("bt", "力量", "10t")))

    ctx = make_ctx("tl", "get", "5")
    run(timeline_module.tl(ctx))
    reply = ctx.get_reply_texts()[0]
    assert "超过" not in reply
    assert "勇者" in reply
