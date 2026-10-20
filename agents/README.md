# agents · LangChain 视角 Agent 开发 27 项渐进实验

> 通过 27 个小项目（每个 100-500 行 Python）系统掌握 AI Agent 开发：
> 从裸 HTTP 调用 LLM，到手写 ReAct 循环、Function Calling、MCP、HITL 审批，
> 再到记忆系统、多 Agent 协同与可观测性。
> 每个实验：**README 教程 + 主脚本 + 真实可跑**（01-25 另配交互架构图）。
> RAG 检索增强方向已独立为 [hands-on-rag](../hands-on-rag/README.md) 系列
> （本仓库 qa 线另有 28_rag_quality 问题实证）。
> 完整学习清单与 AI 提示词见 [../docs/agent.md](../docs/agent.md)。
> 问题实证的 31 个项目见 [../qa/](../qa/README.md)。

## 环境要求

**一键预载（推荐）**：安装 [Ollama](https://ollama.com/download) 后，先跑公共脚本——
幂等，自动安装 requirements.txt 中的 Python 依赖、启动服务并预拉本系列依赖的
两个本地模型（无 API Key）：

```bash
bash scripts/load_resources.sh
```

手动方式（等价）：

```bash
# 1) 本地模型运行时（本系列统一用本地 Ollama，无需 API Key）
#    安装: https://ollama.com/download
ollama pull qwen3.8:latest          # 系列默认模型（约 17GB）
ollama pull nomic-embed-text:latest # 向量嵌入（项目 15-17）
ollama serve                        # 默认监听 http://localhost:11434

# 2) Python 3.11+
conda create -n agent_dev python=3.11 && conda activate agent_dev

# 3) 依赖（与 load_resources.sh 第 1 步等价，覆盖 agents/ 与 qa/ 全部脚本）
pip install -r requirements.txt
```

网络受限时：`npx` 首次拉取 MCP Server（项目 12）可能较慢属预期行为，
脚本已内置超时等待。

## 实验列表

编号即学习顺序。每个实验的教程为其目录下的 `README.md`。

### 第一阶段 · LLM 基础与 Prompt 工程

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 01 | [call_llm_basics](01_call_llm_basics/README.md) | 裸 HTTP + SSE 流式 + 温度对照，调用三合一 |
| ✅ 02 | [call_llm_cot](02_call_llm_cot/README.md) | CoT + Few-shot 引导结构化 JSON 输出 |
| ✅ 03 | [chat_session](03_chat_session/README.md) | 多轮对话：记忆 = 全量重发 messages |

### 第二阶段 · Agent Loop 与框架基础

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 04 | [react_basic](04_react_basic/README.md) | 手写 ReAct：Thought→Action→Observation |
| ✅ 05 | [agent_loop](05_agent_loop/README.md) | 生产级循环：事件流 + scratchpad + 三类终止 |
| ✅ 06 | [plan_execute](06_plan_execute/README.md) | Plan-and-Execute：JSON 计划 + 步骤引用 |
| ✅ 07 | [langchain_agent](07_langchain_agent/README.md) | LangChain 托管循环 + 工具沙箱 |
| ✅ 08 | [session_persist](08_session_persist/README.md) | 会话持久化：保存→恢复→断点续跑 |

### 第三阶段 · 工具系统

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 09 | [function_calling](09_function_calling/README.md) | 协议级工具调用，告别正则解析 |
| ✅ 10 | [tool_registry](10_tool_registry/README.md) | Registry 模式：加工具只加一个函数 |
| ✅ 11 | [error_handling](11_error_handling/README.md) | 错误分类、重试预算、大结果卸载 |
| ✅ 12 | [mcp_integration](12_mcp_integration/README.md) | MCP 协议：三步握手 + 动态发现工具 |
| ✅ 13 | [hitl_approval](13_hitl_approval/README.md) | HITL：三档策略 + 人工确认 + 审计日志 |

### 第四阶段 · 记忆与上下文工程

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 14 | [context_injection](14_context_injection/README.md) | Identity+Memory+Tools 组装 System Prompt |
| ✅ 15 | [memory](15_memory/README.md) | 滑动窗口 + 向量库检索注入 |
| ✅ 16 | [context_compression](16_context_compression/README.md) | 截断 vs 摘要 vs 不压缩对照实验 |
| ✅ 17 | [memory_update](17_memory_update/README.md) | 重要性判定 + 查重 + LLM 融合 |

### 第五阶段 · 多 Agent 协同

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 18 | [langgraph_state](18_langgraph_state/README.md) | StateGraph 条件边 + 修订循环 |
| ✅ 19 | [manager_worker](19_manager_worker/README.md) | Manager 分解 + Worker 真并行 + 合并 |
| ✅ 20 | [workflow_orchestration](20_workflow_orchestration/README.md) | 扇出评审 + 反思修订循环 |
| ✅ 21 | [agent_debate](21_agent_debate/README.md) | 三专家两轮辩论 + 投票共识 |

### 第六阶段 · 工程化、安全与可观测性

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 22 | [agent_server](22_agent_server/README.md) | FastAPI + SSE + 会话管理 |
| ✅ 23 | [security_guard](23_security_guard/README.md) | 注入检测 + 白名单 + 输出过滤 |
| ✅ 24 | [observability_eval](24_observability_eval/README.md) | Trace + 评估集 + 优化对比 |

### 第七阶段 · 2025-26 前沿补充

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 25 | [code_execution](25_code_execution/README.md) | Code Mode：写代码调工具替代逐个 JSON schema |
| ✅ 26 | [agent_card](26_agent_card/README.md) | A2A/Agent Card：能力卡片 + 零改动发现 |
| ✅ 27 | [skills_disclosure](27_skills_disclosure/README.md) | Agent Skills 渐进式披露（按需加载技能） |

## 学习路线

```
会调 API（非流式/流式/温度）──► 会用 Prompt 控格式 ──► 会聊天    （01-03）
   │
   └─► 会做事：手写 ReAct ──► 生产级循环 ──► 框架托管 ──► 状态持久化   （04-08）
          │
          └─► 工具系统：协议级调用 ──► 注册表 ──► 容错 ──► MCP ──► 安全审批  （09-13）
                 │
                 └─► 记忆/上下文（14-17）──► 多 Agent（18-21）
                        │
                        └─► 工程化收尾：服务化 + 安全 + 可观测/评估（22-24）
                               │
                               └─► 前沿补充：Code Mode + A2A 卡片 + Skills 披露（25-27）
```

排序原则：最小可运行单元最先；每个实验只引入一个新概念；后面的实验复用
前面的组件（例如 05 的 `AgentResult` 会被 24 的评估框架直接消费）。
RAG 方向（检索增强生成）见同仓库群的 hands-on-rag 系列。

## 每个实验怎么用

每个实验目录结构一致（四件套）：

```
agents/NN_xxx/
├── README.md          # 教程：六段式 Background / What / When to Use / Quick Start / How It Works / Pitfalls & Q&A
├── xxx.py             # 主脚本 = 学习重点，逐行读脚本就是在学这个主题
└── images/            # 交互架构图三件套（01-25 各配，01 含 3 组）
    ├── xxx.<type>.json  # 图源（Typed JSON，可 diff、可复现）
    ├── xxx.html         # 交互版（自包含单文件：缩放/聚焦/路径追踪）
    └── xxx.svg          # 双主题矢量图（跟随系统深浅色）
```

脚本普遍支持 `--demo` 离线模式（无需 Ollama）与真实模式；交互类脚本支持
管道输入。**诚实预期**：凡依赖外部环境的行为（npx 首次下载、本地推理速度、
模型 thinking 字段怪癖）都在各 README 中如实标注。

## 已在真实环境验证过的事

- 27 个实验全部在本机（Ollama + qwen3.8:latest）跑通，
  交互脚本以管道输入方式回归验证；
- 修复过的真实 bug：项目 03 的 EOF 死循环、项目 07 的推理模型空答案
  （`reasoning=False`）、项目 12 的 MCP 废弃包名与裸 sleep、项目 13 的
  交互模式缺入口；
- 全部交互架构图（27 组，覆盖 01-25；26-27 待补）通过 showcase 级九项
  质量校验与多视口（1440/1600/1920/2048）浏览器零溢出检查；SVG 画布按
  内容实测边界紧裁（四周 24px 均匀留白，Chrome getBBox 实测 + 像素级
  背景覆盖验证），HTML 交互版 viewBox 同步收紧并保持最小宽高比 1.6
  以免页面溢出。
