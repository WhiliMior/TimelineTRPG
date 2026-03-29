"""
游戏配置管理模块 - 统一管理游戏数字精度配置
迁移自老项目 Game/game_config.json
"""
import json
from pathlib import Path
from typing import Union


class GameConfig:
    """游戏配置管理类"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        config_path = Path(__file__).parent / "game_config.json"
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        except FileNotFoundError:
            # 默认配置
            self._config = {
                "timeline_precision": {
                    "time": 1,
                    "impact": 0,
                    "percentage": 1,
                    "attribute": 0,
                    "resource": 1
                }
            }
    
    def get_precision(self, precision_type: str) -> int:
        """
        获取指定类型的精度
        
        Args:
            precision_type: 精度类型 (time/impact/percentage/attribute/resource)
        
        Returns:
            int: 小数位数
        """
        timeline_precision = self._config.get("timeline_precision", {})
        return timeline_precision.get(precision_type, 0)
    
    def format_value(self, value: Union[int, float], precision_type: str) -> str:
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
    
    def round_value(self, value: float, precision_type: str) -> Union[int, float]:
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
        设置指定类型的精度并保存到配置文件
        
        Args:
            precision_type: 精度类型 (time/impact/percentage/attribute/resource)
            value: 小数位数
        
        Returns:
            bool: 是否成功保存
        """
        if "timeline_precision" not in self._config:
            self._config["timeline_precision"] = {}
        
        self._config["timeline_precision"][precision_type] = value
        
        # 保存到配置文件
        config_path = Path(__file__).parent / "game_config.json"
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False
    
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
