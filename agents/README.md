# agents · LangChain 视角 Agent 开发 30 项渐进实验

> 通过 30 个小项目（每个 100-500 行 Python）系统掌握 AI Agent 开发：
> 从裸 HTTP 调用 LLM，到手写 ReAct 循环、Function Calling、MCP、HITL 审批，
> 再到记忆系统、RAG、多 Agent 协同与可观测性。
> 每个实验四件套：**README 教程 + 主脚本 + 真实可跑 + 架构图三件套**。
> 完整学习清单与 AI 提示词见 [../docs/agent.md](../docs/agent.md)。
> 面试导向的 31 个项目见 [../interview/](../interview/README.md)。

## 环境要求

**一键预载（推荐）**：安装 [Ollama](https://ollama.com/download) 后，先跑公共脚本——
幂等，自动启动服务并预拉本系列依赖的两个本地模型（无 API Key）：

```bash
bash scripts/load_resources.sh
```

手动方式（等价）：

```bash
# 1) 本地模型运行时（本系列统一用本地 Ollama，无需 API Key）
#    安装: https://ollama.com/download
ollama pull qwen3.8:latest          # 系列默认模型（约 17GB）
ollama pull nomic-embed-text:latest # 向量嵌入（项目 17-19）
ollama serve                        # 默认监听 http://localhost:11434

# 2) Python 3.11+
conda create -n agent_dev python=3.11 && conda activate agent_dev

# 3) 依赖（多数项目仅需 requests）
pip install requests                                   # 项目 01-08, 10-15
pip install langchain langchain-ollama                 # 项目 09
pip install chromadb faiss-cpu tiktoken                # 项目 16-19（记忆/压缩）
pip install fastapi uvicorn sse-starlette              # 项目 28（服务化）
pip install opentelemetry-api opentelemetry-sdk        # 项目 30（可观测性）
```

网络受限时：`npx` 首次拉取 MCP Server（项目 14）可能较慢属预期行为，
脚本已内置超时等待。

## 实验列表

编号即学习顺序。每个实验的教程在其目录下的 [README.md]。

### 第一阶段 · LLM 基础与 Prompt 工程

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 01 | [call_llm](01_call_llm/README.md) | 裸 HTTP 调用 LLM API，一切的最小骨架 |
| ✅ 02 | [call_llm_stream](02_call_llm_stream/README.md) | SSE 流式输出，打字机效果完整拆解 |
| ✅ 03 | [call_llm_cot](03_call_llm_cot/README.md) | CoT + Few-shot 引导结构化 JSON 输出 |
| ✅ 04 | [call_llm_temperature](04_call_llm_temperature/README.md) | temperature 对照实验，量化随机性 |
| ✅ 05 | [chat_session](05_chat_session/README.md) | 多轮对话：记忆 = 全量重发 messages |

### 第二阶段 · Agent Loop 与框架基础

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 06 | [react_basic](06_react_basic/README.md) | 手写 ReAct：Thought→Action→Observation |
| ✅ 07 | [agent_loop](07_agent_loop/README.md) | 生产级循环：事件流 + scratchpad + 三类终止 |
| ✅ 08 | [plan_execute](08_plan_execute/README.md) | Plan-and-Execute：JSON 计划 + 步骤引用 |
| ✅ 09 | [langchain_agent](09_langchain_agent/README.md) | LangChain 托管循环 + 工具沙箱 |
| ✅ 10 | [session_persist](10_session_persist/README.md) | 会话持久化：保存→恢复→断点续跑 |

### 第三阶段 · 工具系统

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 11 | [function_calling](11_function_calling/README.md) | 协议级工具调用，告别正则解析 |
| ✅ 12 | [tool_registry](12_tool_registry/README.md) | Registry 模式：加工具只加一个函数 |
| ✅ 13 | [error_handling](13_error_handling/README.md) | 错误分类、重试预算、大结果卸载 |
| ✅ 14 | [mcp_integration](14_mcp_integration/README.md) | MCP 协议：三步握手 + 动态发现工具 |
| ✅ 15 | [hitl_approval](15_hitl_approval/README.md) | HITL：三档策略 + 人工确认 + 审计日志 |

### 第四阶段 · 记忆与上下文工程

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 16 | [context_injection](16_context_injection/README.md) | Identity+Memory+Tools 组装 System Prompt |
| ✅ 17 | [memory](17_memory/README.md) | 滑动窗口 + 向量库检索注入 |
| ✅ 18 | [context_compression](18_context_compression/README.md) | 截断 vs 摘要 vs 不压缩对照实验 |
| ✅ 19 | [memory_update](19_memory_update/README.md) | 重要性判定 + 查重 + LLM 融合 |

### 第五阶段 · RAG 检索增强生成

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 20 | [doc_splitting](20_doc_splitting/README.md) | 加载器 + 递归字符切分 |
| ✅ 21 | [vector_store](21_vector_store/README.md) | Chroma 向量索引 + 语义检索 |
| ✅ 22 | [agentic_rag](22_agentic_rag/README.md) | 检索工具 + 自主决策 + 拒答 |
| ✅ 23 | [rag_rerank](23_rag_rerank/README.md) | baseline/MMR/LLM 重排对照评估 |

### 第六阶段 · 多 Agent 协同

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 24 | [langgraph_state](24_langgraph_state/README.md) | StateGraph 条件边 + 修订循环 |
| ✅ 25 | [manager_worker](25_manager_worker/README.md) | Manager 分解 + Worker 真并行 + 合并 |
| ✅ 26 | [workflow_orchestration](26_workflow_orchestration/README.md) | 扇出评审 + 反思修订循环 |
| ✅ 27 | [agent_debate](27_agent_debate/README.md) | 三专家两轮辩论 + 投票共识 |

### 第七阶段 · 工程化、安全与可观测性

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 28 | [agent_server](28_agent_server/README.md) | FastAPI + SSE + 会话管理 |
| ✅ 29 | [security_guard](29_security_guard/README.md) | 注入检测 + 白名单 + 输出过滤 |
| ✅ 30 | [observability_eval](30_observability_eval/README.md) | Trace + 评估集 + 优化对比 |

### 第八阶段 · 2025-26 前沿补充

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 31 | [code_execution](31_code_execution/README.md) | Code Mode：写代码调工具替代逐个 JSON schema |
| ✅ 32 | [agent_card](32_agent_card/README.md) | A2A/Agent Card：能力卡片 + 零改动发现 |
| ✅ 33 | [skills_disclosure](33_skills_disclosure/README.md) | Agent Skills 渐进式披露（按需加载技能） |
| ✅ 34 | [rag_quality](34_rag_quality/README.md) | RAG 质量量化：Faithfulness/Relevance + chunking 对照 |

## 学习路线

```
会调 API ──► 会聊天 ──► 会用 Prompt 控格式 ──► 会调参数        （01-05）
   │
   └─► 会做事：手写 ReAct ──► 生产级循环 ──► 框架托管 ──► 状态持久化   （06-10）
          │
          └─► 工具系统：协议级调用 ──► 注册表 ──► 容错 ──► MCP ──► 安全审批  （11-15）
                 │
                 └─► 记忆/上下文（16-19）──► RAG（20-23）──► 多 Agent（24-27）
                        │
                        └─► 工程化收尾：服务化 + 安全 + 可观测/评估（28-30）
```

排序原则：最小可运行单元最先；每个实验只引入一个新概念；后面的实验复用
前面的组件（例如 07 的 `AgentResult` 会被 30 的评估框架直接消费）。

## 每个实验怎么用

每个实验目录结构一致（四件套）：

```
agents/NN_xxx/
├── README.md          # 教程：为什么 / 一图看懂 / 快速开始 / 核心概念 / 深入要点
├── xxx.py             # 主脚本 = 学习重点，逐行读脚本就是在学这个主题
└── images/            # 架构图三件套
    ├── xxx.<type>.json  # 图源（Typed JSON，可 diff、可复现）
    ├── xxx.html         # 交互版（自包含单文件：缩放/聚焦/路径追踪）
    └── xxx.svg          # 双主题矢量图（跟随系统深浅色，README 内嵌）
```

脚本普遍支持 `--demo` 离线模式（无需 Ollama）与真实模式；交互类脚本支持
管道输入。**诚实预期**：凡依赖外部环境的行为（npx 首次下载、本地推理速度、
模型 thinking 字段怪癖）都在各 README 中如实标注。

## 已在真实环境验证过的事

- 30 个实验全部在本机（Ollama + qwen3.8:latest）跑通（26-30 为收官批次），
  交互脚本以管道输入方式回归验证；
- 修复过的真实 bug：项目 05 的 EOF 死循环、项目 09 的推理模型空答案
  （`reasoning=False`）、项目 14 的 MCP 废弃包名与裸 sleep、项目 15 的
  交互模式缺入口；
- 14 张架构图全部通过 showcase 级九项质量校验与多视口（1440/1600/1920/
  2048）浏览器零溢出检查；SVG 画布按内容实测边界紧裁（四周 24px 均匀留白，
  Chrome getBBox 实测 + 像素级背景覆盖验证），HTML 交互版 viewBox 同步收紧
  并保持最小宽高比 1.6 以免页面溢出。
