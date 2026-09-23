# harness · Agent Harness 运行时视角 18 项渐进实验

> 第三条学习线：把 harness **亲手造出来**。Agentic AI 回答"agent 做什么"，
> 本线回答"harness 怎么让它被允许、被管控、跑得久"——核心公式
> **Agent = Model + Harness**。
> 全部项目共同生长为 `mh/` mini-harness 包，最终总装成类 Claude Code 的终端 CLI。
> 每个实验四件套：**README 教程 + 主脚本 + 真实可跑 + 架构图三件套**。
> 完整学习清单（含 Harness AI vs Agentic AI 区别速览与来源）见
> [../docs/harness.md](../docs/harness.md)。
> 另两条线：[agents/](../agents/README.md)（framework 视角）·
> [qa/](../qa/README.md)（问题实证视角）。

## 环境要求

与前两条线完全共用，零新增依赖（2026-09-17 实测 ✅）：

```bash
# Ollama + 本地模型（免 Key）
ollama pull qwen3.8:latest           # 系列默认模型（约 17GB）
ollama serve                         # http://localhost:11434
# Python 依赖: 复用 requirements.txt（jsonschema/requests/mcp 均已覆盖）
pip install -r requirements.txt
```

- 共用客户端 `../qa/llm.py`：`LLM_BASE_URL` / `LLM_MODEL` 环境变量切换，
  `MOCK=1` 离线模式。
- 提速跑法：`LLM_MODEL=qwen3:4b`（2.5GB，注意 qwen3 混合推理模型的
  thinking 配额坑，各实验脚本已内置 `/no_think` 处理）。

## 实验列表

编号即学习顺序，与 [../docs/harness.md](../docs/harness.md) 项目一一对应。

### 第一阶段 · 概念破题：Harness 与 Agentic AI 的分界

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 01 | [no_harness_baseline](01_no_harness_baseline/README.md) | 无 Harness 基线：裸 LLM 多步任务失败实录 + 最小对照组 |
| ✅ 02 | [harness_anatomy](02_harness_anatomy/README.md) | 拆解工业 Harness：Claude Code 分层地图 + 四层对照 |
| ✅ 03 | [scaffold_ab_test](03_scaffold_ab_test/README.md) | 固定模型变 Harness：受控对照——真机零差异的反常发现 |

### 第二阶段 · 最小可运行 Harness

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 04 | [min_loop](04_min_loop/README.md) | ⛓️ 最小 Agent Loop：while + 一个 bash 工具（mh v0.1） |
| ✅ 05 | [tool_contract](05_tool_contract/README.md) | 工具契约层：schema 注册、参数校验、错误回传自纠 |
| ✅ 06 | [sandbox](06_sandbox/README.md) | 执行安全沙箱：超时、截断、目录隔离 |

### 第三阶段 · 控制面：权限、Hook、预算

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 07 | [permissions](07_permissions/README.md) | 权限门 allow/ask/deny 三档 + HITL 人工确认 |
| ✅ 08 | [hooks](08_hooks/README.md) | Hook 系统：pre/post 工具钩子与可阻断执行 |
| ✅ 09 | [budget](09_budget/README.md) | 预算与止损：token 计量、步数上限、优雅降级 |

### 第四阶段 · 上下文工程与记忆

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 10 | [compaction](10_compaction/README.md) | 上下文压缩：阈值触发 + 摘要 + 工具结果治理 |
| ✅ 11 | [session](11_session/README.md) | 会话持久化与崩溃恢复：checkpoint/resume（≙ qa/31 进阶） |
| ✅ 12 | [memory](12_memory/README.md) | 跨会话记忆：MEMORY.md 自动沉淀与新会话注入 |

### 第五阶段 · 扩展机制

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 13 | [subagent](13_subagent/README.md) | 子代理调度：上下文隔离的任务分派与回收 |
| ✅ 14 | [skills](14_skills/README.md) | Skills 按需注入：触发匹配 + 懒加载省 token 实测 |
| ✅ 15 | [mcp_client](15_mcp_client/README.md) | MCP 动态工具：在权限门下接入外部 server（≙ qa/19-20 进阶） |

### 第六阶段 · 评测与总装

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 16 | [eval](eval/README.md) | Harness 评测台：固定任务集回归，量化每次演进 |
| ✅ 17 | [cli](17_cli/README.md) | 🏁 终极总装：mini-harness CLI（类 Claude Code 终端） |
| ✅ 18 | [model_vs_harness](18_model_vs_harness/README.md) | 收尾对照：同 Harness 异模型 2×2 实验，闭环"区别"主线 |
