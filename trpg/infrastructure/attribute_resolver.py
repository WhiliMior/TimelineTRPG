"""
属性解析器 - 统一的属性输入处理基础设施

提供属性名称的标准化解析：
- 支持属性原名和别名输入
- 验证属性是否合规
- 返回标准属性名供 CharacterReader 查询使用
"""

# 标准属性列表（按字母顺序排列）
STANDARD_ATTRIBUTES: list[str] = [
    "体质",
    "敏捷",
    "力量",
    "意志",
    "教育",
    "智力",
    "医学及生命科学",
    "工程与科技",
    "军事与生存",
    "文学",
    "视觉及表演艺术",
]

# 中文别名映射表
# 格式：别名 -> 标准属性名
CHINESE_ALIASES: dict[str, str] = {
    # 医学及生命科学的别名
    "医学": "医学及生命科学",
    "生命科学": "医学及生命科学",
    # 工程与科技的别名
    "工程": "工程与科技",
    "科技": "工程与科技",
    # 军事与生存的别名
    "军事": "军事与生存",
    "生存": "军事与生存",
    # 视觉及表演艺术的别名
    "表演": "视觉及表演艺术",
    "艺术": "视觉及表演艺术",
}

# 英文别名映射表
# 格式：英文别名 -> 标准属性名
ENGLISH_ALIASES: dict[str, str] = {
    "str": "力量",
    "strength": "力量",
    "dex": "敏捷",
    "dexterity": "敏捷",
    "con": "体质",
    "constitution": "体质",
    "int": "智力",
    "intelligence": "智力",
    "wis": "意志",
    "wisdom": "意志",
    "edu": "教育",
    "education": "教育",
    # 领域属性的英文别名
    "med": "医学及生命科学",
    "medical": "医学及生命科学",
    "medicine": "医学及生命科学",
    "eng": "工程与科技",
    "engineering": "工程与科技",
    "tech": "工程与科技",
    "technology": "工程与科技",
    "mil": "军事与生存",
    "military": "军事与生存",
    "survival": "军事与生存",
    "lit": "文学",
    "literature": "文学",
    "art": "视觉及表演艺术",
    "visual": "视觉及表演艺术",
    "performing": "视觉及表演艺术",
    "vp": "视觉及表演艺术",
    "vpa": "视觉及表演艺术",
}

# 合并所有别名映射（中文 + 英文）
# 别名 -> 标准属性名
ALL_ALIASES: dict[str, str] = {**CHINESE_ALIASES, **ENGLISH_ALIASES}

# 构建标准属性集合（用于快速查找）
_STANDARD_ATTRIBUTE_SET: set[str] = set(STANDARD_ATTRIBUTES)

# 构建有效输入集合（标准属性 + 所有别名 + 特殊范围）
_SPECIAL_SCOPES: set[str] = {"物理", "思维", "领域", "所有", "全部"}
_VALID_INPUTS: set[str] = (
    _STANDARD_ATTRIBUTE_SET | set(ALL_ALIASES.keys()) | _SPECIAL_SCOPES
)

# 特殊范围映射到属性列表
# 注意：思维范围包括意志、教育、智力 + 所有领域属性
SCOPE_ATTRIBUTES: dict[str, list[str]] = {
    "物理": ["体质", "力量", "敏捷"],
    "思维": [
        "意志",
        "教育",
        "智力",
        "医学及生命科学",
        "工程与科技",
        "军事与生存",
        "文学",
        "视觉及表演艺术",
    ],
    "领域": ["医学及生命科学", "工程与科技", "军事与生存", "文学", "视觉及表演艺术"],
    "所有": STANDARD_ATTRIBUTES,
    "全部": STANDARD_ATTRIBUTES,
}


