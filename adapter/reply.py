"""
回复管理器模块，负责从 JSON 文件中加载回复模板并渲染变量。
提供 ReplyPayload 数据类，用于封装回复数据，不涉及实际发送逻辑。
"""
import json
import os
from dataclasses import dataclass, field

@dataclass
class ReplyPayload:
    """
    回复载荷数据类，包含回复消息的最终文本内容。
    
    业务模块调用 ctx.send(text) 时实际创建的是这个对象，
    由 main.py 统一转换为 AstrBot 的 event.plain_result() 调用。
    """
    text: str
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, str | dict[str, str | int | float | bool | None]]:
        """转换为字典格式，便于序列化或调试"""
        return {
            "text": self.text,
            "metadata": self.metadata
        }


class ReplyManager:
    """
    回复模板管理器，根据模块名从 JSON 文件中加载回复模板。
    
    使用示例:
        reply = ReplyManager("character")
        text = reply.render("set_success", name="Alice", attr="力量", value=30)
    """
    
    _templates: dict[str, dict[str, str]] = {}
    _config_loaded: bool = False
    
    def __init__(self, module_name: str):
        """
        初始化指定模块的回复管理器
        
        Args:
            module_name: 模块名，对应 replies.json 中的顶层键名
        """
        self.module_name: str = module_name
        self._ensure_config_loaded()
    
    @classmethod
    def _ensure_config_loaded(cls):
        """确保配置已经加载"""
        if not cls._config_loaded:
            cls._load_config()
    
    @classmethod
    def _load_config(cls):
        """从 config/replies.json 加载模板配置"""
        # __file__ = adapter/reply.py，需要两级 dirname 才能到达插件根目录
        plugin_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(plugin_root, "config", "replies.json")
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cls._templates = json.load(f)
                cls._config_loaded = True
        except FileNotFoundError:
            # 如果配置文件不存在，使用空的模板字典
            cls._templates = {}
            cls._config_loaded = True
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {config_path} - {e}")
    
    @classmethod
    def reload_config(cls):
        """重新加载配置文件"""
        cls._config_loaded = False
        cls._templates = {}
        cls._load_config()
    
    def render(self, template_name: str, **variables: str) -> str:
        """
        渲染指定名称的模板
        
        Args:
            template_name: 模板名称
            **variables: 模板变量，如 name="Alice", attr="力量"
            
        Returns:
            渲染后的字符串
            
        Raises:
            KeyError: 如果模块或模板不存在
        """
        if self.module_name not in self._templates:
            raise KeyError(f"模块 '{self.module_name}' 在配置文件中不存在")
        
        if template_name not in self._templates[self.module_name]:
            raise KeyError(f"模板 '{template_name}' 在模块 '{self.module_name}' 中不存在")
        
        template = self._templates[self.module_name][template_name]
        
        # 简单替换变量：{var} -> value
        for key, value in variables.items():
            template = template.replace(f"{{{key}}}", str(value))
        
        return template
    
    def get_template(self, template_name: str) -> str | None:
        """
        获取指定名称的原始模板（不渲染）
        
        Args:
            template_name: 模板名称
            
        Returns:
            原始模板字符串，如果不存在则返回 None
        """
        try:
            return self._templates[self.module_name][template_name]
        except KeyError:
            return None
    
    def has_template(self, template_name: str) -> bool:
        """
        检查指定模板是否存在
        """
        return (
            self.module_name in self._templates and 
            template_name in self._templates[self.module_name]
        )