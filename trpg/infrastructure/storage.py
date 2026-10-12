"""
统一的数据存储后端

提供 JSON 文件持久化存储，目录结构（data/plugin_data/TimelineTRPG/ 下）：
- User/{user_id}/characters.json                          角色（列表）
- BattleTimeline/Group|Private/{conversation_id}/data.json 战斗时间轴
- Inventory/Group|Private/{conversation_id}/weights.json   物品重量记忆
- Examination/Group|Private/{conversation_id}/target.json  检定目标值
- Examination/Group|Private/{conversation_id}/negotiation.json 交涉对象

可靠性约定：
- 写入为原子操作：先写同目录临时文件并 fsync，再 os.replace 替换
- 读到损坏的 JSON 时，原文件改名为 .corrupt-<时间戳> 保留，并抛出 StorageCorruptedError，
  绝不静默返回默认值（否则下一次保存会把原数据覆盖掉）
- 读-改-写需要串行时使用 edit_* 异步上下文，按文件路径加 asyncio.Lock
- 字典类存档带 schema_version 字段，加载时经过 _migrate() 升级
"""

import asyncio
import copy
import json
import logging
import os
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("TimelineTRPG.storage")

SCHEMA_VERSION = 1


class StorageError(Exception):
    """存储读写失败"""


class StorageCorruptedError(StorageError):
    """存档文件损坏，已备份原文件"""

    def __init__(self, path: Path, backup_path: Path | None):
        super().__init__(f"存档文件损坏: {path}")
        self.path = path
        self.backup_path = backup_path


class StorageType(str, Enum):
    """存储类型枚举"""

    USER = "User"
    BATTLE_TIMELINE = "BattleTimeline"  # 战斗时间轴存储（Group/Private结构）
    EXAMINATION = "Examination"
    INVENTORY = "Inventory"  # 物品重量自动存储


class SessionType(str, Enum):
    """会话类型枚举"""

    GROUP = "Group"
    PRIVATE = "Private"


# 各类字典存档的版本迁移函数：kind -> [v0->v1, v1->v2, ...]
_MIGRATIONS: dict[str, list[Callable[[dict], dict]]] = {}


def _migrate(data: Any, kind: str) -> Any:
    """按 schema_version 依次执行迁移函数；非字典存档（如角色列表）原样返回"""
    if not isinstance(data, dict):
        return data
    version = data.get("schema_version", 0)
    steps = _MIGRATIONS.get(kind, [])
    while version < len(steps):
        data = steps[version](data)
        version += 1
    data["schema_version"] = max(version, SCHEMA_VERSION)
    return data


def _safe_id(entity_id: Any) -> str:
    """替换 Windows 不允许的路径字符"""
    return str(entity_id).replace(":", "_").replace("/", "_").replace("\\", "_")


