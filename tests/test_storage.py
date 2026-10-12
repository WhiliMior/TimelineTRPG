import json

import pytest

from timeline_trpg.trpg.infrastructure.storage import (
    StorageBackend,
    StorageCorruptedError,
)
from timeline_trpg.trpg.service.examination.target import target_module


def _char_path(data_dir, user_id="u1"):
    return data_dir / "User" / user_id / "characters.json"


def test_save_is_atomic_and_leaves_no_temp_files(data_dir):
    assert StorageBackend.save_characters("u1", [{"name": "甲"}])
    path = _char_path(data_dir)
    assert json.loads(path.read_text(encoding="utf-8")) == [{"name": "甲"}]
    assert [p.name for p in path.parent.iterdir()] == ["characters.json"]


def test_failed_write_keeps_original(data_dir):
    StorageBackend.save_characters("u1", [{"name": "甲"}])
    assert not StorageBackend.save_characters("u1", [{"name": object()}])
    assert StorageBackend.load_characters("u1") == [{"name": "甲"}]
    assert len(list(_char_path(data_dir).parent.iterdir())) == 1


def test_corrupted_file_is_backed_up_and_not_overwritten(data_dir):
    path = _char_path(data_dir)
    path.parent.mkdir(parents=True)
    path.write_text('[{"name": "甲"', encoding="utf-8")

    with pytest.raises(StorageCorruptedError) as err:
        StorageBackend.load_characters("u1")

    backup = err.value.backup_path
    assert backup is not None and backup.exists()
    assert backup.read_text(encoding="utf-8") == '[{"name": "甲"'
    assert not path.exists()


def test_wrong_structure_is_treated_as_corrupted(data_dir):
    path = _char_path(data_dir)
    path.parent.mkdir(parents=True)
    path.write_text('{"name": "甲"}', encoding="utf-8")
    with pytest.raises(StorageCorruptedError):
        StorageBackend.load_characters("u1")


def test_corrupted_file_gives_player_a_clear_message(data_dir, make_ctx, run):
    from timeline_trpg import main

    path = _char_path(data_dir)
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")

    plugin = main.TimelineTRPG(context=None)
    ctx = make_ctx("chr")
    run(plugin.router.dispatch(ctx))
    assert ctx.get_reply_texts() == [plugin.system_reply.render("data_corrupted")]


def test_battle_timeline_has_schema_version(data_dir):
    data = StorageBackend.load_battle_timeline("g1", True)
    assert data["schema_version"] == 1
    StorageBackend.save_battle_timeline("g1", data, True)
    raw = json.loads(
        (data_dir / "BattleTimeline" / "Group" / "g1" / "data.json").read_text()
    )
    assert raw["schema_version"] == 1


def test_edit_battle_timeline_saves_on_exit(run):
    async def scenario():
        async with StorageBackend.edit_battle_timeline("g1", True) as data:
            data["active_battle_id"] = "42"

    run(scenario())
    assert StorageBackend.load_battle_timeline("g1", True)["active_battle_id"] == "42"


def test_edit_does_not_save_when_block_fails(run):
    async def scenario():
        async with StorageBackend.edit_battle_timeline("g1", True) as data:
            data["active_battle_id"] = "42"
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run(scenario())
    assert StorageBackend.load_battle_timeline("g1", True)["active_battle_id"] is None


def test_target_is_stored_per_conversation(make_ctx, run):
    run(target_module.tar(make_ctx("tar", "30", group_id="g1")))
    run(target_module.tar(make_ctx("tar", "50", group_id="g2")))

    assert StorageBackend.load_target("g1", "group") == {"target_value": 30}
    assert StorageBackend.load_target("g2", "group") == {"target_value": 50}


def test_legacy_global_target_is_migrated(data_dir):
    legacy = data_dir / "Examination" / "target.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"group": {"g1": {"target_value": 12}}, "private": {}}),
        encoding="utf-8",
    )

    assert StorageBackend.load_target("g1", "group") == {"target_value": 12}
    assert (data_dir / "Examination" / "Group" / "g1" / "target.json").exists()
    assert StorageBackend.load_target("g2", "group") == {}


def test_negotiation_without_target_does_not_crash(make_ctx, run):
    from timeline_trpg.trpg.service.negotiation.negotiation import negotiation_module

    ctx = make_ctx("neg")
    run(negotiation_module.neg(ctx))
    assert "未设定" in ctx.get_reply_texts()[0]
