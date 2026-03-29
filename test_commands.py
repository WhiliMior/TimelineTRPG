"""
TimelineTRPG 指令测试文件
用于测试所有指令的基本功能是否正常工作

运行方式：
    cd <plugin_dir>
    python test_commands.py
"""
import asyncio
import sys
import os
import tempfile
import shutil
from pathlib import Path

# 获取插件目录
_plugin_dir = Path(__file__).parent
_plugin_root = str(_plugin_dir)
_data_dir = str(_plugin_dir.parent)  # data 目录

# 模拟 AstrBot 环境
class MockStarTools:
    """模拟 StarTools"""
    _data_dirs = {}

    @classmethod
    def get_data_dir(cls, plugin_name: str) -> Path:
        """获取插件数据目录"""
        if plugin_name not in cls._data_dirs:
            # 使用临时目录进行测试
            temp_dir = Path(tempfile.mkdtemp(prefix=f"test_{plugin_name}_"))
            cls._data_dirs[plugin_name] = temp_dir
        return cls._data_dirs[plugin_name]

    @classmethod
    def clear_data_dirs(cls):
        """清除所有模拟数据目录"""
        for temp_dir in cls._data_dirs.values():
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        cls._data_dirs.clear()


# 注入模拟的 StarTools
sys.modules['astrbot'] = type(sys)('astrbot')
sys.modules['astrbot.core'] = type(sys)('astrbot.core')
sys.modules['astrbot.core.star'] = type(sys)('astrbot.core.star')
sys.modules['astrbot.core.star.star_tools'] = type(sys)('astrbot.core.star.star_tools')
sys.modules['astrbot.core.star.star_tools'].StarTools = MockStarTools

# 关键：添加 data 目录到 sys.path（不是 TimelineTRPG 目录）
# 这样 TimelineTRPG 就会被识别为 data 的子包，..adapter 就能正常工作
if _data_dir not in sys.path:
    sys.path.insert(0, _data_dir)

print("加载模块...")
print(f"Plugin dir: {_plugin_root}")
print(f"Data dir: {_data_dir}")

# 现在直接导入，Python 会识别 TimelineTRPG 为 data 的子包
# 导入 adapter 层
from TimelineTRPG.trpg.adapter.command_context import CommandContext
from TimelineTRPG.trpg.adapter.message import ReplyManager
from TimelineTRPG.trpg.infrastructure.help import HelpEntry, HelpRegistry
from TimelineTRPG.trpg.infrastructure.storage import StorageBackend, StorageType
from TimelineTRPG.trpg.infrastructure.config.game_config import GameConfig

# 导入业务模块
from TimelineTRPG.trpg.service.dice.dice import roll_dice_module
from TimelineTRPG.trpg.service.examination.examination import examination_module
from TimelineTRPG.trpg.service.examination.target import target_module
from TimelineTRPG.trpg.service.character.character import character_module
from TimelineTRPG.trpg.service.buff.buff import buff_module
from TimelineTRPG.trpg.service.resource.modifier import resource_modifier_module
from TimelineTRPG.trpg.service.negotiation.negotiation import negotiation_module
from TimelineTRPG.trpg.service.battle.timeline import timeline_module
from TimelineTRPG.trpg.service.battle.battle import battle_module
from TimelineTRPG.trpg.service.inventory.inventory import inventory_module
from TimelineTRPG.trpg.service.resource.resource import resource_record_module
from TimelineTRPG.trpg.service.weapon.weapon import weapon_module
from TimelineTRPG.trpg.service.level.level import level_module

print("模块加载完成")


class MockEvent:
    """模拟事件对象"""
    def __init__(self, user_id="test_user", user_name="测试用户", group_id="test_group"):
        self.user_id = user_id
        self.user_name = user_name
        self.group_id = group_id
        self._session_id = user_id

    def get_sender_id(self):
        return self.user_id

    def get_sender_name(self):
        return self.user_name

    def get_session_id(self):
        return self._session_id

    def get_group_id(self):
        return self.group_id


def create_context(command: str, args: list, sender_id="test_user", sender_name="测试用户", group_id="test_group"):
    """创建指令上下文"""
    return CommandContext(
        command=command,
        args=args,
        sender_id=sender_id,
        sender_name=sender_name,
        session_id=sender_id,
        group_id=group_id,
        metadata={}
    )


