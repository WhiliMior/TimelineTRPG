"""
角色图片生成器 - 生成角色属性图片

基于老项目 Game/Character/ 中的 get_character_picture 函数重构。
使用 CharacterReader 获取最终属性，支持 buff/debuff 显示。
"""

import logging
import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from PIL import Image as PilImage, ImageFont, ImageDraw

logger = logging.getLogger("TimelineTRPG.character_picture")

from .storage import StorageBackend, StorageType
from .character_reader import CharacterReader
from .config.game_config import game_config


@dataclass
class AttributeConfig:
    """属性配置"""
    name: str  # 属性名
    short_name: str  # 简写
    icon: str  # 图标名
    x_icon: int  # 图标x坐标
    y_icon: int  # 图标y坐标
    x_text: int  # 文字x坐标
    y_text: int  # 文字y坐标
    font_size: int = 33  # 字体大小


@dataclass  
class RevisionConfig:
    """修正项配置"""
    label: str  # 显示标签
    icon: str  # 图标名
    x_icon: int
    y_icon: int
    x_text: int
    y_text: int
    color: Tuple[int, int, int] = (0, 0, 0)  # 文字颜色


class CharacterPictureGenerator:
    """
    角色图片生成器
    
    生成格式与老项目完全一致的角色属性卡片图片。
    支持显示 buff/debuff 差异（绿色=增加，红色=减少）。
    """
    
    # 字体配置
    # 优先使用插件自带的思源黑体Variable字体，跨平台兼容
    FONT_DEFAULT = 'NotoSansSC-VariableFont_wght.ttf'
    FONT_BOLD = 'NotoSansSC-Bold.ttf'
    FONT_SIZE_LARGE = 33
    FONT_SIZE_SMALL = 28
    FONT_SIZE_BUFF = 24  # buff字体大小（比属性字体小）
    
    # 插件字体目录（相对于插件根目录）
    FONT_DIR = "fonts"
    
    # 颜色配置
    COLOR_BLACK = (0, 0, 0)
    COLOR_WHITE = (255, 255, 255)
    COLOR_RED = (220, 20, 60)  # 减少-红色
    COLOR_GREEN = (34, 139, 34)  # 增加-绿色
    
    # 区域颜色
    COLOR_HEADER = (80, 156, 254)  # 蓝色
    COLOR_PHYSICAL = (244, 176, 132)  # 橙色
    COLOR_MENTAL = (142, 169, 219)  # 浅蓝
    COLOR_REVISION = (177, 177, 177)  # 灰色
    COLOR_DOMAIN = (236, 178, 0)  # 黄色
    
    # 修正项颜色
    COLOR_AGE_PHYSICAL = (237, 125, 49)  # 物理年龄修正-橙色
    COLOR_AGE_MENTAL = (68, 114, 196)  # 思维年龄修正-蓝色
    
    # 基础信息配置
    BASIC_INFO_CONFIGS = [
        # 左侧（种族、性别、职业）
        AttributeConfig('种族', '', 'Race.png', 76, 298, 126, 300),
        AttributeConfig('性别', '', 'Gender.png', 76, 380, 126, 380),
        AttributeConfig('职业', '', 'Job.png', 76, 462, 126, 460),
        # 右侧（外貌、资产、年龄、体型）
        AttributeConfig('外貌', '', 'Appearence.png', 426, 287, 476, 288, FONT_SIZE_SMALL),
        AttributeConfig('资产', '', 'Wealth.png', 426, 348, 476, 350, FONT_SIZE_SMALL),
        AttributeConfig('年龄', '', 'Age.png', 426, 410, 476, 412, FONT_SIZE_SMALL),
        AttributeConfig('体型', '', 'Size.png', 426, 471, 476, 474, FONT_SIZE_SMALL),
    ]
    
    # 物理属性配置
    PHYSICAL_ATTRS = [
        AttributeConfig('体质', '体', 'Constitution.png', 76, 731, 126, 726),
        AttributeConfig('敏捷', '敏', 'Dexterity.png', 76, 793, 126, 792),
        AttributeConfig('力量', '力', 'Strengh.png', 76, 860, 126, 858),
    ]
    
    # 思维属性配置
    MENTAL_ATTRS = [
        AttributeConfig('意志', '意', 'Willpower.png', 426, 726, 476, 726),
        AttributeConfig('教育', '教', 'Education.png', 426, 792, 476, 792),
        AttributeConfig('智力', '智', 'Intelligence.png', 426, 860, 476, 858),
    ]
    
    # 领域属性配置
    DOMAIN_ATTRS = [
        AttributeConfig('医学及生命科学', '医', 'Medical.png', 426, 1008, 476, 1008, FONT_SIZE_SMALL),
        AttributeConfig('工程与科技', '工', 'Engineer.png', 426, 1074, 476, 1074, FONT_SIZE_SMALL),
        AttributeConfig('军事与生存', '军', 'Survival.png', 426, 1140, 476, 1140, FONT_SIZE_SMALL),
        AttributeConfig('文学', '文', 'Literature.png', 426, 1205, 476, 1206, FONT_SIZE_SMALL),
        AttributeConfig('视觉及表演艺术', '艺', 'Art.png', 426, 1270, 476, 1272, FONT_SIZE_SMALL),
    ]
    
    # 修正项配置
    REVISION_CONFIGS = [
        RevisionConfig('负重', 'Weight.png', 76, 1012, 126, 1008),
        RevisionConfig('', 'Weight.png', 76, 1074, 126, 1074),  # 负重修正
        RevisionConfig('', 'Age.png', 76, 1138, 126, 1140, COLOR_AGE_PHYSICAL),  # 物理年龄修正
        RevisionConfig('', '', 0, 1206, 126, 1206, COLOR_AGE_MENTAL),  # 思维年龄修正
        RevisionConfig('', 'Size.png', 76, 1274, 126, 1272, COLOR_WHITE),  # 体型修正
    ]
    
    # 背景板配置: (x, y, width, height, radius, color)
    BACKGROUND_CONFIGS = [
        (44, 268, 662, 262, 10, COLOR_HEADER),
        (44, 574, 310, 360, 10, COLOR_PHYSICAL),
        (396, 574, 310, 360, 10, COLOR_MENTAL),
        (44, 978, 310, 360, 10, COLOR_REVISION),
        (396, 978, 310, 360, 10, COLOR_DOMAIN),
    ]
    
    # 字体缓存
    _font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
    
    @classmethod
    def get_icons_dir(cls) -> Path:
        """获取图标目录路径"""
        plugin_root = Path(__file__).parent.parent.parent
        return plugin_root / "icons"
    
    @classmethod
    def get_font(cls, size: int) -> ImageFont.FreeTypeFont:
        """获取字体（带缓存，优先使用插件自带字体）"""
        return cls._load_font(cls.FONT_DEFAULT, size)
    
    @classmethod
    def get_bold_font(cls, size: int) -> ImageFont.FreeTypeFont:
        """获取粗体字体（带缓存）"""
        return cls._load_font(cls.FONT_BOLD, size)
    
    @classmethod
    def _load_font(cls, font_file: str, size: int) -> ImageFont.FreeTypeFont:
        """加载字体的内部方法（带缓存）"""
        cache_key = (font_file, size)
        if cache_key not in cls._font_cache:
            # 优先尝试从插件字体目录加载
            plugin_root = Path(__file__).parent.parent.parent
            local_font_path = plugin_root / cls.FONT_DIR / "Noto_Sans_SC" / font_file
            
            logger.debug(f"尝试加载字体: {local_font_path}")
            logger.debug(f"字体文件是否存在: {local_font_path.exists()}")
            
            font_loaded = False
            # 1. 首先尝试插件自带字体
            if local_font_path.exists():
                try:
                    cls._font_cache[cache_key] = ImageFont.truetype(str(local_font_path), size)
                    font_loaded = True
                    logger.info(f"成功加载插件字体: {local_font_path}, size={size}")
                except Exception as e:
                    logger.warning(f"加载插件字体失败: {e}")
            
            # 2. 插件字体失败，尝试系统字体
            if not font_loaded:
                system_fonts = [
                    "msyh.ttc",          # Windows 微软雅黑
                    "PingFang.ttc",      # macOS
                    "Heiti.ttc",         # macOS 黑体
                    "SimHei.ttf",        # Windows 黑体
                ]
                for font_name in system_fonts:
                    try:
                        cls._font_cache[cache_key] = ImageFont.truetype(font_name, size)
                        font_loaded = True
                        logger.info(f"成功加载系统字体: {font_name}, size={size}")
                        break
                    except Exception as e:
                        logger.debug(f"系统字体 {font_name} 不存在或加载失败: {e}")
            
            # 3. 都失败则使用默认字体（显示方框）
            if not font_loaded:
                logger.warning(f"所有字体加载失败，使用PIL默认字体，显示可能异常")
                cls._font_cache[cache_key] = ImageFont.load_default()
        
        return cls._font_cache[cache_key]
    
    @classmethod
    def generate_character_picture(
        cls,
        user_id: str,
        character_name: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        生成角色属性图片
        
        Args:
            user_id: 用户ID
            character_name: 角色名，如果为None则获取激活角色
            output_path: 输出路径，如果为None则使用默认路径（character.json同目录下temp.png）
        
        Returns:
            图片路径，如果失败返回None
        """
        # 获取角色数据
        if character_name:
            character = StorageBackend.get_character(user_id, character_name)
        else:
            character = CharacterReader.get_active_character(user_id)
        
        if not character:
            return None
        
        # 获取角色的原始属性和最终属性
        raw_attributes = CharacterReader.get_character_raw_attributes(user_id, character.get('name'))
        final_attributes = CharacterReader.get_character_final_attributes(user_id, character.get('name'))
        
        if not raw_attributes or not final_attributes:
            return None
        
        # 准备数据
        data = cls._prepare_character_data(user_id, character, raw_attributes, final_attributes)
        
        # 确定输出路径
        if output_path is None:
            char_dir = StorageBackend._get_entity_dir(StorageType.USER, user_id)
            output_path = char_dir / "temp.png"
        
        # 生成图片
        cls._draw_character_image(output_path, data)
        
        return output_path
    
    @classmethod
    def _prepare_character_data(
        cls,
        user_id: str,
        character: Dict,
        raw_attributes: Dict,
        final_attributes: Dict,
    ) -> Dict:
        """准备角色数据"""
        char_data = character.get('data', {})
        
        # 基础信息
        data = {
            'name': character.get('name', '未知'),
            'level': char_data.get('等级', 1),
            'appearance': char_data.get('外貌', 0),
            'wealth': char_data.get('资产', 0),
            'age': char_data.get('年龄', 0),
            'adult_age': char_data.get('成年年龄', 0),
            'size': char_data.get('体型', 0),
            'standard_size': char_data.get('标准体型', 0),
            'race': char_data.get('种族', ''),
            'gender': char_data.get('性别', ''),
            'occupation': char_data.get('职业', ''),
        }
        
        # 物理/思维值
        data['physical'] = raw_attributes.get('物理', 0)
        data['mental'] = raw_attributes.get('思维', 0)
        
        # 计算修正值
        data['revision_age_physical'], data['revision_age_mental'] = cls._calculate_age_revision(
            data['age'], data['adult_age']
        )
        data['revision_size'] = cls._calculate_size_revision(data['size'], data['standard_size'])
        data['revised_physical'] = data['physical'] * data['revision_age_physical']
        data['revised_mental'] = data['mental'] * data['revision_age_mental']
        
        # HP/MP - 从resources获取当前值，从final_attributes获取上限
        resources = char_data.get('resources', {})
        
        # 体力上限 = 体质最终属性
        data['full_hitpoint'] = final_attributes.get('体质', 0)
        # 当前体力 = resources中的current_hp
        data['hp'] = resources.get('current_hp', data['full_hitpoint'])
        
        # 意志上限 = 意志最终属性
        data['full_willpower'] = final_attributes.get('意志', 0)
        # 当前意志 = resources中的current_mp
        data['mp'] = resources.get('current_mp', data['full_willpower'])
        
        # 负重
        weight = CharacterReader.get_character_current_weight(user_id, character.get('name')) or 0
        full_weight = CharacterReader.get_character_full_weight(user_id, character.get('name')) or 0
        data['weight'] = weight
        data['full_weight'] = full_weight
        data['revision_weight'] = cls._calculate_weight_revision(weight, full_weight)
        
        # 属性和buff差异
        data['final_attributes'] = final_attributes
        data['buff_diff'] = cls._calculate_buff_diff(raw_attributes, final_attributes)
        
        return data
    
    @classmethod
    def _calculate_age_revision(cls, age: int, adult_age: int) -> Tuple[float, float]:
        """计算年龄修正"""
        if adult_age <= 0:
            return 1.0, 1.0
        
        # 物理年龄修正
        age_ratio = age / (adult_age * 1.5)
        if age_ratio > 0:
            revision_physical = max(0.01, math.cos(math.log(age_ratio, math.e)) + 0.12)
        else:
            revision_physical = 1.0
        
        # 思维年龄修正
        age_ratio_mental = age / adult_age
        if age_ratio_mental > 0:
            revision_mental = math.log(age_ratio_mental, 10) + 0.8
        else:
            revision_mental = 1.0
        
        return revision_physical, revision_mental
    
    @classmethod
    def _calculate_size_revision(cls, size: int, standard_size: int) -> float:
        """计算体型修正"""
        if standard_size <= 0 or size <= 0:
            return 1.0
        size_ratio = size / standard_size
        return max(0.01, math.log(size_ratio, math.e) + 1)
    
    @classmethod
    def _calculate_weight_revision(cls, weight: float, full_weight: float) -> float:
        """计算负重修正"""
        if full_weight <= 0:
            return 1.0
        revision = -1 * math.pow(weight / full_weight, 2) + 1
        return max(0.01, revision)
    
    @classmethod
    def _calculate_buff_diff(cls, raw_attributes: Dict, final_attributes: Dict) -> Dict:
        """计算buff差异"""
        buff_diff = {}
        for attr, final_value in final_attributes.items():
            raw_value = raw_attributes.get(attr, 0)
            if final_value != raw_value:
                buff_diff[attr] = final_value - raw_value
        return buff_diff
    
    @classmethod
    def _draw_character_image(cls, output_path: Path, data: Dict):
        """绘制角色图片"""
        # 创建画布
        img = PilImage.new('RGB', (750, 1536), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # 绘制背景板
        cls._draw_backgrounds(draw)
        
        # 绘制头部信息
        cls._draw_header(img, draw, data)
        
        # 绘制基础信息
        cls._draw_basic_info(img, draw, data)
        
        # 绘制HP/MP
        cls._draw_hp_mp(draw, data)
        
        # 绘制属性（物理、思维、领域）
        cls._draw_attributes(img, draw, data)
        
        # 绘制修正信息
        cls._draw_revisions(img, draw, data)
        
        # 保存图片
        img.save(str(output_path))
    
    @classmethod
    def _draw_backgrounds(cls, draw: ImageDraw.Draw):
        """绘制背景板"""
        for x, y, w, h, r, color in cls.BACKGROUND_CONFIGS:
            cls._draw_rounded_rectangle(draw, x, y, w, h, r, color)
    
    @classmethod
    def _draw_rounded_rectangle(
        cls, draw: ImageDraw.Draw, x: int, y: int, w: int, h: int, r: int, color: Tuple[int, int, int]
    ):
        """绘制圆角矩形"""
        draw.rectangle((x + r, y, x + w - r, y + h), fill=color)
        draw.rectangle((x, y + r, x + w, y + h - r), fill=color)
        draw.ellipse((x, y, x + 2 * r, y + 2 * r), fill=color)
        draw.ellipse((x + w - 2 * r, y, x + w, y + 2 * r), fill=color)
        draw.ellipse((x, y + h - 2 * r, x + 2 * r, y + h), fill=color)
        draw.ellipse((x + w - 2 * r, y + h - 2 * r, x + w, y + h), fill=color)
    
    @classmethod
    def _draw_header(cls, img: PilImage.Image, draw: ImageDraw.Draw, data: Dict):
        """绘制头部信息"""
        icons_dir = cls.get_icons_dir()
        
        # 角色姓名
        cls._draw_icon_text(img, draw, icons_dir, 'Character.png', (76, 114), (126, 112), data['name'])
        
        # 等级
        cls._draw_icon_text(img, draw, icons_dir, 'Level.png', (76, 202), (126, 200), f"等级：{data['level']}")
    
    @classmethod
    def _draw_basic_info(cls, img: PilImage.Image, draw: ImageDraw.Draw, data: Dict):
        """绘制基础信息"""
        icons_dir = cls.get_icons_dir()
        
        # 左侧信息
        cls._draw_icon_text(img, draw, icons_dir, 'Race.png', (76, 298), (126, 300), f"种族：{data['race']}")
        cls._draw_icon_text(img, draw, icons_dir, 'Gender.png', (76, 380), (126, 380), f"性别：{data['gender']}")
        cls._draw_icon_text(img, draw, icons_dir, 'Job.png', (76, 462), (126, 460), f"职业：{data['occupation']}")
        
        # 右侧信息
        cls._draw_icon_text(img, draw, icons_dir, 'Appearence.png', (426, 287), (476, 288), 
                           f"外貌：{data['appearance']}", cls.FONT_SIZE_SMALL)
        cls._draw_icon_text(img, draw, icons_dir, 'Wealth.png', (426, 348), (476, 350),
                           f"资产：{data['wealth']}", cls.FONT_SIZE_SMALL)
        
        # 年龄（特殊格式）
        adult_age_str = f"[{data['adult_age']}]"
        text = f"年龄：{data['age']:<4} {adult_age_str:>5}"
        cls._draw_icon_text(img, draw, icons_dir, 'Age.png', (426, 410), (476, 412), text, cls.FONT_SIZE_SMALL)
        
        # 体型（特殊格式）
        standard_size_str = f"[{data['standard_size']}]"
        text = f"体型：{data['size']:<4} {standard_size_str:>5}"
        cls._draw_icon_text(img, draw, icons_dir, 'Size.png', (426, 471), (476, 474), text, cls.FONT_SIZE_SMALL)
    
    @classmethod
    def _draw_hp_mp(cls, draw: ImageDraw.Draw, data: Dict):
        """绘制HP/MP - 两行格式"""
        font_large = cls.get_bold_font(cls.FONT_SIZE_LARGE)
        
        # 向上移动一行（体质与敏捷间距66像素，半行约33像素）
        offset_y = -33
        
        # HP - 两行格式
        hp_ratio = int((data['hp'] / data['full_hitpoint']) * 100) if data['full_hitpoint'] > 0 else 0
        # 第一行：HP [百分比]
        hp_label = f"HP [{hp_ratio}%]"
        draw.text((76, 645 + offset_y), hp_label, cls.COLOR_BLACK, font=font_large)
        # 第二行：当前值/最大值
        hp_text = f"{int(data['hp'])}/{int(data['full_hitpoint'])}"
        draw.text((76, 685 + offset_y), hp_text, cls.COLOR_BLACK, font=font_large)
        
        # MP - 两行格式
        mp_ratio = int((data['mp'] / data['full_willpower']) * 100) if data['full_willpower'] > 0 else 0
        # 第一行：MP [百分比]
        mp_label = f"MP [{mp_ratio}%]"
        draw.text((426, 645 + offset_y), mp_label, cls.COLOR_BLACK, font=font_large)
        # 第二行：当前值/最大值
        mp_text = f"{int(data['mp'])}/{int(data['full_willpower'])}"
        draw.text((426, 685 + offset_y), mp_text, cls.COLOR_BLACK, font=font_large)
    
    @classmethod
    def _draw_attributes(cls, img: PilImage.Image, draw: ImageDraw.Draw, data: Dict):
        """绘制属性"""
        icons_dir = cls.get_icons_dir()
        final_attributes = data['final_attributes']
        buff_diff = data['buff_diff']
        
        # 物理属性
        for config in cls.PHYSICAL_ATTRS:
            value = final_attributes.get(config.name, 0)
            buff_amount = buff_diff.get(config.name, 0)
            cls._draw_attribute_with_icon(img, draw, icons_dir, config, value, buff_amount)
        
        # 思维属性
        for config in cls.MENTAL_ATTRS:
            value = final_attributes.get(config.name, 0)
            buff_amount = buff_diff.get(config.name, 0)
            cls._draw_attribute_with_icon(img, draw, icons_dir, config, value, buff_amount)
        
        # 领域属性
        for config in cls.DOMAIN_ATTRS:
            value = final_attributes.get(config.name, 0)
            buff_amount = buff_diff.get(config.name, 0)
            cls._draw_attribute_with_icon(img, draw, icons_dir, config, value, buff_amount)
    
    @classmethod
    def _draw_attribute_with_icon(
        cls, img: PilImage.Image, draw: ImageDraw.Draw, icons_dir: Path, config: AttributeConfig, value: float, buff_amount: float
    ):
        """绘制单个属性（带图标）"""
        # 绘制图标
        icon_path = os.path.join(str(icons_dir), config.icon)
        if os.path.exists(icon_path):
            try:
                icon = PilImage.open(icon_path)
                # 确保图标使用RGBA模式以支持透明度
                if icon.mode != 'RGBA':
                    icon = icon.convert('RGBA')
                img.paste(icon, (config.x_icon, config.y_icon), icon)
            except Exception:
                pass
        
        # 绘制文字和buff
        cls._draw_attribute_with_buff(draw, config.short_name, value, buff_amount, (config.x_text, config.y_text), config.font_size)
    
    @classmethod
    def _draw_icon_text(
        cls, img: PilImage.Image, draw: ImageDraw.Draw, icons_dir: Path, icon: str, icon_coord: Tuple[int, int], 
        text_coord: Tuple[int, int], text: str, font_size: int = FONT_SIZE_LARGE, text_color: Tuple[int, int, int] = None
    ):
        """绘制图标和文字"""
        icon_path = os.path.join(str(icons_dir), icon)
        if os.path.exists(icon_path):
            try:
                icon_img = PilImage.open(icon_path)
                # 确保图标使用RGBA模式以支持透明度
                if icon_img.mode != 'RGBA':
                    icon_img = icon_img.convert('RGBA')
                img.paste(icon_img, icon_coord, icon_img)
            except Exception:
                pass
        if text_color is None:
            text_color = cls.COLOR_BLACK
        draw.text(text_coord, text, text_color, font=cls.get_bold_font(font_size))
    
    @classmethod
    def _draw_revisions(cls, img: PilImage.Image, draw: ImageDraw.Draw, data: Dict):
        """绘制修正信息"""
        icons_dir = cls.get_icons_dir()
        
        # 负重
        text = f"负重 {int(data['weight'])}/{int(data['full_weight'])}"
        cls._draw_icon_text(img, draw, icons_dir, 'Weight.png', (76, 1008), (126, 1008), text)
        
        # 负重修正
        revision = int(data['revision_weight'] * 100)
        text = f"修正 [{revision}%]"
        cls._draw_icon_text(img, draw, icons_dir, 'Weight.png', (76, 1074), (126, 1074), text)
        
        # 物理年龄修正
        revision = int(data['revision_age_physical'] * 100)
        text = f"修正 [{revision}%]"
        cls._draw_icon_text(img, draw, icons_dir, 'Age.png', (76, 1140), (126, 1140), text, font_size=cls.FONT_SIZE_SMALL, text_color=cls.COLOR_AGE_PHYSICAL)
        
        # 思维年龄修正
        revision = int(data['revision_age_mental'] * 100)
        text = f"修正 [{revision}%]"
        cls._draw_icon_text(img, draw, icons_dir, 'Age.png', (76, 1206), (126, 1206), text, font_size=cls.FONT_SIZE_SMALL, text_color=cls.COLOR_AGE_MENTAL)
        
        # 体型修正
        revision = int(data['revision_size'] * 100)
        text = f"修正 [{revision}%]"
        cls._draw_icon_text(img, draw, icons_dir, 'Size.png', (76, 1272), (126, 1272), text, font_size=cls.FONT_SIZE_SMALL, text_color=cls.COLOR_WHITE)
    
    @classmethod
    def _draw_attribute_with_buff(
        cls,
        draw: ImageDraw.Draw,
        short_label: str,
        value: float,
        buff_amount: float,
        coord: Tuple[int, int],
        font_size: int,
    ):
        """绘制属性值和buff差异"""
        font = cls.get_bold_font(font_size)
        
        if buff_amount != 0:
            # 有buff，显示差异（带颜色）
            buff_str = f'(+{int(buff_amount)})' if buff_amount > 0 else f'({int(buff_amount)})'
            buff_color = cls.COLOR_GREEN if buff_amount > 0 else cls.COLOR_RED
            
            # 属性值部分
            text = f"{short_label} {int(value):<5}"
            draw.text(coord, text, cls.COLOR_BLACK, font=font)
            
            # buff部分 - 使用较小字体，紧贴属性值
            buff_font = cls.get_font(cls.FONT_SIZE_BUFF)
            # 计算属性值文本的宽度
            char_width = int(font_size * 0.5)
            buff_x = coord[0] + len(text) * char_width - 5  # 稍微重叠一点
            draw.text((buff_x, coord[1] + (font_size - cls.FONT_SIZE_BUFF) // 2 + 2), buff_str, buff_color, font=buff_font)
        else:
            # 无buff，只显示属性值
            text = f"{short_label} {int(value):<5}"
            draw.text(coord, text, cls.COLOR_BLACK, font=font)


# 全局实例
character_picture_generator = CharacterPictureGenerator()
