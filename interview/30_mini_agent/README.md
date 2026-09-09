# 30 · 🏁 终极串联——mini-agent 框架与架构答辩

> 覆盖面试题：设计一个支持工具调用的 Agent 框架（中高级大题）+ 全部考点综合
> 把前面项目的考点接成一个可跑的最小框架：Planner（目标→DAG）→
> Guard（注入扫描）→ HITL（写操作审批）→ Executor（工具注册表）→
> Memory（事实沉淀）→ Tracer（事件流+trace 树）→ Eval（完成度报告）。
> `make demo` 一条命令跑通全链路。

## 1. 运行与实测

```bash
make demo    # 或 python3 mini_agent.py
```

实测（2026-09-09，全离线确定）：完成度 4/4 ✓
（库存查询 ✓ / 订单创建 ✓ / 记忆沉淀 ✓ / 审计落盘 ✓）；
攻击对照：place_order 参数注入"忽略之前所有指令…"被扫描拦截 ✓；
trace 树完整呈现 规划→工具→记忆 三层 span。

## 2. 框架分层（架构答辩图）

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

- 与 LangGraph 对照：它把"节点=步骤、边=控制流"做成图运行时，状态
  显式传递并支持 checkpoint 中断恢复；本框架用隐式依赖的最小 DAG——
  教学最小核，生产按 LangGraph 的恢复机制补齐（项目 31）。
- 与 OpenAI Agents SDK 对照：内建 handoffs（多 Agent 交接）与
  guardrails 钩子；本框架的 Guard/HITL 对应其 Guardrail 接口。
- 每层可替换：Planner 换 LLM（项目 12）、工具换 MCP（项目 19）、
  记忆换向量库（项目 8）——分层就是为了这些替换点。

## 3. 模块→考点话术卡

| 模块 | 来源项目 | 面试一句话 |
|:--|:--|:--|
| Planner | 12/13 | 先规划后执行，失败分三类响应 |
| Guard | 24/20 | 注入扫描在服务侧，参数是模型可控输入 |
| HITL | 14 | 不可逆操作必审批，超时默认拒绝 |
| Executor | 15/17/18 | 注册表+校验+并行+降级链 |
| Memory | 7/8/9 | 窗口+摘要+长期库，写入要过滤读取要检索 |
| Tracer | 29 | 一切皆事件，trace 树+统计+回放 |
| Eval | 27 | 规则可判定的绝不劳烦 Judge |

## 4. 文件结构

```
interview/30_mini_agent/
├── README.md            # 本篇
├── Makefile             # make demo / make clean
├── mini_agent.py        # 七组件接线 + 全链路演示（约 270 行）
├── memory.json          # 运行产物
└── trace.jsonl          # 运行产物
```
