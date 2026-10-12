import json
import re
from pathlib import Path

from timeline_trpg.trpg.service.buff.buff import buff_module

ROOT = Path(__file__).resolve().parent.parent
REPLIES = ROOT / "trpg" / "infrastructure" / "config" / "replies.json"


def _iter_sources():
    for path in (ROOT / "trpg").rglob("*.py"):
        if path.name != "message.py":
            yield path
    yield ROOT / "main.py"


def test_replies_json_has_no_duplicate_keys_or_escaped_newlines():
    raw = REPLIES.read_text(encoding="utf-8")
    assert "\\\\n" not in raw

    def no_duplicates(pairs):
        keys = [k for k, _ in pairs]
        assert len(keys) == len(set(keys)), keys
        return dict(pairs)

    json.loads(raw, object_pairs_hook=no_duplicates)


def test_every_rendered_template_exists():
    templates = json.loads(REPLIES.read_text(encoding="utf-8"))
    missing = []
    for path in _iter_sources():
        src = path.read_text(encoding="utf-8")
        managers = dict(re.findall(r'self\.(\w+)\s*=\s*ReplyManager\("(\w+)"\)', src))
        managers.update(re.findall(r'(\w+)\s*=\s*ReplyManager\("(\w+)"\)', src))
        for var, key in re.findall(r'(?:self\.)?(\w+)\.render\(\s*"(\w+)"', src):
            module = managers.get(var)
            if module and key not in templates.get(module, {}):
                missing.append(f"{path.name}: {module}.{key}")
    assert not missing, missing


def test_multi_delete_buffs_reports_success(make_ctx, run, create_character):
    create_character()
    for name in ("甲", "乙", "丙"):
        run(buff_module.buff(make_ctx("buff", "add", name, "力量", "直接加算", "5")))

    ctx = make_ctx("buff", "del", "1", "2")
    run(buff_module.buff(ctx))
    assert "失败" not in ctx.get_reply_texts()[0]


def test_tlsetup_accepts_full_width_punctuation(make_ctx, run):
    from timeline_trpg.trpg.infrastructure.storage import StorageBackend
    from timeline_trpg.trpg.service.character.character import character_module

    run(character_module.tlsetup(make_ctx("tlsetup", "名称：小明，力量：30，等级：1")))
    character = StorageBackend.get_character("u1", "小明")
    assert character["data"]["力量"] == 30