async def test_module(module, module_name: str, test_cases: list):
    """测试单个模块的所有用例"""
    print(f"\n{'='*60}")
    print(f"测试模块: {module_name}")
    print(f"{'='*60}")

    results = []
    for test_name, command, args in test_cases:
        ctx = create_context(command, args)
        handler = getattr(module, command, None)

        if handler is None:
            print(f"  [FAIL] {test_name}: 处理器不存在")
            results.append((test_name, False, "处理器不存在"))
            continue

        try:
            result = await handler(ctx)
            has_reply = ctx.has_reply()
            reply_texts = ctx.get_reply_texts()

            print(f"\n--- {test_name} ---")
            print(f"  命令: .{command} {' '.join(args) if args else ''}")
            print(f"  结果: {result}")
            print(f"  有回复: {has_reply}")
            if has_reply:
                # 限制显示长度
                reply_preview = str(reply_texts)[:200]
                print(f"  回复内容: {reply_preview}...")

            # 测试通过条件：有回复或者没有异常
            success = has_reply or result is True
            results.append((test_name, success, None if success else "无回复"))
        except Exception as e:
            print(f"  [FAIL] {test_name}: 异常 - {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False, str(e)))

    return results


async def run_all_tests():
    """运行所有测试"""
    print("开始 TimelineTRPG 指令测试")
    print(f"插件目录: {_plugin_root}")

    all_results = []

    # 1. Roll Dice 模块测试
    roll_tests = [
        ("默认掷骰", "r", []),
        ("表达式掷骰", "r", ["3d6+2"]),
        ("单值掷骰", "r", ["20"]),
        ("d面掷骰", "r", ["d20"]),
    ]
    all_results.extend(await test_module(roll_dice_module, "roll_dice", roll_tests))

    # 3. Examination 模块测试
    ex_tests = [
        ("无参数", "ex", []),
        ("单属性", "ex", ["力量"]),
        ("属性+目标值", "ex", ["力量", "50"]),
        ("属性+乘积", "ex", ["智力", "10", "5"]),
    ]
    all_results.extend(await test_module(examination_module, "examination", ex_tests))

    # 4. Target 模块测试
    tar_tests = [
        ("查看目标", "tar", []),
        ("设定目标", "tar", ["50"]),
        ("随机难度", "tar", ["5", "d"]),
        ("等级+难度", "tar", ["5", "hard"]),
    ]
    all_results.extend(await test_module(target_module, "target", tar_tests))

    # 5. Character 模块测试
    chr_tests = [
        ("查看角色列表", "chr", []),
        ("帮助", "chr", ["help"]),
    ]
    all_results.extend(await test_module(character_module, "character", chr_tests))

    # 6. Buff 模块测试
    buff_tests = [
        ("查看Buff", "buff", []),
        ("添加Buff", "buff", ["力量", "加值", "5", "3"]),
        ("帮助", "buff", ["help"]),
    ]
    all_results.extend(await test_module(buff_module, "buff", buff_tests))

    # 7. Resource Modifier 模块测试
    dr_tests = [
        ("查看修饰", "dr", []),
        ("添加修饰", "dr", ["hp", "强化", "10", "self"]),
    ]
    all_results.extend(await test_module(resource_modifier_module, "resource_modifier", dr_tests))

    # 8. Negotiation 模块测试
    neg_tests = [
        ("RP检定", "neg", ["50"]),
        ("设定对象", "neg", ["5", "60"]),
        ("完整参数", "neg", ["50", "5", "60"]),
    ]
    all_results.extend(await test_module(negotiation_module, "negotiation", neg_tests))

    # 9. Timeline 模块测试
    tl_tests = [
        ("查看时间线", "tl", []),
        ("创建时间线", "tl", ["new", "测试战斗"]),
        ("帮助", "tl", ["help"]),
    ]
    all_results.extend(await test_module(timeline_module, "timeline", tl_tests))

    # 10. Battle 模块测试
    bt_tests = [
        ("查看状态(无战斗)", "bt", []),
        ("创建战斗", "bt", ["new", "测试战斗"]),
        ("查看状态(有战斗)", "bt", ["status"]),
        ("帮助", "bt", ["help"]),
    ]
    all_results.extend(await test_module(battle_module, "battle", bt_tests))

    # 11. Inventory 模块测试
    i_tests = [
        ("查看背包", "i", []),
        ("添加物品", "i", ["剑", "+1", "5"]),
        ("现金变动", "i", ["cash", "+100", "测试"]),
        ("帮助", "i", ["help"]),
    ]
    all_results.extend(await test_module(inventory_module, "inventory", i_tests))

    # 12. Resource Record 模块测试
    rc_tests = [
        ("查看资源", "rc", []),
        ("HP变化", "rc", ["hp", "10"]),
        ("重置资源", "rc", ["reset"]),
    ]
    all_results.extend(await test_module(resource_record_module, "resource_record", rc_tests))

    # 13. Weapon 模块测试
    wp_tests = [
        ("查看武器列表", "wp", []),
        ("帮助", "wp", ["help"]),
    ]
    all_results.extend(await test_module(weapon_module, "weapon", wp_tests))

    # 14. Level 模块测试
    lv_tests = [
        ("查看等级", "lv", []),
        ("等级+1", "lv", ["+1"]),
        ("等级-1", "lv", ["-1"]),
        ("设定等级", "lv", ["5"]),
    ]
    all_results.extend(await test_module(level_module, "level", lv_tests))

    # 打印测试结果汇总
    print(f"\n{'='*60}")
    print("测试结果汇总")
    print(f"{'='*60}")

    passed = sum(1 for _, success, _ in all_results if success)
    failed = len(all_results) - passed

    for test_name, success, error in all_results:
        status = "[PASS]" if success else "[FAIL]"
        error_info = f" ({error})" if error else ""
        print(f"  {status} {test_name}{error_info}")

    print(f"\n通过: {passed}/{len(all_results)}")
    print(f"失败: {failed}/{len(all_results)}")

    # 清理临时目录
    MockStarTools.clear_data_dirs()

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
