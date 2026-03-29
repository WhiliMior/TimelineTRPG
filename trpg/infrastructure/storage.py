"""
统一的数据存储后端

提供 JSON 文件持久化存储，目录结构完全按照老项目 TimelineBot 设计：
- plugin_data/TimelineTRPG/User/{user_id}/characters.json
- plugin_data/TimelineTRPG/Battle/{conversation_id}/battle.json
- plugin_data/TimelineTRPG/Examination/negotiation.json
- plugin_data/TimelineTRPG/Examination/target.json
- plugin_data/TimelineTRPG/Weapon/{user_id}/weapons.json
- plugin_data/TimelineTRPG/Timeline/{conversation_id}/timeline.json
- plugin_data/TimelineTRPG/Resource/{user_id}/resources.json
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum


class StorageType(str, Enum):
    """存储类型枚举"""
    USER = "User"
    BATTLE = "Battle"
    BATTLE_TIMELINE = "BattleTimeline"  # 战斗时间轴存储（Group/Private结构）
    EXAMINATION = "Examination"
    WEAPON = "Weapon"
    TIMELINE = "Timeline"
    RESOURCE = "Resource"


class SessionType(str, Enum):
    """会话类型枚举（用于 BattleTimeline）"""
    GROUP = "Group"
    PRIVATE = "Private"


class StorageBackend:
    """
    统一的 JSON 文件存储后端
    
    所有业务模块通过此类进行数据持久化，数据格式与老项目完全一致。
    数据存储在 data/plugin_data/TimelineTRPG/ 目录下。
    """
    
    # 插件数据目录（类级别缓存）
    _plugin_data_dir: Optional[Path] = None
    
    @classmethod
    def _get_plugin_data_dir(cls) -> Path:
        """获取插件数据目录 (data/plugin_data/TimelineTRPG/)"""
        if cls._plugin_data_dir is None:
            # 使用 AstrBot 标准插件数据目录
            from astrbot.core.star.star_tools import StarTools
            cls._plugin_data_dir = StarTools.get_data_dir("TimelineTRPG")
        return cls._plugin_data_dir
    
    @classmethod
    def _get_base_dir(cls, storage_type: StorageType) -> Path:
        """获取指定存储类型的基础目录"""
        base_dir = cls._get_plugin_data_dir() / storage_type.value
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir
    
    @classmethod
    def _get_entity_dir(cls, storage_type: StorageType, entity_id: str) -> Path:
        """
        获取实体目录
        
        Args:
            storage_type: 存储类型
            entity_id: 实体ID（用户ID或群组ID）
        
        Returns:
            实体目录路径
        """
        # 替换 Windows 不允许的路径字符
        safe_entity_id = entity_id.replace(":", "_").replace("/", "_").replace("\\", "_")
        entity_dir = cls._get_base_dir(storage_type) / safe_entity_id
        entity_dir.mkdir(parents=True, exist_ok=True)
        return entity_dir
    
    @classmethod
    def _get_file_path(cls, storage_type: StorageType, entity_id: str, filename: str = None) -> Path:
        """
        获取文件路径
        
        Args:
            storage_type: 存储类型
            entity_id: 实体ID
            filename: 文件名，如果为None则使用默认文件名
        
        Returns:
            文件完整路径
        """
        entity_dir = cls._get_entity_dir(storage_type, entity_id)
        
        # 默认文件名映射
        if filename is None:
            filename_map = {
                StorageType.USER: "characters.json",
                StorageType.BATTLE: "battle.json",
                StorageType.WEAPON: "weapons.json",
                StorageType.TIMELINE: "timeline.json",
                StorageType.RESOURCE: "resources.json",
            }
            filename = filename_map.get(storage_type, f"{storage_type.value.lower()}.json")
        
        return entity_dir / filename
    
    @classmethod
    def _get_global_file_path(cls, storage_type: StorageType, filename: str) -> Path:
        """
        获取全局文件路径（不需要 entity_id）
        
        Args:
            storage_type: 存储类型
            filename: 文件名
        
        Returns:
            文件完整路径
        """
        base_dir = cls._get_base_dir(storage_type)
        return base_dir / filename
    
    # ==================== 通用加载/保存方法 ====================
    
    @classmethod
    def load(cls, storage_type: StorageType, entity_id: str, filename: str = None, default: Any = None) -> Any:
        """
        加载数据
        
        Args:
            storage_type: 存储类型
            entity_id: 实体ID
            filename: 文件名
            default: 如果文件不存在，返回的默认值
        
        Returns:
            加载的数据，如果是列表或字典则返回相应类型
        """
        file_path = cls._get_file_path(storage_type, entity_id, filename)
        
        if not file_path.exists():
            return default
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except (json.JSONDecodeError, IOError) as e:
            print(f"[StorageBackend] 加载文件失败 {file_path}: {e}")
            return default
    
    @classmethod
    def save(cls, storage_type: StorageType, entity_id: str, data: Any, filename: str = None) -> bool:
        """
        保存数据
        
        Args:
            storage_type: 存储类型
            entity_id: 实体ID
            data: 要保存的数据
            filename: 文件名
        
        Returns:
            保存是否成功
        """
        file_path = cls._get_file_path(storage_type, entity_id, filename)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except (TypeError, IOError) as e:
            print(f"[StorageBackend] 保存文件失败 {file_path}: {e}")
            return False
    
    # ==================== 全局文件操作（无需 entity_id）====================
    
    @classmethod
    def load_global(cls, storage_type: StorageType, filename: str, default: Any = None) -> Any:
        """
        加载全局数据文件
        
        Args:
            storage_type: 存储类型
            filename: 文件名
            default: 默认值
        
        Returns:
            加载的数据
        """
        file_path = cls._get_global_file_path(storage_type, filename)
        
        if not file_path.exists():
            return default
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[StorageBackend] 加载全局文件失败 {file_path}: {e}")
            return default
    
    @classmethod
    def save_global(cls, storage_type: StorageType, filename: str, data: Any) -> bool:
        """
        保存全局数据文件
        
        Args:
            storage_type: 存储类型
            filename: 文件名
            data: 要保存的数据
        
        Returns:
            保存是否成功
        """
        file_path = cls._get_global_file_path(storage_type, filename)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except (TypeError, IOError) as e:
            print(f"[StorageBackend] 保存全局文件失败 {file_path}: {e}")
            return False
    
    # ==================== 角色数据快捷方法 ====================
    
    @classmethod
    def load_characters(cls, user_id: str) -> List[Dict]:
        """
        加载用户角色列表
        
        Args:
            user_id: 用户ID
        
        Returns:
            角色列表
        """
        return cls.load(StorageType.USER, user_id, default=[])
    
    @classmethod
    def save_characters(cls, user_id: str, characters: List[Dict]) -> bool:
        """
        保存用户角色列表
        
        Args:
            user_id: 用户ID
            characters: 角色列表
        
        Returns:
            保存是否成功
        """
        return cls.save(StorageType.USER, user_id, characters)
    
    @classmethod
    def get_character(cls, user_id: str, character_name: str) -> Optional[Dict]:
        """
        获取指定角色
        
        Args:
            user_id: 用户ID
            character_name: 角色名
        
        Returns:
            角色数据，如果不存在返回 None
        """
        characters = cls.load_characters(user_id)
        for char in characters:
            if char.get("name") == character_name:
                return char
        return None
    
    @classmethod
    def update_character(cls, user_id: str, character_name: str, character_data: Dict) -> bool:
        """
        更新角色数据
        
        Args:
            user_id: 用户ID
            character_name: 角色名
            character_data: 新的角色数据
        
        Returns:
            更新是否成功
        """
        characters = cls.load_characters(user_id)
        
        for i, char in enumerate(characters):
            if char.get("name") == character_name:
                characters[i] = character_data
                return cls.save_characters(user_id, characters)
        
        # 角色不存在，添加新角色
        characters.append(character_data)
        return cls.save_characters(user_id, characters)
    
    @classmethod
    def delete_character(cls, user_id: str, character_name: str) -> bool:
        """
        删除角色
        
        Args:
            user_id: 用户ID
            character_name: 角色名
        
        Returns:
            删除是否成功
        """
        characters = cls.load_characters(user_id)
        original_len = len(characters)
        characters = [c for c in characters if c.get("name") != character_name]
        
        if len(characters) < original_len:
            return cls.save_characters(user_id, characters)
        return False
    
    # ==================== 战斗数据快捷方法 ====================
    
    @classmethod
    def load_battle(cls, conversation_id: str) -> Dict:
        """
        加载战斗数据
        
        Args:
            conversation_id: 群组/会话ID
        
        Returns:
            战斗数据
        """
        default = {
            "active_battle_id": None,
            "player": {},
            "battle_list": {}
        }
        return cls.load(StorageType.BATTLE, conversation_id, default=default)
    
    @classmethod
    def save_battle(cls, conversation_id: str, battle_data: Dict) -> bool:
        """
        保存战斗数据
        
        Args:
            conversation_id: 群组/会话ID
            battle_data: 战斗数据
        
        Returns:
            保存是否成功
        """
        return cls.save(StorageType.BATTLE, conversation_id, battle_data)
    
    # ==================== 谈判数据快捷方法 ====================
    
    @classmethod
    def load_negotiation(cls, conversation_id: str = None, session_type: str = "private") -> Dict:
        """
        加载谈判数据
        
        Args:
            conversation_id: 可选的会话ID，如果提供则返回该会话的数据
            session_type: 会话类型，"group" 或 "private"
        
        Returns:
            谈判数据
        """
        data = cls.load_global(StorageType.EXAMINATION, "negotiation.json", default={"group": {}, "private": {}})
        
        # 确保结构存在
        if session_type not in data:
            data[session_type] = {}
        
        if conversation_id:
            return data.get(session_type, {}).get(conversation_id, {})
        return data
    
    @classmethod
    def save_negotiation(cls, conversation_id: str, negotiation_data: Dict, session_type: str = "private") -> bool:
        """
        保存谈判数据
        
        Args:
            conversation_id: 会话ID
            negotiation_data: 谈判数据
            session_type: 会话类型，"group" 或 "private"
        
        Returns:
            保存是否成功
        """
        data = cls.load_global(StorageType.EXAMINATION, "negotiation.json", default={"group": {}, "private": {}})
        
        # 确保结构存在
        if session_type not in data:
            data[session_type] = {}
        
        data[session_type][conversation_id] = negotiation_data
        return cls.save_global(StorageType.EXAMINATION, "negotiation.json", data)
    
    # ==================== 目标数据快捷方法 ====================
    
    @classmethod
    def load_target(cls, conversation_id: str = None, session_type: str = "private") -> Dict:
        """
        加载目标数据
        
        Args:
            conversation_id: 可选的会话ID
            session_type: 会话类型，"group" 或 "private"
        
        Returns:
            目标数据
        """
        data = cls.load_global(StorageType.EXAMINATION, "target.json", default={"group": {}, "private": {}})
        
        # 确保结构存在
        if session_type not in data:
            data[session_type] = {}
        
        if conversation_id:
            return data.get(session_type, {}).get(conversation_id, {})
        return data
    
    @classmethod
    def save_target(cls, conversation_id: str, target_data: Dict, session_type: str = "private") -> bool:
        """
        保存目标数据
        
        Args:
            conversation_id: 会话ID
            target_data: 目标数据
            session_type: 会话类型，"group" 或 "private"
        
        Returns:
            保存是否成功
        """
        data = cls.load_global(StorageType.EXAMINATION, "target.json", default={"group": {}, "private": {}})
        
        # 确保结构存在
        if session_type not in data:
            data[session_type] = {}
        
        data[session_type][conversation_id] = target_data
        return cls.save_global(StorageType.EXAMINATION, "target.json", data)
    
    # ==================== 武器数据快捷方法 ====================
    
    @classmethod
    def load_weapons(cls, user_id: str) -> List[Dict]:
        """
        加载用户武器列表
        
        Args:
            user_id: 用户ID
        
        Returns:
            武器列表
        """
        return cls.load(StorageType.WEAPON, user_id, default=[])
    
    @classmethod
    def save_weapons(cls, user_id: str, weapons: List[Dict]) -> bool:
        """
        保存用户武器列表
        
        Args:
            user_id: 用户ID
            weapons: 武器列表
        
        Returns:
            保存是否成功
        """
        return cls.save(StorageType.WEAPON, user_id, weapons)
    
    # ==================== 资源数据快捷方法 ====================
    
    @classmethod
    def load_resources(cls, user_id: str) -> Dict:
        """
        加载用户资源数据
        
        Args:
            user_id: 用户ID
        
        Returns:
            资源数据
        """
        return cls.load(StorageType.RESOURCE, user_id, default={})
    
    @classmethod
    def save_resources(cls, user_id: str, resources: Dict) -> bool:
        """
        保存用户资源数据
        
        Args:
            user_id: 用户ID
            resources: 资源数据
        
        Returns:
            保存是否成功
        """
        return cls.save(StorageType.RESOURCE, user_id, resources)
    
    # ==================== BattleTimeline 战斗时间轴存储 ====================
    
    @classmethod
    def _get_battle_timeline_dir(cls, session_type: SessionType, conversation_id: str) -> Path:
        """
        获取战斗时间轴目录
        
        Args:
            session_type: 会话类型（Group 或 Private）
            conversation_id: 群组ID或私聊ID
        
        Returns:
            目录路径
        """
        base_dir = cls._get_plugin_data_dir() / StorageType.BATTLE_TIMELINE.value / session_type.value
        # 替换 Windows 不允许的路径字符
        safe_id = str(conversation_id).replace(":", "_").replace("/", "_").replace("\\", "_")
        dir_path = base_dir / safe_id
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path
    
    @classmethod
    def _get_battle_timeline_file_path(cls, session_type: SessionType, conversation_id: str) -> Path:
        """
        获取战斗时间轴文件路径
        
        Args:
            session_type: 会话类型（Group 或 Private）
            conversation_id: 群组ID或私聊ID
        
        Returns:
            文件路径
        """
        return cls._get_battle_timeline_dir(session_type, conversation_id) / "data.json"
    
    @classmethod
    def load_battle_timeline(cls, conversation_id: str, is_group: bool = True) -> Dict:
        """
        加载战斗时间轴数据
        
        Args:
            conversation_id: 群组ID或私聊ID
            is_group: True 表示群聊，False 表示私聊
        
        Returns:
            战斗时间轴数据
        """
        session_type = SessionType.GROUP if is_group else SessionType.PRIVATE
        file_path = cls._get_battle_timeline_file_path(session_type, conversation_id)
        
        default = {
            "active_battle_id": None,
            "player": {},
            "battle_list": {}
        }
        
        if not file_path.exists():
            return default
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[StorageBackend] 加载战斗时间轴失败 {file_path}: {e}")
            return default
    
    @classmethod
    def save_battle_timeline(cls, conversation_id: str, data: Dict, is_group: bool = True) -> bool:
        """
        保存战斗时间轴数据
        
        Args:
            conversation_id: 群组ID或私聊ID
            data: 战斗时间轴数据
            is_group: True 表示群聊，False 表示私聊
        
        Returns:
            保存是否成功
        """
        session_type = SessionType.GROUP if is_group else SessionType.PRIVATE
        file_path = cls._get_battle_timeline_file_path(session_type, conversation_id)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except (TypeError, IOError) as e:
            print(f"[StorageBackend] 保存战斗时间轴失败 {file_path}: {e}")
            return False
