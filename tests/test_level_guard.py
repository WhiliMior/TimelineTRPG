from timeline_trpg.trpg.infrastructure.character_reader import CharacterReader
from timeline_trpg.trpg.service.buff.buff import buff_module
from timeline_trpg.trpg.service.negotiation.negotiation import negotiation_module
from timeline_trpg.trpg.service.resource.modifier import resource_modifier_module
from timeline_trpg.trpg.service.resource.resource import resource_record_module


def test_effective_level_never_below_one():
    assert CharacterReader.effective_level({"等级": 0}) == 1
    assert CharacterReader.effective_level({"等级": "abc"}) == 1
    assert CharacterReader.effective_level({}) == 1
    assert CharacterReader.effective_level({"等级": 3}) == 3


def test_defense_modifier_with_level_zero():
    data = {"等级": 0}
    value = {"raw": "10d", "type": "defense"}
    assert resource_modifier_module._calculate_modifier_value(value, data, "+hp") == 1
    assert (
        resource_record_module._calculate_modifier_value_from_raw(value, data, "-hp")
        == 10 / 20
    )


def test_level_based_buff_with_level_zero(make_ctx, run, create_character):
    create_character(spec="名称:零级,等级:0,力量:30")
    ctx = make_ctx("buff", "add", "祝福", "力量", "5d")
    run(buff_module.buff(ctx))
    assert "祝福" in ctx.get_reply_texts()[0]


def test_negotiation_with_zero_target_level():
    rate = negotiation_module._calculate_success_rate(5, 10, 50, 0, 0)
    assert rate > 0
