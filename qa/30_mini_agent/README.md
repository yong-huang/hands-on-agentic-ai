# 30 · 🏁 终极串联——mini-agent 框架

> 把前面项目的能力接成一个可跑的最小框架：Planner（目标→DAG）→
> Guard（注入扫描）→ HITL（写操作审批）→ Executor（工具注册表）→
> Memory（事实沉淀）→ Tracer（事件流+trace 树）→ Eval（完成度报告）。
> `make demo` 一条命令跑通全链路。

## What

框架分层：

```
目标 ──► Planner(子目标DAG) ──► Executor(工具注册表)
              │                      │
              │            Guard: 参数注入扫描 ──┐
              │            HITL:  写操作审批  ──┤── 拦截/放行
              ▼                      ▼         │
           Memory(事实沉淀)      Tracer(事件流) ◄┘
                                     │
                          Eval(规则完成度报告) + trace 回放
```

**每层可替换**：Planner 换 LLM（12）、工具换 MCP（19）、记忆换向量库
（8）——分层就是为了这些替换点。

心智模型一句话：**框架 = 前面每个实验的最小核，接缝就是扩展点。**

## Why

单个实验各自成立，接起来才知道缝在哪：规划器的输出要过注入扫描、写
操作要过审批、执行全程要留事件。把七组件接成一条链，也是对全系列的
综合验收。

## How

```bash
cd qa/30_mini_agent
make demo    # 或 python3 mini_agent.py
```

实测（全离线确定）：完成度 4/4 ✓
（库存查询 ✓ / 订单创建 ✓ / 记忆沉淀 ✓ / 审计落盘 ✓）；
攻击对照：place_order 参数注入"忽略之前所有指令…"被扫描拦截 ✓；
trace 树完整呈现 规划→工具→记忆 三层 span。

## Deep Dive

**与生产框架的对照定位**：

- **LangGraph**：把"节点=步骤、边=控制流"做成图运行时，状态显式传递
  并支持 checkpoint 中断恢复；本框架用隐式依赖的最小 DAG——教学最小
  核，生产按 LangGraph 的恢复机制补齐（31）。
- **OpenAI Agents SDK**：内建 handoffs（多 Agent 交接）与 guardrails
  钩子；本框架的 Guard/HITL 对应其 Guardrail 接口。

## Q&A

**Q1: 七个组件分别来自哪些实验？**

| 模块 | 来源项目 | 一句话要点 |
|:--|:--|:--|
| Planner | 12/13 | 先规划后执行，失败分三类响应 |
| Guard | 24/20 | 注入扫描在服务侧，参数是模型可控输入 |
| HITL | 14 | 不可逆操作必审批，超时默认拒绝 |
| Executor | 15/17/18 | 注册表+校验+并行+降级链 |
| Memory | 7/8/9 | 窗口+摘要+长期库，写入要过滤读取要检索 |
| Tracer | 29 | 一切皆事件，trace 树+统计+回放 |
| Eval | 27 | 规则可判定的绝不劳烦 Judge |
