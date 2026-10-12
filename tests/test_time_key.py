import pytest

from timeline_trpg.trpg.infrastructure.config.game_config import game_config
from timeline_trpg.trpg.infrastructure.storage import StorageBackend
from timeline_trpg.trpg.service.battle.battle import battle_module
from timeline_trpg.trpg.service.battle.core import TimelineCore
from timeline_trpg.trpg.service.battle.timeline import timeline_module


@pytest.fixture
def time_precision(monkeypatch):
    def _set(precision: int):
        monkeypatch.setitem(
            game_config._config["timeline_precision"], "time", precision
        )

    return _set


@pytest.mark.parametrize(
    ("precision", "value", "expected"),
    [(0, 10, "10"), (0, 9.6, "10"), (1, 10, "10.0"), (2, 10.25, "10.25")],
)
def test_time_key(time_precision, precision, value, expected):
    time_precision(precision)
    assert game_config.time_key(value) == expected


def test_timeline_slot_reuses_numerically_equal_key(time_precision):
    time_precision(0)
    battle = {"timeline": {"10.0": [{"a": 1}]}}
    TimelineCore.timeline_slot(battle, 10).append({"b": 2})
    assert list(battle["timeline"]) == ["10.0"]
    assert len(battle["timeline"]["10.0"]) == 2


@pytest.mark.parametrize("precision", [0, 1, 2])
def test_actions_visible_at_any_precision(
    precision, time_precision, make_ctx, run, create_character
):
    time_precision(precision)
    create_character()
    run(timeline_module.tl(make_ctx("tl", "new", "测试")))
    run(battle_module.bt(make_ctx("bt", "in")))
    run(battle_module.bt(make_ctx("bt", "力量", "10t", "冲锋")))

    data = StorageBackend.load_battle_timeline("g1", True)
    battle = data["battle_list"][data["active_battle_id"]]
    assert list(battle["timeline"]) == [game_config.time_key(10)]

    ctx = make_ctx("tl", "show")
    run(timeline_module.tl(ctx))
    assert "冲锋" in ctx.get_reply_texts()[0]
