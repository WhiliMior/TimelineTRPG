"""
pytest 公共配置

AstrBot 本体不在测试环境中，这里为 astrbot.* 注入最小桩模块，
并把仓库根目录注册为包 ``timeline_trpg``（与 AstrBot 以
``data.plugins.<目录名>`` 形式加载插件的方式一致，保证相对导入可用）。
"""

import importlib.util
import logging
import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PKG = "timeline_trpg"

_DEFAULT_DATA_DIR = Path(tempfile.mkdtemp(prefix="timeline_trpg_"))


def _stub(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


class _StarTools:
    data_dir: Path = _DEFAULT_DATA_DIR

    @classmethod
    def get_data_dir(cls, name: str | None = None) -> Path:
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        return cls.data_dir


class _Star:
    def __init__(self, context=None, *args, **kwargs):
        self.context = context


class _AstrBotConfig(dict):
    saved = 0

    def save_config(self):
        self.saved += 1


class _Filter:
    @staticmethod
    def regex(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator


def _register(*_args, **_kwargs):
    def decorator(cls):
        return cls

    return decorator


class _Image:
    @staticmethod
    def fromFileSystem(path):  # noqa: N802
        return ("image", path)

    @staticmethod
    def fromBytes(data):  # noqa: N802
        return ("image_bytes", len(data))


_stub("astrbot")
_stub(
    "astrbot.api",
    logger=logging.getLogger("astrbot"),
    AstrBotConfig=_AstrBotConfig,
)
_stub(
    "astrbot.api.event",
    AstrMessageEvent=object,
    MessageEventResult=object,
    filter=_Filter(),
)
_stub("astrbot.api.message_components", Image=_Image)
_stub("astrbot.api.star", Context=object, Star=_Star, register=_register)
_stub("astrbot.core")
_stub("astrbot.core.star")
_stub("astrbot.core.star.star_tools", StarTools=_StarTools)

_spec = importlib.util.spec_from_file_location(
    PKG, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
_root_module = importlib.util.module_from_spec(_spec)
sys.modules[PKG] = _root_module
_spec.loader.exec_module(_root_module)


SAMPLE_CHARACTER = (
    "名称:勇者,等级:2,物理思维比值:500,年龄:20,成年年龄:18,"
    "体型:170,标准体型:170,体质:60,敏捷:50,力量:55,意志:40,教育:30,智力:45,"
    "文学:20,外貌:50,资产:10"
)


@pytest.fixture
def make_ctx():
    """构造 CommandContext；group_id 为空字符串表示私聊（与 AstrBot 行为一致）"""
    from timeline_trpg.trpg.adapter.command_context import CommandContext

    def _make(
        command: str,
        *args: str,
        sender_id: str = "u1",
        sender_name: str = "Alice",
        group_id: str = "g1",
    ) -> CommandContext:
        return CommandContext(
            command=command,
            args=list(args),
            sender_id=sender_id,
            sender_name=sender_name,
            session_id=group_id or sender_id,
            group_id=group_id,
        )

    return _make


@pytest.fixture
def run():
    import asyncio

    return asyncio.run


@pytest.fixture
def create_character(make_ctx, run):
    from timeline_trpg.trpg.service.character.character import character_module

    def _create(user_id: str = "u1", spec: str = SAMPLE_CHARACTER) -> None:
        ctx = make_ctx("tlsetup", *spec.split(" "), sender_id=user_id)
        run(character_module.tlsetup(ctx))

    return _create


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """每个用例使用独立的数据目录，互不影响"""
    from timeline_trpg.trpg.infrastructure.storage import StorageBackend

    monkeypatch.setattr(_StarTools, "data_dir", tmp_path)
    StorageBackend._plugin_data_dir = None
    yield tmp_path
    StorageBackend._plugin_data_dir = None
