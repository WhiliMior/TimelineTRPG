import json

from timeline_trpg.trpg.infrastructure.command_dispatcher import command_dispatcher
from timeline_trpg.trpg.infrastructure.config.game_config import game_config
from timeline_trpg.trpg.service.battle.timeline import timeline_module


def _panel_config(**precision):
    from astrbot.api import AstrBotConfig

    return AstrBotConfig(precision=precision)


def test_bundled_defaults():
    assert game_config.get_precision("time") == 2
    assert game_config.get_precision("impact") == 0


def test_tl_acc_saved_to_data_dir_without_panel(data_dir, make_ctx, run):
    run(timeline_module.tl(make_ctx("tl", "acc", "1")))
    assert game_config.get_precision("time") == 1

    saved = json.loads((data_dir / "config" / "game_config.json").read_text())
    assert saved["timeline_precision"]["time"] == 1

    game_config.reset()
    assert game_config.get_precision("time") == 1


def test_panel_config_is_source_of_truth(data_dir, make_ctx, run):
    from timeline_trpg import main

    panel = _panel_config(time=0, impact=1, weight="bad")
    main.TimelineTRPG(context=None, config=panel)
    assert game_config.get_precision("time") == 0
    assert game_config.get_precision("impact") == 1
    assert game_config.get_precision("weight") == 2

    run(timeline_module.tl(make_ctx("tl", "acc", "3")))
    assert panel["precision"]["time"] == 3
    assert panel.saved == 1
    assert not (data_dir / "config" / "game_config.json").exists()


def test_terminate_cleans_global_state(run):
    from timeline_trpg import main

    plugin = main.TimelineTRPG(context=None, config=_panel_config(time=0))
    assert command_dispatcher.has_command("chr_reset")
    run(plugin.terminate())
    assert not command_dispatcher.has_command("chr_reset")
    assert game_config.get_precision("time") == 2

    main.TimelineTRPG(context=None)
    assert command_dispatcher.has_command("chr_reset")
