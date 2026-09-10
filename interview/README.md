# interview · AI Agent 面试攻坚 31 项目（一题一项目，全部可跑）

> 以**真实面试真题**为纲：每道高频题对应一个能跑通的小项目，做完即"能讲+能写"。
> 三条面试主线贯穿：**ReAct 循环能手写** · **记忆系统+RAG 能讲清** · **系统设计能画架构图**。
> 语言 Python 3.10+；LLM 走本地 Ollama（qwen3.8，OpenAI 兼容接口），全部支持
> `MOCK=1` 离线模式。完整题单、AI 提示词与踩坑日志见 [../agent_interview.md](../agent_interview.md)。
> 工程化渐进学习路线（LangChain 视角）见 [../agents/](../agents/README.md)。

## 运行方式

```bash
# 环境见文末；单项目两种模式
MOCK=1 python 04_loop_guard/loop_guard.py   # 离线: 预置响应, 结果确定
python 04_loop_guard/loop_guard.py          # 真实: 本地 Ollama qwen3.8

# 全量测试 (31 个 lab 的 mock/real 批量回归)
bash run_all.sh mock
bash run_all.sh real
```

最近一次全量回归：**离线 31/31 PASS；真机 31/31 PASS**（12/28 两处真机
缺陷修复后复测通过，见各 README）。

## 实验列表

### 阶段一 · 推理框架：CoT / ReAct / ToT（面试主线①）

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 01 | [cot_compare](01_cot_compare/README.md) | CoT 原理/局限/Auto-CoT | few-shot 11/20，auto-cot 成本最高 |
| ✅ 02 | [cot_failure](02_cot_failure/README.md) | CoT 何时反而降性能 | 简单题 CoT 有害 -20%，token 65× |
| ✅ 03 | [react_manual](03_react_manual/README.md) | 手写 ReAct 循环 | 失败→自愈轨迹完整可复现 |
| ✅ 04 | [loop_guard](04_loop_guard/README.md) | 死循环检测与四层防护 | 层间语义要划界（L2/L3 让位） |
| ✅ 05 | [fc_vs_react](05_fc_vs_react/README.md) | FC 与 ReAct 的关系 | FC token +75% 但可并行调用 |
| ✅ 06 | [tot_solver](06_tot_solver/README.md) | ToT / BFS vs DFS / 剪枝 | **CoT 9/10 反超 ToT 2/10**：评估器-生成器能力错配 |

### 阶段二 · 记忆系统（高频考点，面试主线②）

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 07 | [short_memory](07_short_memory/README.md) | 窗口溢出/摘要压缩 | 窗口确定性丢早期(1/5)，摘要丢细节 |
| ✅ 08 | [long_memory](08_long_memory/README.md) | 设计记忆系统 | 跨会话 4/4，归一化事实提升检索 |
| ✅ 09 | [memory_poison](09_memory_poison/README.md) | 记忆污染 | 三层防御 5/5 vs 无防御 0/5 |
| ✅ 10 | [hybrid_retrieval](10_hybrid_retrieval/README.md) | 混合检索选择 | 短语料下 RRF 与 BM25 打平 |
| ✅ 11 | [reflection](11_reflection/README.md) | Reflection 机制 | 强模型+少记忆无增益(-1.0) |

### 阶段三 · 规划与可控性

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 12 | [plan_execute](12_plan_execute/README.md) | Planning/子目标分解 | P&E 3/3 vs ReAct 2/3，token 减半 |
| ✅ 13 | [replan](13_replan/README.md) | 规划失败处理 | 三类失败三响应，LLM 分类器 3/3 一致 |
| ✅ 14 | [hitl_gate](14_hitl_gate/README.md) | HITL 介入时机 | 危险 5/5 卡住，安全零打扰 |

