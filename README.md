# Timeline TRPG Bot
### 一个以 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 框架为基础的 `时间线 Timeline TRPG规则` 跑团机器人

> [AstrBot](https://github.com/AstrBotDevs/AstrBot) is an agentic assistant for both personal and group conversations. It can be deployed across dozens of mainstream instant messaging platforms, including QQ, Telegram, Feishu, DingTalk, Slack, LINE, Discord, Matrix, etc. In addition, it provides a reliable and extensible conversational AI infrastructure for individuals, developers, and teams. Whether you need a personal AI companion, an intelligent customer support agent, an automation assistant, or an enterprise knowledge base, AstrBot enables you to quickly build AI applications directly within your existing messaging workflows.

# 功能列表
---
### 游戏功能
-- 角色
- 角色创建
- 多个角色管理
- 等级变更

-- BUFF、减伤、状态记录
- 角色Buff管理，具有持续时间的Buff创建
- 角色减伤、增伤、减疗、增疗管理，具有持续时间的类减伤创建
- 护盾管理，具有持续时间的护盾创建
- 角色状态记录，HP/MP记录

-- 背包
- 背包管理
- 自定义物件录入，自定义现金记录
- 自动负重处理

-- 武器
- 武器管理
- 自动负重处理

-- 检定
- 目标数值设置
- 检定
- [ ] 合作检定
>合作检定仍在开发中
- 交涉检定

-- 战斗
- 战斗行动指令
- 使用武器战斗

# 插件层 (data/plugins/)
### 文件结构
```
TimelineTRPG/
├── main.py            # 插件入口点
├── metadata.yaml      # 插件元信息
└── trpg/
    ├── service/       # 业务服务层
    │   ├── battle/    # 战斗系统
    │   ├── resource/  # 资源管理（HP、护盾等）
    │   ├── buff/      # Buff系统
    │   ├── weapon/    # 武器系统
    │   ├── character/ # 角色管理
    │   ├── dice/      # 骰子系统
    │   └── ...
    ├── infrastructure/ # 基础设施（配置、JSON处理）
    └── adapter/       # 外部适配器
```

### 项目架构
```
AstrBot 消息
    │
    ▼
┌──────────────────────────────┐
│       插件 adapter 层        │ ← 消息入口、指令解析
│  command_context / router   │
│  reply / help                │
└──────────────┬───────────────┘
               │ Router 路由分发
               ▼
┌──────────────────────────────┐
│       插件 service 层        │ ← TRPG 业务逻辑（骰子、检定、战斗……）
│  roll_dice / examination     │
│  character / battle / ...    │
└──────────────┬───────────────┘
               │ 调用
               ▼
┌──────────────────────────────┐
│    插件 infrastructure 层    │ ← 通用方法与数据持久化
│  character_repo / save_data  │
└──────────────┬───────────────┘
               │ 读写
               ▼
┌──────────────────────────────┐
│    data/plugin_data/         │ ← 角色数据、背包、武器、状态……
└──────────────────────────────┘
```

# Supports

- [AstrBot Repo](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot Plugin Development Docs (Chinese)](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot Plugin Development Docs (English)](https://docs.astrbot.app/en/dev/star/plugin-new.html)
