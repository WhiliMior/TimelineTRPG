"""
定时事件调度器 - 管理战斗中的定时事件
迁移自老项目 Game/Runtime/Battle/BattleSystem.py 中的定时事件功能

功能：
- 调度带持续时间的buff事件
- 调度带持续时间的护盾事件
- 调度带持续时间的资源修饰事件
- 执行到期的定时事件回调
"""
import time
from typing import Dict, List, Optional

from ..adapter.message import ReplyManager
from .storage import StorageBackend


class SchedulerModule:
    """
    定时事件调度器模块
    
    提供统一的定时事件调度和执行功能，
    避免 service 模块之间的循环引用。
    """
    
    def __init__(self):
        self.system_reply = ReplyManager("system")
    
    def schedule_event(self, conversation_id: str, user_id: str, character_name: str,
                      action_description: str, duration_or_count: float,
                      callback_path: str, callback_args: Dict, callback_message: str,
                      mode: str = 'time_based', event_type: str = 'general') -> bool:
        """
        调度一个定时事件
        
        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            character_name: 角色名
            action_description: 行动描述
            duration_or_count: 持续时间或生效次数
            callback_path: 回调函数路径
            callback_args: 回调函数参数
            callback_message: 回调执行提示
            mode: 模式 ('time_based' 或 'count_based')
            event_type: 事件类型 ('general', 'buff', 'shield', 'modifier')
        
        Returns:
            bool: 是否成功调度
        """
        storage_key = conversation_id
        battle = self._get_battle(storage_key)
        
        if battle.get("status") != "active":
            return False
        
        # 获取当前时间点
        current_time = battle.get('current_time', 0)
        
        # 创建事件对象
        event = {
            'id': f"event_{int(time.time())}_{len(battle.get('scheduled_events', []))}",
            'event_type': event_type,
            'action_description': action_description,
            'start_time': current_time,
            'user_id': user_id,
            'character_name': character_name,
            'callback_path': callback_path,
            'callback_args': callback_args,
            'callback_message': callback_message,
            'mode': mode
        }
        
        if mode == 'time_based':
            # 持续时间模式：当前时间 + 持续时间 = 结束时间
            event['end_time'] = current_time + duration_or_count
            event['remaining_count'] = None
        elif mode == 'count_based':
            # 生效次数模式：记录剩余次数
            event['remaining_count'] = int(duration_or_count)
            event['end_time'] = None
        else:
            return False
        
        # 添加到事件列表
        if 'scheduled_events' not in battle:
            battle['scheduled_events'] = []
        battle['scheduled_events'].append(event)
        
        # 保存
        self._save_battle(storage_key, battle)
        return True
    
    def execute_scheduled_events(self, conversation_id: str, user_id: str = None) -> List[str]:
        """
        执行到期的定时事件
        
        Args:
            conversation_id: 会话ID
            user_id: 用户ID，如果指定则只执行该用户的到期事件
        
        Returns:
            List[str]: 执行结果消息列表
        """
        storage_key = conversation_id
        battle = self._get_battle(storage_key)
        
        if battle.get("status") != "active":
            return []
        
        current_time = battle.get('current_time', 0)
        scheduled_events = battle.get('scheduled_events', [])
        
        executed_messages = []
        events_to_remove = []
        
        for i, event in enumerate(scheduled_events):
            # 检查是否为时间模式且已到期
            if (event.get('mode') == 'time_based' and 
                event.get('end_time') is not None and 
                current_time >= event.get('end_time', 0)):
                
                # 如果指定了用户ID，只执行该用户的事件
                if user_id is not None and event.get('user_id') != user_id:
                    continue
                
                # 执行回调
                if 'callback_path' in event and event['callback_path']:
                    try:
                        callback_path = event['callback_path']
                        callback_args = event.get('callback_args', {})
                        
                        if callback_path == "trpg.service.buff.buff.remove_expired_buff":
                            from ...service.buff.buff import remove_expired_buff
                            remove_expired_buff(**callback_args)
                            executed_messages.append(event.get('callback_message', ''))
                        elif callback_path == "trpg.service.resource.resource.remove_expired_shield":
                            from ...service.resource.resource import remove_expired_shield
                            remove_expired_shield(**callback_args)
                            executed_messages.append(event.get('callback_message', ''))
                        elif callback_path == "trpg.service.resource.modifier.remove_expired_modifier":
                            from ...service.resource.modifier import remove_expired_modifier
                            remove_expired_modifier(**callback_args)
                            executed_messages.append(event.get('callback_message', ''))
                    except Exception as e:
                        print(f"Error executing scheduled event callback: {e}")
                
                # 标记为删除
                events_to_remove.append(i)
        
        # 从后往前删除已执行的事件
        for i in reversed(events_to_remove):
            if i < len(scheduled_events):
                del scheduled_events[i]
        
        # 保存更新后的事件列表
        if events_to_remove:
            battle['scheduled_events'] = scheduled_events
            self._save_battle(storage_key, battle)
        
        return executed_messages
    
    def _get_battle(self, storage_key: str) -> Dict:
        """获取战斗数据"""
        data = StorageBackend.load_battle(storage_key)
        if not data.get("battle_list"):
            data["battle_list"] = {}
        
        active_battle_id = data.get("active_battle_id")
        
        if active_battle_id and active_battle_id in data["battle_list"]:
            return data["battle_list"][active_battle_id]
        else:
            return {
                "status": "idle",
                "name": None,
                "creator": None,
                "participants": {},
                "ready": [],
                "timeline": {},
                "current_time": 0,
                "max_time": 0,
                "scheduled_events": []
            }
    
    def _save_battle(self, storage_key: str, battle: Dict):
        """保存战斗数据"""
        data = StorageBackend.load_battle(storage_key)
        
        if not data.get("battle_list"):
            data["battle_list"] = {}
        if "player" not in data:
            data["player"] = {}
        
        active_battle_id = data.get("active_battle_id")
        
        if active_battle_id:
            data["battle_list"][active_battle_id] = battle
        else:
            import time
            new_battle_id = f"battle_{int(time.time())}"
            data["active_battle_id"] = new_battle_id
            data["battle_list"][new_battle_id] = battle
        
        StorageBackend.save_battle(storage_key, data)


# 创建模块实例
scheduler_module = SchedulerModule()


def execute_scheduled_events(conversation_id: str, user_id: str = None) -> List[str]:
    """
    执行到期的定时事件（便捷函数）
    """
    return scheduler_module.execute_scheduled_events(conversation_id, user_id)


def schedule_event(conversation_id: str, user_id: str, character_name: str,
                  action_description: str, duration_or_count: float,
                  callback_path: str, callback_args: Dict, callback_message: str,
                  mode: str = 'time_based', event_type: str = 'general') -> bool:
    """
    调度一个定时事件（便捷函数）
    """
    return scheduler_module.schedule_event(
        conversation_id, user_id, character_name,
        action_description, duration_or_count,
        callback_path, callback_args, callback_message,
        mode, event_type
    )
