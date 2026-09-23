# 32 · A2A / Agent Card：Agent 能力卡片、发现与互操作

> 项目 14 的 MCP 管"Agent 接工具"（垂直），本项目管 **Agent 之间互发现、
> 互调用**（水平）——对齐 Google A2A 规范的简化版：每个 Agent 用一张
> JSON Card 描述能力（skills/schema/端点），路由端只看卡片做发现与调度，
> **新增 Agent 零代码改动**。

## What

- **Agent Card**：`name / description / skills[{id, input_schema,
  output_schema}] / endpoint`——对方据此决定"要不要找你、怎么调你"。
- **发现与过滤**：按技能 id 或描述关键词检索卡片目录（生产中对应 A2A 的
  registry / well-known URI）。
- **MCP vs A2A**：MCP 是 Agent↔工具的垂直协议；A2A 是 Agent↔Agent 的
  水平协议。一个 Agent 对下用 MCP 接工具，对上用 A2A 暴露能力。

心智模型一句话：**卡片即接口——路由端逻辑与 Agent 数量无关。**

## Why

多 Agent 系统里，路由端如果硬编码"有哪些 Agent、怎么调"，每加一个 Agent
就要改一次路由代码——组合爆炸。Agent Card 把能力声明从代码里抽出来：
发现（按技能关键词过滤卡片）→ 匹配 → 调用（统一 endpoint + skill_input）。

## How

```bash
cd agents/32_agent_card
python agent_card.py    # 全离线: 模拟卡片 + 确定性路由
```

实测输出（节选）：三个 Agent（translator / weather / math）注册卡片 →
按关键词发现 → 路由调用；随后运行时 `AGENT_CARDS.append(new_agent)`——
**注册后即刻被发现，路由端零改动**。

## Deep Dive

**MCP 与 A2A 的分工**：一个管 Agent 接工具，一个管 Agent 间协作，互补而
非竞争。卡片的最小集是"能力描述 + 输入输出 schema + 端点"——schema 让
调用方无需读源码即可构造合法请求。

## Q&A

**Q1: 零改动接入为什么是开放生态的前提？**

对比项目 21（硬编码路由表）体会差异：新 Agent 只发一张卡片即可被网络
发现——接入成本从"改路由代码"降到"注册数据"。
