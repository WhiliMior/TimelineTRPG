"""
QQ 移动端排版回归测试

按真实指令走一遍完整流程（经由插件 Router 分发），检查每条回复：
- 每行不超过 18 个汉字宽（36 个半角单位）
- 单条消息行数受控

用 ``pytest tests/test_layout.py -s`` 可以把所有回复打印出来人工检查。
"""

import re

import pytest

MAX_LINES = 20


@pytest.fixture
def plugin():
    from timeline_trpg import main

    instance = main.TimelineTRPG(context=None)
    yield instance
    import asyncio

    asyncio.run(instance.terminate())


@pytest.fixture
def say(plugin, run):
    from timeline_trpg.trpg.adapter.command_context import CommandContext

    transcript: list[tuple[str, list[str]]] = []

    def _say(
        message: str, sender_id: str = "u1", sender_name: str = "Alice", group="g1"
    ) -> list[str]:
        match = re.match(r"^[.。/](\w+)\b\s*(.*)$", message)
        assert match, message
        ctx = CommandContext(
            command=match.group(1),
            args=match.group(2).split(),
            sender_id=sender_id,
            sender_name=sender_name,
            session_id=group or sender_id,
            group_id=group,
            metadata={"message_str": message},
        )
        run(plugin.router.dispatch(ctx))
        replies = ctx.get_reply_texts()
        transcript.append((message, replies))
        return replies

    _say.transcript = transcript
    yield _say
    for message, replies in transcript:
        print(f"\n>>> {message}")
        for reply in replies:
            print(reply)
            print("~~")


def assert_layout(transcript):
    from timeline_trpg.trpg.infrastructure.text_style import display_width

    problems = []
    for message, replies in transcript:
        assert replies, f"{message} 没有回复"
        for reply in replies:
            lines = reply.split("\n")
            if len(lines) > MAX_LINES:
                problems.append(f"{message}: {len(lines)} 行")
            for line in lines:
                if display_width(line) > 36:
                    problems.append(f"{message}: 过宽 {line!r}")
            for banned in ("===", "指令处理失败", "指令执行完成", "Traceback"):
                if banned in reply:
                    problems.append(f"{message}: 含有 {banned!r}")
    assert not problems, "\n".join(problems)


def test_full_session_layout(say, sample_character):
    say(".help")
    say(".help bt")
    say(".help tlsetup")
    say(".help setupWP")
    say(".tlsetup " + sample_character)
    say(".chr")
    say(".chr show")
    say(".r 3d6+2")
    say(".r")
    say(".tar 50")
    say(".ex 力量")
    say(".ex 力量 10 5")
    say(".neg 3 2 50")
    say(".lv +1")
    say(".rc")
    say(".dr add 铠甲 hp 50% 物理 3t")
    say(".buff add 祝福 力量 直接加算 5 3t")
    say(".rc s 20 全部 5t")
    say(".rc hp -30 物理")
    say(".rc mp +5")
    say(".dr")
    say(".buff")
    say(".i 绳索 +2 1.5")
    say(".i cash +50 卖剑")
    say(".i")
    say(".i cash")
    say(".setupWP 名称:激光枪,类型:火力,伤害:20,载弹量:6,负重:3.5")
    say(".wp")
    say(".wp show 1")
    say(".tl new 遭遇战")
    say(".bt in")
    say(".bt in", sender_id="u2", sender_name="Bob")
    say(".tlsetup " + sample_character.replace("勇者", "游侠"), sender_id="u2")
    say(".bt in", sender_id="u2", sender_name="Bob")
    say(".dr add 铠甲 hp 50% 物理 3t")
    say(".buff add 祝福 力量 直接加算 5 3t")
    say(".bt 力量 5t 冲锋")
    say(".bt 敏捷 4t", sender_id="u2", sender_name="Bob")
    say(".bt 敏捷 3t")
    say(".tl")
    say(".tl show")
    say(".tl get 3")
    say(".bt undo")
    say(".chr reset")
    say(".lv")
    assert_layout(say.transcript)


def test_error_replies_layout(say, sample_character):
    say(".ex 力量")
    say(".tlsetup " + sample_character)
    say(".ex 力良")
    say(".ex 力量 1 2 3")
    say(".buff add")
    say(".buff add 祝福 力良 直接加算 5")
    say(".dr add 铠甲")
    say(".dr foo")
    say(".rc foo")
    say(".rc hp abc")
    say(".i ???")
    say(".wp del")
    say(".tl foo")
    say(".tl get")
    say(".chr foo")
    say(".lv abc")
    say(".neg")
    say(".bt")
    say(".bt 力良 5t")
    say(".setupWP")
    say(".tlsetup")
    assert_layout(say.transcript)


def test_help_unknown_module_is_single_message(say):
    replies = say(".help btt")
    assert len(replies) == 1
    assert ".help bt" in replies[0]

    replies = say(".help zzzzzz")
    assert len(replies) == 1


def test_unknown_command_suggests_closest(say):
    (reply,) = say(".buf")
    assert ".buff" in reply


def test_command_routing_ignores_case(say):
    (reply,) = say(".R 1d1")
    assert "[Alice]" in reply and "1d1" in reply


def test_help_summary_lists_setup_commands(say):
    (reply,) = say(".help")
    lines = reply.split("\n")
    assert lines[0] == "【TimelineTRPG】"
    assert any(line.startswith(".tlsetup ") for line in lines)
    assert any(line.startswith(".setupWP ") for line in lines)
    assert not any(line.startswith(".resmod ") for line in lines)


def test_cmd_help_matches_help_cmd(say):
    (a,) = say(".bt help")
    (b,) = say(".help bt")
    assert a == b
    (c,) = say(".bt")
    assert c == b


def test_examination_is_three_lines(say, sample_character):
    say(".tlsetup " + sample_character)
    (reply,) = say(".ex 力量 50")
    lines = reply.split("\n")
    assert len(lines) == 3
    assert lines[0].startswith("[勇者]")


def test_attribute_typo_suggests(say, sample_character):
    say(".tlsetup " + sample_character)
    (reply,) = say(".ex 力良")
    assert "力量" in reply


def test_add_echoes_expiry(say, sample_character):
    say(".tlsetup " + sample_character)
    (reply,) = say(".buff add 祝福 力量 直接加算 5 3t")
    assert "没有战斗" in reply

    say(".tl new 遭遇战")
    say(".bt in")
    say(".bt 力量 2t")
    (reply,) = say(".buff add 迅捷 敏捷 直接加算 5 3t")
    assert "到期" in reply
    (reply,) = say(".dr add 铠甲 hp 50% 物理 2")
    assert "2 次" in reply


def test_expired_events_shown_first(say, sample_character):
    say(".tlsetup " + sample_character)
    say(".tl new 遭遇战")
    say(".bt in")
    say(".bt 力量 1t")
    say(".buff add 祝福 力量 直接加算 5 2t")
    (reply,) = say(".bt 力量 5t")
    assert reply.startswith("【到期】")
    assert "祝福" in reply.split("\n")[1]


def test_reset_summary(say, sample_character):
    (reply,) = say(".chr reset")
    assert "还没有激活的角色" in reply

    say(".tlsetup " + sample_character)
    (reply,) = say(".chr reset")
    lines = reply.split("\n")
    assert lines[0] == "【角色重置】勇者"
    assert [line.split("：")[0] for line in lines[1:]] == ["资源", "资源修正", "Buff"]
