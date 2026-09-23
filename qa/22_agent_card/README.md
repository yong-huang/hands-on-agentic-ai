# 22 · Agent Card 与 A2A 风格互操作

> 每个 Agent 发布 Agent Card（JSON: 描述/技能/输入输出 schema/端点）；
> 客户端闭环 = 发现(拉卡片) → 匹配(真机 LLM 选 Agent) → 调用(统一
> invoke)。零改动验证：运行时注册一张 promo 促销卡片，路由端不改一行
> 代码即可发现并调用新 Agent。

## What

Agent Card 是 Agent 的名片：描述/技能清单/输入输出 schema/端点。对方
据此决定"要不要找你、怎么调你"，无需读对方源码。与 MCP 的分工：

- **MCP 是垂直协议**：Agent ↔ 工具/资源；
- **A2A 是水平协议**：Agent ↔ Agent 协作——互补而非竞争。

心智模型一句话：**生态从静态组合变成动态发现——新 Agent 只发布卡片
即可被网络找到。**

## Why

[21 的多 Agent 系统](../21_multi_agent_cs/README.md)新增专家要改路由
代码；Agent 之间要大规模协作时，静态注册不可扩展——互操作协议让接入
变成"发一张卡片"。

## How

```bash
cd qa/22_agent_card
MOCK=1 python3 agent_card.py    # 离线: 关键词技能匹配
python3 agent_card.py           # 真实: qwen3.8 技能匹配
```

真机实测：

```
帮我查下订单 A1002 -> order-agent    :: 订单 A1002 状态: 运输中
我要退款           -> aftersale-agent :: 已创建退款单, 3 个工作日到账
我要投诉           -> human-agent    :: 已升级人工专席
── 运行时注册 promo-agent 卡片, 路由端零改动 ──
有什么优惠活动?     -> promo-agent    :: 本周大促: 满 199 减 30...
```

发现→匹配→调用闭环全程走通；新 Agent 零改动接入 ✓。

## Deep Dive

**卡片即契约**：匹配阶段模型只看卡片字段做选择——描述与技能清单的
质量直接决定路由准确率（与
[16 工具描述](../16_tool_description/README.md)同一条规律：路由靠
"时机判断"，卡片要写清"何时找我"）。运行时注册即生效，证明发现与
调用完全解耦于具体 Agent 列表。

## Q&A

**Q1: A2A 和 MCP 什么关系？**

互补：MCP 解决 Agent 接工具（垂直，Agent↔工具/资源），A2A 解决 Agent
之间协作（水平，Agent↔Agent）。一个完整的系统通常两者都要——工具接
入用 MCP，Agent 网络用 A2A 风格的卡片发现。
