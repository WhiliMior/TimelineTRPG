"""
游戏配置管理模块 - 统一管理游戏数字精度配置
迁移自老项目 Game/game_config.json

配置来源（优先级从高到低）：
1. AstrBot 插件配置面板（_conf_schema.json 中的 precision，由 main.py 注入）
2. 数据目录下的 config/game_config.json（未注入面板配置时，.tl acc 写入此处）
3. 插件目录内置的 game_config.json（只读默认值，插件更新会覆盖）
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("TimelineTRPG.config")

PRECISION_TYPES = (
    "time",
    "impact",
    "percentage",
    "attribute",
    "resource",
    "weight",
    "success_rate",
)
MAX_PRECISION = 5

_BUNDLED_PATH = Path(__file__).parent / "game_config.json"
_CONFIG_NAME = "game_config"
_FALLBACK_PRECISION = {
    "time": 2,
    "impact": 0,
    "percentage": 1,
    "attribute": 0,
    "resource": 1,
    "weight": 2,
    "success_rate": 1,
}


def _valid_precision(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= MAX_PRECISION else None


def _load_bundled_precision() -> dict:
    precision = dict(_FALLBACK_PRECISION)
    try:
        with open(_BUNDLED_PATH, encoding="utf-8") as f:
            bundled = json.load(f).get("timeline_precision", {})
        precision.update(
            {k: v for k, v in bundled.items() if _valid_precision(v) is not None}
        )
    except (OSError, ValueError, AttributeError):
        logger.warning("内置精度配置读取失败，使用默认值: %s", _BUNDLED_PATH)
    return precision


class GameConfig:
    """游戏配置管理类"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reset()
        return cls._instance

    def reset(self) -> None:
        """恢复为内置默认值并解除面板配置绑定（插件卸载/热重载时调用）"""
        self._config = {"timeline_precision": _load_bundled_precision()}
        self._panel_config = None
        self._overrides_loaded = False

    def bind_panel_config(self, panel_config) -> None:
        """
        绑定 AstrBot 插件面板配置（AstrBotConfig）

        绑定后面板中的 precision 为唯一来源，.tl acc 修改也会写回面板配置。
        """
        self._panel_config = panel_config
        self._overrides_loaded = False

    def _read_overrides(self) -> dict:
        if self._panel_config is not None:
            return dict(self._panel_config.get("precision") or {})

        from ..storage import StorageBackend

        return dict(
            StorageBackend.load_plugin_config(_CONFIG_NAME).get("timeline_precision")
            or {}
        )

    def _ensure_loaded(self) -> None:
        if self._overrides_loaded:
            return
        self._overrides_loaded = True
        try:
            overrides = self._read_overrides()
        except Exception:
            logger.exception("加载精度配置失败，使用默认值")
            return
        precision = self._config["timeline_precision"]
        for key, value in overrides.items():
            valid = _valid_precision(value)
            if key in PRECISION_TYPES and valid is not None:
                precision[key] = valid

    def get_precision(self, precision_type: str) -> int:
        """
        获取指定类型的精度

        Args:
            precision_type: 精度类型（见 PRECISION_TYPES）

        Returns:
            int: 小数位数
        """
        self._ensure_loaded()
        return self._config["timeline_precision"].get(precision_type, 0)

    def format_value(self, value: int | float, precision_type: str) -> str:
        """
        格式化数值为字符串

        Args:
            value: 数值
            precision_type: 精度类型

        Returns:
            str: 格式化后的字符串
        """
        precision = self.get_precision(precision_type)

        # 如果是整数类型且精度为0
        if isinstance(value, int) and precision == 0:
            return str(value)

        # 格式化浮点数
        return f"{value:.{precision}f}"

    def round_value(self, value: float, precision_type: str) -> int | float:
        """
        根据精度类型四舍五入数值

        Args:
            value: 数值
            precision_type: 精度类型

        Returns:
            Union[int, float]: 四舍五入后的数值
        """
        precision = self.get_precision(precision_type)
        rounded = round(value, precision)

        # 如果精度为0，返回整数
        if precision == 0:
            return int(rounded)

        return rounded

    def set_precision(self, precision_type: str, value: int) -> bool:
        """
        设置指定类型的精度并持久化（面板配置或数据目录）

        Args:
            precision_type: 精度类型（见 PRECISION_TYPES）
            value: 小数位数（0 ~ MAX_PRECISION）

        Returns:
            bool: 是否成功保存
        """
        valid = _valid_precision(value)
        if precision_type not in PRECISION_TYPES or valid is None:
            return False

        self._ensure_loaded()
        self._config["timeline_precision"][precision_type] = valid

        try:
            if self._panel_config is not None:
                precision = dict(self._panel_config.get("precision") or {})
                precision[precision_type] = valid
                self._panel_config["precision"] = precision
                self._panel_config.save_config()
                return True

            from ..storage import StorageBackend

            return StorageBackend.save_plugin_config(
                _CONFIG_NAME,
                {"timeline_precision": dict(self._config["timeline_precision"])},
            )
        except Exception:
            logger.exception("保存精度配置失败")
            return False

    def time_key(self, value: float) -> str:
        """
        生成时间线中时间点的存储键（所有写入时间线的地方都必须使用）

        与历史数据保持一致：精度为 0 时为 "10"，否则为 Python 浮点字符串如 "10.0"、"10.25"。
        读取时间线时不要自行拼键，应遍历已有键并用 float() 解析。
        """
        return str(self.round_value(float(value), "time"))

    def get_min_time_unit(self) -> float:
        """
        获取时间的最小单位（基于精度计算）

        Returns:
            float: 最小时间单位，例如精度为1时返回0.1
        """
        precision = self.get_precision("time")
        return 10 ** (-precision)


# 全局单例
game_config = GameConfig()