class AttributeResolver:
    """
    属性解析器

    提供统一的属性输入处理接口：
    - 解析属性名称（支持原名和别名）
    - 验证属性是否合规
    - 返回标准属性名供 CharacterReader 使用
    """

    @staticmethod
    def resolve(input_attribute: str) -> str | None:
        """
        解析属性输入，返回标准属性名

        Args:
            input_attribute: 属性输入（可能是标准名、别名或特殊范围）

        Returns:
            标准属性名或特殊范围名，如果输入不合法返回 None

        Example:
            >>> AttributeResolver.resolve("力量")
            '力量'
            >>> AttributeResolver.resolve("str")
            '力量'
            >>> AttributeResolver.resolve("医学")
            '医学及生命科学'
            >>> AttributeResolver.resolve("物理")
            '物理'
            >>> AttributeResolver.resolve("未知属性")
            None
        """
        if not input_attribute:
            return None

        # 去除首尾空白
        input_attribute = input_attribute.strip()

        # 首先检查是否是标准属性
        if input_attribute in _STANDARD_ATTRIBUTE_SET:
            return input_attribute

        # 检查是否是别名
        if input_attribute in ALL_ALIASES:
            return ALL_ALIASES[input_attribute]

        # 检查是否是特殊范围
        if input_attribute in _SPECIAL_SCOPES:
            return input_attribute

        return None

    @staticmethod
    def is_valid(input_attribute: str) -> bool:
        """
        检查属性输入是否合法

        Args:
            input_attribute: 属性输入

        Returns:
            True 如果输入是合法的属性名或别名，False 否则

        Example:
            >>> AttributeResolver.is_valid("力量")
            True
            >>> AttributeResolver.is_valid("str")
            True
            >>> AttributeResolver.is_valid("医学")
            True
            >>> AttributeResolver.is_valid("未知属性")
            False
        """
        if not input_attribute:
            return False

        input_attribute = input_attribute.strip()
        return input_attribute in _VALID_INPUTS

    @staticmethod
    def get_standard_attributes() -> list[str]:
        """
        获取所有标准属性列表

        Returns:
            标准属性名列表（按字母顺序）
        """
        return STANDARD_ATTRIBUTES.copy()

    @staticmethod
    def get_all_valid_inputs() -> list[str]:
        """
        获取所有有效输入列表（标准属性 + 别名）

        Returns:
            有效输入列表
        """
        return sorted(list(_VALID_INPUTS))

    @staticmethod
    def get_aliases_for(standard_attribute: str) -> list[str]:
        """
        获取指定标准属性的所有别名

        Args:
            standard_attribute: 标准属性名

        Returns:
            别名列表，如果属性不存在返回空列表

        Example:
            >>> AttributeResolver.get_aliases_for("医学及生命科学")
            ['医学', '生命科学']
            >>> AttributeResolver.get_aliases_for("力量")
            []
        """
        if standard_attribute not in _STANDARD_ATTRIBUTE_SET:
            return []

        aliases = []
        for alias, attr in ALL_ALIASES.items():
            if attr == standard_attribute:
                aliases.append(alias)
        return aliases

    @staticmethod
    def get_attribute_display_name(input_attribute: str) -> str | None:
        """
        获取属性的展示名称

        如果输入是别名，返回标准属性名 + 别名信息
        如果输入是标准属性，只返回标准属性名

        Args:
            input_attribute: 属性输入

        Returns:
            展示名称，非法输入返回 None

        Example:
            >>> AttributeResolver.get_attribute_display_name("力量")
            '力量'
            >>> AttributeResolver.get_attribute_display_name("医学")
            '医学及生命科学（别名：医学）'
        """
        standard = AttributeResolver.resolve(input_attribute)
        if not standard:
            return None

        # 如果输入的就是标准名，直接返回
        if input_attribute.strip() == standard:
            return standard

        # 如果是别名，返回带别名信息的展示
        return f"{standard}（别名：{input_attribute.strip()}）"

    @staticmethod
    def is_scope(input_attribute: str) -> bool:
        """
        检查输入是否是特殊范围

        Args:
            input_attribute: 属性输入

        Returns:
            True 如果是特殊范围（物理、思维、所有/全部）
        """
        if not input_attribute:
            return False
        return input_attribute.strip() in _SPECIAL_SCOPES

    @staticmethod
    def get_scope_attributes(scope: str) -> list[str]:
        """
        获取特殊范围对应的属性列表

        Args:
            scope: 特殊范围名（物理、思维、所有/全部）

        Returns:
            属性列表，如果范围不存在返回空列表

        Example:
            >>> AttributeResolver.get_scope_attributes("物理")
            ['体质', '力量', '敏捷']
            >>> AttributeResolver.get_scope_attributes("思维")
            ['意志', '教育', '智力', '医学及生命科学', ...]
        """
        scope = scope.strip()
        if scope in SCOPE_ATTRIBUTES:
            return SCOPE_ATTRIBUTES[scope]
        return []


# 全局单例
attribute_resolver = AttributeResolver()
