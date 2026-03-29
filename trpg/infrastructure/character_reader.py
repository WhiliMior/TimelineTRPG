"""
角色属性读取模块 - 统一的角色数据出口
迁移自老项目 Game/Runtime/Attribute/AttributeReader.py

提供统一的接口获取角色属性数据：
- 获取激活角色的属性
- 获取指定角色的属性
- 支持属性别名映射
"""
import math
from typing import Dict, Optional, Union

from .storage import StorageBackend
from .config.game_config import game_config
from .attribute_resolver import AttributeResolver


# 属性别名配置（支持中英文）- 已迁移到 attribute_resolver.py
# 此处保留向后兼容
ATTRIBUTE_ALIASES: Dict[str, str] = {
    # 英文别名 -> 中文属性名
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
}


class CharacterReader:
    """
    角色属性读取器
    
    提供统一的接口获取角色属性数据
    """
    
    @staticmethod
    def get_active_character(user_id: str) -> Optional[Dict]:
        """
        获取当前激活的角色
        
        Args:
            user_id: 用户ID
        
        Returns:
            角色数据字典，如果不存在返回 None
        """
        characters = StorageBackend.load_characters(user_id)
        for char in characters:
            if char.get('active', False):
                return char
        return None
    
    @staticmethod
    def get_character_by_name(user_id: str, character_name: str) -> Optional[Dict]:
        """
        根据角色名获取角色
        
        Args:
            user_id: 用户ID
            character_name: 角色名
        
        Returns:
            角色数据字典，如果不存在返回 None
        """
        return StorageBackend.get_character(user_id, character_name)
    
    @staticmethod
    def get_character_raw_attributes(user_id: str, character_name: str = None) -> Optional[Dict]:
        """
        获取指定角色的原始属性（经过复杂计算，未受buff影响）
        
        Args:
            user_id: 用户ID
            character_name: 角色名，如果为None则获取激活角色
        
        Returns:
            属性字典，如果角色不存在返回 None
        """
        # 获取角色数据
        if character_name:
            character = StorageBackend.get_character(user_id, character_name)
        else:
            character = CharacterReader.get_active_character(user_id)
        
        if not character:
            return None
        
        # 从角色的data字段获取基础属性
        basic_attributes = character.get("data", {})
        
        # 使用 create_raw_attributes 进行复杂计算
        raw_attributes = CharacterReader.create_raw_attributes(basic_attributes, user_id, character_name)
        
        return raw_attributes
    
    @staticmethod
    def get_character_final_attributes(user_id: str, character_name: str = None) -> Optional[Dict]:
        """
        获取指定角色的最终属性（经过buff影响后的属性，包含交涉加成）
        与老项目 AttributeReader.py 的 get_character_final_attributes 保持一致
        
        Args:
            user_id: 用户ID
            character_name: 角色名，如果为None则获取激活角色
        
        Returns:
            属性字典，如果角色不存在返回 None
        """
        # 先获取原始属性
        raw_attributes = CharacterReader.get_character_raw_attributes(user_id, character_name)
        if not raw_attributes:
            return None

        # 获取角色数据以获取buffs
        if character_name:
            character = StorageBackend.get_character(user_id, character_name)
        else:
            character = CharacterReader.get_active_character(user_id)

        if not character:
            return raw_attributes

        # 应用buff修正
        buffs = character.get("buffs", [])
        final_attributes = CharacterReader.apply_buffs_to_attributes(raw_attributes, buffs)

        # 计算最终交涉属性（使用经过buff修正的属性值）
        final_attributes['交涉'] = CharacterReader._calculate_negotiation_buff(
            final_attributes,
            character,
            final_attributes.get('物理', 0),
            final_attributes.get('思维', 0)
        )

        return final_attributes
    
    @staticmethod
    def get_active_character_attributes(user_id: str, include_buffs: bool = True) -> Optional[Dict]:
        """
        获取当前激活角色的属性（便捷方法）
        
        Args:
            user_id: 用户ID
            include_buffs: 是否包含buff修正
        
        Returns:
            属性字典，如果角色不存在返回 None
        """
        if include_buffs:
            return CharacterReader.get_character_final_attributes(user_id, None)
        else:
            return CharacterReader.get_character_raw_attributes(user_id, None)
    
    @staticmethod
    def get_attribute_value(user_id: str, attribute_name: str, include_buffs: bool = True) -> Optional[float]:
        """
        获取指定属性的值
        
        Args:
            user_id: 用户ID
            attribute_name: 属性名（支持别名）
            include_buffs: 是否包含buff修正
        
        Returns:
            属性值，如果角色不存在返回 None
        """
        # 解析属性名
        resolved_name = CharacterReader.resolve_attribute_name(attribute_name)
        
        # 获取属性
        if include_buffs:
            attributes = CharacterReader.get_character_final_attributes(user_id, None)
        else:
            attributes = CharacterReader.get_character_raw_attributes(user_id, None)
        
        if not attributes:
            return None
        
        value = attributes.get(resolved_name)
        if value is None:
            return None
        
        if CharacterReader.is_number(value):
            return float(value)
        
        return None
    
    @staticmethod
    def resolve_attribute_name(attribute: str) -> Optional[str]:
        """
        解析属性名称，使用别名映射
        
        Args:
            attribute: 属性名或别名
        
        Returns:
            标准化的属性名，如果输入不合法返回 None
        """
        # 使用 AttributeResolver 进行解析
        resolved = AttributeResolver.resolve(attribute)
        if resolved:
            return resolved
        
        # 向后兼容：检查旧的 ATTRIBUTE_ALIASES
        if attribute in ATTRIBUTE_ALIASES:
            return ATTRIBUTE_ALIASES[attribute]
        
        # 如果是标准属性直接返回
        return attribute
    
    @staticmethod
    def is_number(value) -> bool:
        """
        检查值是否为数字
        """
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except (ValueError, TypeError):
                return False
        return False
    
    @staticmethod
    def apply_buffs_to_attributes(raw_attributes: Dict, buffs: list) -> Dict:
        """
        将buff应用到原始属性上，生成最终属性
        
        Args:
            raw_attributes: 原始属性字典
            buffs: buff列表
        
        Returns:
            应用buff后的属性字典
        """
        final_attributes = raw_attributes.copy()
        
        if not buffs:
            return final_attributes
        
        # 遍历每一个属性，计算其受buff影响后的值
        for attr_name, attr_value in raw_attributes.items():
            if CharacterReader.is_number(attr_value):
                # 获取影响这个属性的所有buff
                buffs_for_attr = CharacterReader._get_buffs_for_attribute(attr_name, buffs)
                # 按照buff计算逻辑对属性值进行计算
                final_value = CharacterReader._calculate_buff_impact(attr_value, buffs_for_attr)
                final_attributes[attr_name] = final_value
        
        return final_attributes
    
    @staticmethod
    def _get_buffs_for_attribute(attribute_name: str, buffs: list) -> list:
        """
        获取影响指定属性的所有buff
        与老项目 AttributeReader.py 的 _get_buffs_for_attribute 保持一致
        支持：物理、思维、领域、所有/全部
        """
        relevant_buffs = []

        # 定义各范围影响的属性
        physical_attributes = {'敏捷', '力量', '体质'}
        mental_attributes = {'意志', '智力', '教育'}
        domain_attributes = {'医学及生命科学', '工程与科技', '军事与生存', '文学', '视觉及表演艺术'}

        for buff in buffs:
            scope = buff.get('attribute', '')
            # 同时支持'全部'和'所有'作为通用范围
            if scope == attribute_name or scope == '所有' or scope == '全部':
                relevant_buffs.append(buff)
            elif scope == '物理' and attribute_name in physical_attributes:
                relevant_buffs.append(buff)
            elif scope == '思维' and (attribute_name in mental_attributes or attribute_name in domain_attributes):
                relevant_buffs.append(buff)
            elif scope == '领域' and attribute_name in domain_attributes:
                relevant_buffs.append(buff)

        return relevant_buffs
    
    @staticmethod
    def _calculate_buff_impact(attribute_value: float, buffs_for_attribute: list) -> float:
        """
        按照buff计算逻辑对属性值进行计算：
        (((原始属性+直接加算)*直接乘算)+最终加算)*最终乘算
        """
        if not buffs_for_attribute:
            return attribute_value
        
        direct_add = 0
        direct_multiply = 1
        final_add = 0
        final_multiply = 1
        
        for buff in buffs_for_attribute:
            buff_type = buff.get('type', '')
            buff_value = buff.get('value', 0)
            
            if CharacterReader.is_number(buff_value):
                buff_value = float(buff_value)
            else:
                continue
            
            if buff_type == '直接加算':
                direct_add += buff_value
            elif buff_type == '直接乘算':
                direct_multiply += buff_value
            elif buff_type == '最终加算':
                final_add += buff_value
            elif buff_type == '最终乘算':
                final_multiply += buff_value
        
        # 应用计算公式
        result = (((attribute_value + direct_add) * direct_multiply) + final_add) * final_multiply
        return game_config.round_value(result, "attribute")

    @staticmethod
    def _read_basic_attribute(character_data: Dict, attribute_name: str) -> float:
        """
        读取基础属性值
        """
        value = character_data.get(attribute_name)
        if CharacterReader.is_number(value):
            return float(value)
        return 0.0

    @staticmethod
    def _reserve_two_decimals(number) -> float:
        """
        保留两位小数（已废弃，请使用 _reserve_weight_decimals）
        """
        if CharacterReader.is_number(number):
            return round(float(number), 2)
        return number
    
    @staticmethod
    def _reserve_weight_decimals(number) -> float:
        """
        根据 game_config 中的 weight 精度设置保留小数
        """
        if CharacterReader.is_number(number):
            return game_config.round_value(float(number), "weight")
        return number

    @staticmethod
    def _calculate_full_weight(check_strength: float, level: float) -> float:
        """
        计算总负重
        """
        if level == 0:
            full_weight = 0
        else:
            full_weight = check_strength * 10 / level
        return full_weight

    @staticmethod
    def _calculate_revision_weight(weight: float, full_weight: float) -> float:
        """
        计算负重修正
        """
        if full_weight == 0:
            revision_weight = 1
        else:
            revision_weight = -1 * math.pow(weight / full_weight, 2) + 1
        if revision_weight <= 0:
            revision_weight = 0.01
        return revision_weight

    @staticmethod
    def _calculate_cash(character: Dict) -> float:
        """
        计算现金属性
        """
        # 从 character['data'] 中读取资产属性
        data = character.get('data', {})
        wealth = CharacterReader._read_basic_attribute(data, '资产')
        if wealth < 0:
            cash = (math.pow(wealth, 4) / math.pow(10, 4)) * -1
        else:
            cash = math.pow(wealth, 4) / math.pow(10, 4)
        return CharacterReader._reserve_two_decimals(float(cash))
    
    @staticmethod
    def calculate_current_cash(inventory: Dict, character: Dict) -> float:
        """
        计算当前现金：将初始现金与所有现金变动记录相加
        """
        # 获取初始现金（从 character 计算）
        initial_cash = CharacterReader._calculate_cash(character)
        
        # 获取现金变动记录的总和
        cash_records = inventory.get('cash_records', [])
        total_changes = sum(record.get('amount', 0) for record in cash_records)
        
        # 当前现金 = 初始现金 + 变动总和
        current_cash = initial_cash + total_changes
        return CharacterReader._reserve_two_decimals(float(current_cash))

    @staticmethod
    def create_raw_attributes(character: Dict, user_id: str = None, character_name: str = None) -> Dict:
        """
        创建原始高级属性（基于基础属性的复杂计算）
        与老项目 AttributeReader.py 的 create_raw_attributes 保持一致
        """
        attribute_dict = {}

        # 获取当前负重（物品+武器）
        current_weight = None
        if user_id and character_name:
            current_weight = CharacterReader.get_character_current_weight(user_id, character_name)

        def add_attribute(key: str, value):
            if CharacterReader.is_number(value):
                value = float(value)
                value = CharacterReader._reserve_two_decimals(value)
            attribute_dict[key] = value

        # 基础属性列表
        basic_attributes_list = [
            '体质', '敏捷', '力量', '意志', '教育', '智力',
            '医学及生命科学', '工程与科技', '军事与生存', '文学', '视觉及表演艺术'
        ]

        basic_values = {}
        for attr in basic_attributes_list:
            basic_values[attr] = CharacterReader._read_basic_attribute(character, attr)

        # 计算基础中间值
        level = CharacterReader._read_basic_attribute(character, '等级')
        ability = level * 100

        ratio = CharacterReader._read_basic_attribute(character, '物理思维比值')
        physical = ability - (ratio * level) / 10

        mental = ability - physical

        # 年龄修正
        age = CharacterReader._read_basic_attribute(character, '年龄')
        adult_age = CharacterReader._read_basic_attribute(character, '成年年龄')
        if adult_age == 0:
            revision_age_physical = 1
            revision_age_mental = 1
        else:
            age_ratio = age / (adult_age * 1.5)
            if age_ratio <= 0:
                revision_age_physical = 1
            else:
                revision_age_physical = math.cos(math.log(age_ratio, math.e)) + 0.12
                if revision_age_physical <= 0:
                    revision_age_physical = 0.01

            age_ratio_mental = age / adult_age
            if age_ratio_mental <= 0:
                revision_age_mental = 1
            else:
                revision_age_mental = math.log(age_ratio_mental, 10) + 0.8

        # 体型修正
        size = CharacterReader._read_basic_attribute(character, '体型')
        standard_size = CharacterReader._read_basic_attribute(character, '标准体型')
        if standard_size == 0:
            revision_size = 1
        else:
            size_ratio = size / standard_size
            if size_ratio <= 0:
                revision_size = 1
            else:
                revision_size = math.log(size_ratio, math.e) + 1
        if revision_size <= 0:
            revision_size = 0.01

        # 负重修正
        strength_raw = basic_values['力量']
        revised_physical = physical * revision_age_physical
        check_strength = revised_physical * strength_raw / 100 * revision_size
        full_weight = CharacterReader._calculate_full_weight(check_strength, level)

        # 使用当前负重（物品+武器），而非角色data中的静态值
        weight = current_weight if current_weight is not None else 0.0
        revision_weight = CharacterReader._calculate_revision_weight(weight, full_weight)

        # 计算并替换物理系属性
        new_constitution = revised_physical * basic_values['体质'] / 100 * revision_size
        add_attribute('体质', new_constitution)

        new_strength = revised_physical * basic_values['力量'] / 100 * revision_size
        add_attribute('力量', new_strength)

        new_dexterity = revised_physical * basic_values['敏捷'] / 100 * revision_weight
        add_attribute('敏捷', new_dexterity)

        # 计算并替换思维系属性
        revised_mental = mental * revision_age_mental

        # 替换基础思维属性
        add_attribute('意志', revised_mental * basic_values['意志'] / 100)
        add_attribute('教育', revised_mental * basic_values['教育'] / 100)
        add_attribute('智力', revised_mental * basic_values['智力'] / 100)

        # 替换领域属性
        add_attribute('医学及生命科学', revised_mental * basic_values['医学及生命科学'] / 100)
        add_attribute('工程与科技', revised_mental * basic_values['工程与科技'] / 100)
        add_attribute('军事与生存', revised_mental * basic_values['军事与生存'] / 100)
        add_attribute('文学', revised_mental * basic_values['文学'] / 100)
        add_attribute('视觉及表演艺术', revised_mental * basic_values['视觉及表演艺术'] / 100)

        # 添加辅助属性
        add_attribute('现金', CharacterReader._calculate_cash(character))

        return attribute_dict

    @staticmethod
    def _calculate_negotiation_buff(attribute_dict: Dict, character: Dict, physical: float, mental: float) -> float:
        """
        计算交涉加成属性
        与老项目 AttributeReader.py 的 _calculate_negotiation_buff 保持一致
        """
        literature = attribute_dict.get('文学', 0)
        visual_and_performing_art = attribute_dict.get('视觉及表演艺术', 0)
        intelligence = attribute_dict.get('智力', 0)
        # 从角色的data字段获取外貌值
        appearance = CharacterReader._read_basic_attribute(character.get('data', {}), '外貌')

        if physical == 0:
            mental_physical_ratio = 1
        else:
            mental_physical_ratio = mental / physical
            if mental_physical_ratio <= 0:
                mental_physical_ratio = 1

        # 处理外貌值，避免math domain error
        if appearance <= 0:
            appearance_ratio = 0
        else:
            appearance_ratio = math.log(appearance / 50, math.e) + 1

        # 处理mental_physical_ratio，避免log(0)或log(负数)的错误
        if mental_physical_ratio <= 0:
            mental_physical_ratio_log = 0
        else:
            mental_physical_ratio_log = math.log(mental_physical_ratio, 10) + 1

        negotiation_buff = (literature + visual_and_performing_art + intelligence) * \
                           mental_physical_ratio_log * \
                           appearance_ratio
        return CharacterReader._reserve_two_decimals(negotiation_buff)

    @staticmethod
    def get_character_full_weight(user_id: str, character_name: str = None) -> Optional[float]:
        """
        获取角色的总负重容量
        与老项目 AttributeReader.py 的 get_character_full_weight 保持一致
        """
        # 获取角色数据
        if character_name:
            character = StorageBackend.get_character(user_id, character_name)
        else:
            character = CharacterReader.get_active_character(user_id)

        if not character:
            return None

        # 从角色的data字段获取基础属性
        basic_attributes = character.get("data", {})

        # 计算 full_weight
        full_weight = CharacterReader._calculate_full_weight_from_character(basic_attributes)
        return full_weight

    @staticmethod
    def _calculate_full_weight_from_character(character: Dict) -> float:
        """
        从角色基础属性计算总负重容量
        与老项目 AttributeReader.py 的 _calculate_full_weight_from_character 保持一致
        """
        # 获取基础属性值
        basic_values = {}
        basic_attributes_list = [
            '体质', '敏捷', '力量', '意志', '教育', '智力',
            '医学及生命科学', '工程与科技', '军事与生存', '文学', '视觉及表演艺术'
        ]

        for attr in basic_attributes_list:
            basic_values[attr] = CharacterReader._read_basic_attribute(character, attr)

        # 计算基础中间值
        level = CharacterReader._read_basic_attribute(character, '等级')
        ability = level * 100

        ratio = CharacterReader._read_basic_attribute(character, '物理思维比值')
        physical = ability - (ratio * level) / 10

        # 年龄修正
        age = CharacterReader._read_basic_attribute(character, '年龄')
        adult_age = CharacterReader._read_basic_attribute(character, '成年年龄')
        if adult_age == 0:
            revision_age_physical = 1
        else:
            age_ratio = age / (adult_age * 1.5)
            if age_ratio <= 0:
                revision_age_physical = 1
            else:
                revision_age_physical = math.cos(math.log(age_ratio, math.e)) + 0.12
                if revision_age_physical <= 0:
                    revision_age_physical = 0.01

        # 体型修正
        size = CharacterReader._read_basic_attribute(character, '体型')
        standard_size = CharacterReader._read_basic_attribute(character, '标准体型')
        if standard_size == 0:
            revision_size = 1
        else:
            size_ratio = size / standard_size
            if size_ratio <= 0:
                revision_size = 1
            else:
                revision_size = math.log(size_ratio, math.e) + 1
        if revision_size <= 0:
            revision_size = 0.01

        # 计算负重相关值
        strength_raw = basic_values['力量']
        revised_physical = physical * revision_age_physical
        check_strength = revised_physical * strength_raw / 100 * revision_size
        full_weight = CharacterReader._calculate_full_weight(check_strength, level)

        return CharacterReader._reserve_weight_decimals(full_weight)

    @staticmethod
    def get_character_current_weight(user_id: str, character_name: str = None) -> Optional[float]:
        """
        获取角色当前负重（物品 + 武器）
        统一的接口，计算背包物品和武器的总负重
        """
        if character_name:
            character = StorageBackend.get_character(user_id, character_name)
        else:
            character = CharacterReader.get_active_character(user_id)

        if not character:
            return None

        total_weight = 0.0

        # 计算物品负重 - 从角色数据中获取 inventory
        inventory = character.get('inventory', {})
        if inventory:
            items = inventory.get('items', [])
            for item in items:
                quantity = item.get('quantity', 1)
                weight = item.get('weight', 0.0)
                total_weight += quantity * weight

        # 计算武器负重
        weapons = character.get('weapons', [])
        for weapon in weapons:
            weight = weapon.get('weight', 0.0)
            if isinstance(weight, (int, float)):
                total_weight += weight

        return CharacterReader._reserve_weight_decimals(total_weight)


# 全局单例
character_reader = CharacterReader()