class StorageBackend:
    """
    统一的 JSON 文件存储后端

    所有业务模块通过此类进行数据持久化。
    数据存储在 data/plugin_data/TimelineTRPG/ 目录下。
    """

    # 插件数据目录（类级别缓存）
    _plugin_data_dir: Path | None = None
    _locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def reset_cache(cls) -> None:
        """清理类级缓存（插件卸载/热重载时调用）"""
        cls._plugin_data_dir = None
        cls._locks = {}

    @classmethod
    def _get_plugin_data_dir(cls) -> Path:
        """获取插件数据目录 (data/plugin_data/TimelineTRPG/)"""
        if cls._plugin_data_dir is None:
            # 使用 AstrBot 标准插件数据目录
            from astrbot.core.star.star_tools import StarTools

            cls._plugin_data_dir = Path(StarTools.get_data_dir("TimelineTRPG"))
        return cls._plugin_data_dir

    @classmethod
    def get_data_dir(cls) -> Path:
        """插件数据根目录（供其他基础设施模块存放配置等）"""
        return cls._get_plugin_data_dir()

    @classmethod
    def _get_base_dir(cls, storage_type: StorageType) -> Path:
        """获取指定存储类型的基础目录"""
        base_dir = cls._get_plugin_data_dir() / storage_type.value
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @classmethod
    def _get_entity_dir(cls, storage_type: StorageType, entity_id: str) -> Path:
        """获取实体目录（用户ID或群组ID）"""
        entity_dir = cls._get_base_dir(storage_type) / _safe_id(entity_id)
        entity_dir.mkdir(parents=True, exist_ok=True)
        return entity_dir

    @classmethod
    def _get_session_dir(
        cls, storage_type: StorageType, conversation_id: str, is_group: bool
    ) -> Path:
        """获取按 Group/Private 划分的会话目录"""
        session_type = SessionType.GROUP if is_group else SessionType.PRIVATE
        dir_path = (
            cls._get_plugin_data_dir()
            / storage_type.value
            / session_type.value
            / _safe_id(conversation_id)
        )
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    # ==================== 底层读写 ====================

    @staticmethod
    def _backup_corrupted(path: Path) -> Path | None:
        backup = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            os.replace(path, backup)
            return backup
        except OSError as e:
            logger.error(f"[StorageBackend] 备份损坏文件失败 {path}: {e}")
            return None

    @classmethod
    def _read_json(cls, path: Path, default: Any, kind: str = "") -> Any:
        """
        读取 JSON 文件

        - 文件不存在：返回 default 的深拷贝
        - 内容损坏：备份原文件并抛出 StorageCorruptedError
        - 其他 IO 错误：抛出 StorageError（不返回默认值，防止覆盖原数据）
        """
        if not path.exists():
            return copy.deepcopy(default)

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            backup = cls._backup_corrupted(path)
            logger.error(f"[StorageBackend] 存档损坏 {path}: {e}；已备份为 {backup}")
            raise StorageCorruptedError(path, backup) from e
        except OSError as e:
            logger.error(f"[StorageBackend] 读取文件失败 {path}: {e}")
            raise StorageError(str(e)) from e

        if default is not None and not isinstance(data, type(default)):
            backup = cls._backup_corrupted(path)
            logger.error(
                f"[StorageBackend] 存档结构异常 {path}: 期望 "
                f"{type(default).__name__}，实际 {type(data).__name__}；已备份为 {backup}"
            )
            raise StorageCorruptedError(path, backup)

        return _migrate(data, kind) if kind else data

    @staticmethod
    def _write_json(path: Path, data: Any) -> bool:
        """原子写入 JSON 文件，返回是否成功"""
        if isinstance(data, dict):
            data.setdefault("schema_version", SCHEMA_VERSION)
        tmp_name = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                tmp_name = f.name
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
            return True
        except (OSError, TypeError, ValueError) as e:
            logger.error(f"[StorageBackend] 保存文件失败 {path}: {e}")
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            return False

    @classmethod
    def lock_for(cls, path: Path) -> asyncio.Lock:
        """获取指定文件路径的 asyncio 锁"""
        key = str(path)
        lock = cls._locks.get(key)
        if lock is None:
            lock = cls._locks[key] = asyncio.Lock()
        return lock

    # ==================== 角色数据 ====================

    @classmethod
    def _characters_path(cls, user_id: str) -> Path:
        return cls._get_entity_dir(StorageType.USER, user_id) / "characters.json"

    @classmethod
    def load_characters(cls, user_id: str) -> list[dict]:
        """加载用户角色列表"""
        return cls._read_json(cls._characters_path(user_id), [])

    @classmethod
    def save_characters(cls, user_id: str, characters: list[dict]) -> bool:
        """保存用户角色列表"""
        return cls._write_json(cls._characters_path(user_id), characters)

    @classmethod
    @asynccontextmanager
    async def edit_characters(cls, user_id: str) -> AsyncIterator[list[dict]]:
        """
        加锁读-改-写角色列表：``async with StorageBackend.edit_characters(uid) as chars:``

        正常退出时保存；块内抛出异常则不保存。
        """
        path = cls._characters_path(user_id)
        async with cls.lock_for(path):
            characters = cls.load_characters(user_id)
            yield characters
            if not cls.save_characters(user_id, characters):
                raise StorageError(f"保存失败: {path}")

    @classmethod
    def get_character(cls, user_id: str, character_name: str) -> dict | None:
        """获取指定角色，不存在返回 None"""
        for char in cls.load_characters(user_id):
            if char.get("name") == character_name:
                return char
        return None

    @classmethod
    def update_character(
        cls, user_id: str, character_name: str, character_data: dict
    ) -> bool:
        """更新角色数据，角色不存在时追加"""
        characters = cls.load_characters(user_id)

        for i, char in enumerate(characters):
            if char.get("name") == character_name:
                characters[i] = character_data
                return cls.save_characters(user_id, characters)

        characters.append(character_data)
        return cls.save_characters(user_id, characters)

    # ==================== BattleTimeline 战斗时间轴 ====================

    @staticmethod
    def _default_battle_timeline() -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "active_battle_id": None,
            "player": {},
            "battle_list": {},
        }

    @classmethod
    def _battle_timeline_path(cls, conversation_id: str, is_group: bool) -> Path:
        return (
            cls._get_session_dir(StorageType.BATTLE_TIMELINE, conversation_id, is_group)
            / "data.json"
        )

    @classmethod
    def load_battle_timeline(cls, conversation_id: str, is_group: bool = True) -> dict:
        """加载战斗时间轴数据"""
        path = cls._battle_timeline_path(conversation_id, is_group)
        return cls._read_json(path, cls._default_battle_timeline(), "battle_timeline")

    @classmethod
    def save_battle_timeline(
        cls, conversation_id: str, data: dict, is_group: bool = True
    ) -> bool:
        """保存战斗时间轴数据"""
        path = cls._battle_timeline_path(conversation_id, is_group)
        return cls._write_json(path, data)

    @staticmethod
    def get_active_battle(data: dict) -> dict | None:
        """从战斗时间轴文件数据中取出当前活跃的战斗（就地引用），没有则返回 None"""
        battle_id = data.get("active_battle_id")
        battle = (data.get("battle_list") or {}).get(battle_id) if battle_id else None
        if not battle or not battle.get("name"):
            return None
        return battle

    @classmethod
    @asynccontextmanager
    async def edit_battle_timeline(
        cls, conversation_id: str, is_group: bool = True
    ) -> AsyncIterator[dict]:
        """加锁读-改-写战斗时间轴；正常退出时保存，块内抛出异常则不保存"""
        path = cls._battle_timeline_path(conversation_id, is_group)
        async with cls.lock_for(path):
            data = cls.load_battle_timeline(conversation_id, is_group)
            yield data
            if not cls.save_battle_timeline(conversation_id, data, is_group):
                raise StorageError(f"保存失败: {path}")

    # ==================== Inventory 物品重量 ====================

    @classmethod
    def _inventory_weights_path(cls, conversation_id: str, is_group: bool) -> Path:
        return (
            cls._get_session_dir(StorageType.INVENTORY, conversation_id, is_group)
            / "weights.json"
        )

    @classmethod
    def load_inventory_weights(
        cls, conversation_id: str, is_group: bool = True
    ) -> dict:
        """加载物品重量数据 {物品名: 重量}"""
        path = cls._inventory_weights_path(conversation_id, is_group)
        weights = cls._read_json(path, {})
        weights.pop("schema_version", None)
        return weights

    @classmethod
    def save_inventory_weights(
        cls, conversation_id: str, weights: dict, is_group: bool = True
    ) -> bool:
        """保存物品重量数据 {物品名: 重量}"""
        path = cls._inventory_weights_path(conversation_id, is_group)
        return cls._write_json(path, dict(weights))

    # ==================== 检定目标值 / 交涉对象（按会话存储）====================

    @classmethod
    def _load_session_record(
        cls, filename: str, conversation_id: str, session_type: str
    ) -> dict:
        """
        读取按会话存储的记录；不存在时尝试从旧版全局文件迁移

        旧版把所有群的数据放在 Examination/{filename} 中，按
        {"group": {id: ...}, "private": {id: ...}} 组织，多个群并发写入会互相覆盖。
        """
        is_group = session_type == "group"
        path = (
            cls._get_session_dir(StorageType.EXAMINATION, conversation_id, is_group)
            / filename
        )
        if path.exists():
            record = cls._read_json(path, {}, filename)
            record.pop("schema_version", None)
            return record

        legacy_path = cls._get_base_dir(StorageType.EXAMINATION) / filename
        try:
            legacy = cls._read_json(legacy_path, {})
        except StorageError:
            logger.warning(f"[StorageBackend] 旧版文件不可读，跳过迁移: {legacy_path}")
            return {}

        record = legacy.get(session_type, {}).get(str(conversation_id))
        if not isinstance(record, dict) or not record:
            return {}
        cls._write_json(path, dict(record))
        logger.info(f"[StorageBackend] 已迁移 {filename}: {conversation_id}")
        return dict(record)

    @classmethod
    def _save_session_record(
        cls, filename: str, conversation_id: str, record: dict, session_type: str
    ) -> bool:
        is_group = session_type == "group"
        path = (
            cls._get_session_dir(StorageType.EXAMINATION, conversation_id, is_group)
            / filename
        )
        return cls._write_json(path, dict(record))

    @classmethod
    def load_negotiation(
        cls, conversation_id: str, session_type: str = "private"
    ) -> dict:
        """加载会话的交涉对象，未设定时返回空字典"""
        return cls._load_session_record(
            "negotiation.json", conversation_id, session_type
        )

    @classmethod
    def save_negotiation(
        cls, conversation_id: str, negotiation_data: dict, session_type: str = "private"
    ) -> bool:
        """保存会话的交涉对象"""
        return cls._save_session_record(
            "negotiation.json", conversation_id, negotiation_data, session_type
        )

    @classmethod
    def load_target(cls, conversation_id: str, session_type: str = "private") -> dict:
        """加载会话的检定目标值，未设定时返回空字典"""
        return cls._load_session_record("target.json", conversation_id, session_type)

    @classmethod
    def save_target(
        cls, conversation_id: str, target_data: dict, session_type: str = "private"
    ) -> bool:
        """保存会话的检定目标值"""
        return cls._save_session_record(
            "target.json", conversation_id, target_data, session_type
        )
