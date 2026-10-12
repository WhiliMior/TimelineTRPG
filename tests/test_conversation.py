import json

from timeline_trpg.trpg.infrastructure.storage import StorageBackend
from timeline_trpg.trpg.service.battle.battle import battle_module
from timeline_trpg.trpg.service.battle.timeline import timeline_module
from timeline_trpg.trpg.service.inventory.inventory import inventory_module


def test_context_properties(make_ctx):
    group = make_ctx("r", group_id="g1")
    private = make_ctx("r", group_id="")
    assert (group.is_group, group.conversation_id, group.session_type) == (
        True,
        "g1",
        "group",
    )
    assert (private.is_group, private.conversation_id, private.session_type) == (
        False,
        "u1",
        "private",
    )


def test_private_battle_saved_under_private(data_dir, make_ctx, run, create_character):
    create_character()
    run(timeline_module.tl(make_ctx("tl", "new", "单人练习", group_id="")))
    run(battle_module.bt(make_ctx("bt", "in", group_id="")))
    run(battle_module.bt(make_ctx("bt", "力量", "5t", group_id="")))

    assert (data_dir / "BattleTimeline" / "Private" / "u1" / "data.json").exists()
    assert not (data_dir / "BattleTimeline" / "Group" / "u1").exists()

    ctx = make_ctx("tl", "show", group_id="")
    run(timeline_module.tl(ctx))
    assert "单人练习" in ctx.get_reply_texts()[0]


def _write_legacy_battle(data_dir, conversation_id, participants):
    path = data_dir / "BattleTimeline" / "Group" / conversation_id / "data.json"
    path.parent.mkdir(parents=True)
    battle = {
        "name": "旧战斗",
        "participants": {uid: {"勇者": {"status": "参与中"}} for uid in participants},
        "timeline": {},
        "scheduled_events": [],
    }
    path.write_text(
        json.dumps(
            {"active_battle_id": "1", "player": {}, "battle_list": {"1": battle}}
        ),
        encoding="utf-8",
    )
    return path


def test_legacy_private_battle_is_migrated(data_dir):
    legacy = _write_legacy_battle(data_dir, "u1", ["u1"])
    data = StorageBackend.load_battle_timeline("u1", is_group=False)
    assert StorageBackend.get_active_battle(data)["name"] == "旧战斗"
    assert not legacy.exists()


def test_group_battle_with_same_id_is_not_migrated(data_dir):
    legacy = _write_legacy_battle(data_dir, "u1", ["u1", "u2"])
    data = StorageBackend.load_battle_timeline("u1", is_group=False)
    assert StorageBackend.get_active_battle(data) is None
    assert legacy.exists()


def test_legacy_private_weights_are_copied(data_dir, make_ctx, run, create_character):
    legacy = data_dir / "Inventory" / "Group" / "u1" / "weights.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"绳索": 1.5}), encoding="utf-8")

    create_character()
    ctx = make_ctx("i", "绳索", "+1", group_id="")
    run(inventory_module.i(ctx))
    assert "1.5" in ctx.get_reply_texts()[0]
    assert legacy.exists()
