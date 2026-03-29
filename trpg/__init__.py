"""
TRPG 业务层模块
包含所有 TRPG 相关的业务逻辑模块

注意：此文件已废弃，请直接从 service.xxx 模块导入
"""
from .service.dice.dice import roll_dice_module
from .service.examination.examination import examination_module
from .service.examination.target import target_module
from .service.character.character import character_module
from .service.buff.buff import buff_module
from .service.resource.modifier import resource_modifier_module
from .service.negotiation.negotiation import negotiation_module
from .service.battle.timeline import timeline_module
from .service.battle.battle import battle_module
from .service.inventory.inventory import inventory_module
from .service.resource.resource import resource_record_module
from .service.weapon.weapon import weapon_module
from .service.level.level import level_module

__all__ = [
    "roll_dice_module",
    "examination_module",
    "target_module",
    "character_module",
    "buff_module",
    "resource_modifier_module",
    "negotiation_module",
    "timeline_module",
    "battle_module",
    "inventory_module",
    "resource_record_module",
    "weapon_module",
    "level_module",
]