### 阶段四 · 工具调用与 MCP

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 15 | [tool_registry](15_tool_registry/README.md) | FC Schema 设计 | 错误带路径才能自纠，真机 3/3 |
| ✅ 16 | [tool_description](16_tool_description/README.md) | 工具描述优化 | **反常**：长描述 80% < 简版 98% |
| ✅ 17 | [parallel_tools](17_parallel_tools/README.md) | 并行调用/依赖 DAG | 50% 耗时达成；盲并行必错 |
| ✅ 18 | [graceful_degrade](18_graceful_degrade/README.md) | 优雅降级 | 主工具全挂仍 80% 可用 |
| ✅ 19 | [mcp_server](19_mcp_server/README.md) | MCP 三原语/Server 设计 | 3T+1R+1P 全连通 |
| ✅ 20 | [mcp_guard](20_mcp_guard/README.md) | MCP 安全 | 5 类恶意全拦+审计 |

### 阶段五 · Multi-Agent

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 21 | [multi_agent_cs](21_multi_agent_cs/README.md) | 多 Agent 客服系统 | LLM 路由 10/10，转接上下文 10/10 |
| ✅ 22 | [agent_card](22_agent_card/README.md) | A2A vs MCP / Agent Card | 新 Agent 零改动接入 |
| ✅ 23 | [generator_critic](23_generator_critic/README.md) | 什么时候用多 Agent | 辩论成本 3×；代表题天花板 6/6 |

### 阶段六 · 安全攻防

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 24 | [injection_range](24_injection_range/README.md) | Prompt Injection 攻防 | qwen3.8 无防御 0/6 得手；弱模型才是靶 |
| ✅ 25 | [guardrails](25_guardrails/README.md) | 越狱/Guardrails | 双层护栏 10/10 拦，模型层仅 1 调用 |
| ✅ 26 | [goal_drift](26_goal_drift/README.md) | 目标漂移 | 阈值要按评估器校准(0.6→0.4) |

### 阶段七 · 评估

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 27 | [eval_judge](27_eval_judge/README.md) | 评测框架/LLM-as-Judge | Judge 与规则 100% 一致；偏见未复现 |
| ✅ 28 | [rag_quality](28_rag_quality/README.md) | Faithfulness/Relevance | 字面重合法双向误差，只能初筛 |

### 阶段八 · 系统设计与终极串联（面试主线③）

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 29 | [observability](29_observability/README.md) | 可观测性系统 | 一切皆事件+离线回放 |
| ✅ 30 | [mini_agent](30_mini_agent/README.md) | 设计 Agent 框架（大题） | make demo 全链路 4/4 |

### 补充 · 长任务韧性

| 项目 | 实验 | 覆盖面试题 | 关键真机结论 |
| :--- | :--- | :--- | :--- |
| ✅ 31 | [checkpoint_resume](31_checkpoint_resume/README.md) | 断点续跑/幂等 | 崩溃重启复用已完成步骤 |

## 环境要求

```bash
# 1) 本地模型 (无需 API Key): 安装 https://ollama.com/download
ollama pull qwen3.8:latest           # 默认对话模型 (约 17GB)
ollama pull nomic-embed-text:latest  # 向量嵌入 (项目 08/10/28)
ollama serve

# 2) Python 3.10+ (项目 15/19/20 需额外依赖)
pip install jsonschema   # 项目 15
pip install mcp          # 项目 19/20 (官方 SDK, 2.x 需用 MCPServer)

# 3) 真实模式统一走环境变量 (缺省指向本地 Ollama)
export LLM_BASE_URL="http://localhost:11434/v1"
export LLM_MODEL="qwen3.8:latest"
export LLM_API_KEY="ollama"
```

注意：本系列大量实验依赖**思考型模型的长输出**，max_tokens 需按模型实测
预留（qwen3.8 实测 1500 起步）；MOCK 模式离线可跑、结果确定，适合先验证
链路再看真机行为。

## 与 agents/ 系列的关系

`agents/`（LangChain 视角，30 项渐进实验）是**技能主线**：怎么一步步把
Agent 做出来。本目录是**考点深化**：每道高频面试题一个最小可跑实证，含
攻防对照与真机反常数据。两边考点重叠的项目（记忆/RAG/多 Agent/安全）
互为印证，README 互相链接。
