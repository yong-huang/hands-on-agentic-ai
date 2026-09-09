# 22 · Agent Card 与 A2A 风格互操作

> 覆盖面试题：A2A 和 MCP 的区别？Agent Card 怎么描述 Agent 能力？
> 每个 Agent 发布 Agent Card（JSON: 描述/技能/输入输出 schema/端点）；
> 客户端闭环 = 发现(拉卡片) → 匹配(真机 LLM 选 Agent) → 调用(统一 invoke)。
> 零改动验证：运行时注册一张 promo 促销卡片，路由端不改一行代码即可
> 发现并调用新 Agent。

## 1. 运行与实测

```bash
MOCK=1 python agent_card.py    # 离线: 关键词技能匹配
python agent_card.py           # 真实: qwen3.8 技能匹配
```

真机实测（2026-09-09）：

```
帮我查下订单 A1002 -> order-agent    :: 订单 A1002 状态: 运输中
我要退款           -> aftersale-agent :: 已创建退款单, 3 个工作日到账
我要投诉           -> human-agent    :: 已升级人工专席
── 运行时注册 promo-agent 卡片, 路由端零改动 ──
有什么优惠活动?     -> promo-agent    :: 本周大促: 满 199 减 30...
```

发现→匹配→调用闭环全程走通；新 Agent 零改动接入 ✓。

## 2. 面试要点

- MCP 是 Agent 接工具的协议（垂直：Agent↔工具/资源）；A2A 是 Agent
  之间协作的协议（水平：Agent↔Agent）——互补而非竞争。
- Agent Card = Agent 的名片：描述/技能清单/输入输出 schema/端点。
  对方据此决定"要不要找你、怎么调你"，无需读对方源码。
- 开放接入的价值：新 Agent 只发布卡片即可被网络发现——生态从静态
  组合变成动态发现（本实验运行时注册即生效）。

## 3. 文件结构

```
interview/22_agent_card/
├── README.md            # 本篇
└── agent_card.py        # 卡片生成 + Registry + 发现/匹配/调用闭环（约 210 行）
```
