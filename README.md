# hands-on-agentic-ai · 29 个小项目亲手构建 AI Agent

> 通过 29 个小项目（每个 100-500 行 Python）系统掌握 AI Agent 开发：
> 从裸 HTTP 调用 LLM，到手写 ReAct 循环、Function Calling、MCP、HITL 审批，
> 再到记忆系统、RAG、多 Agent 协同与可观测性。
> 每个实验四件套：**README 教程 + 主脚本 + 真实可跑 + 架构图三件套**。
> 完整学习清单与 AI 提示词见 [agent.md](agent.md)。

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

编号即学习顺序（已完成 ✅ / 待实现）。**编号 8 已移除**：原"Agent 推理可视化"
仅覆盖终端渲染与 matplotlib 绘图，Agent 知识点与项目 07 重复，可观测性由
项目 30 系统承担。

### 第一阶段 · LLM 基础与 Prompt 工程

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 01 | [call_llm](agents/01_call_llm/) | 裸 HTTP 调用 LLM API，一切的最小骨架 |
| ✅ 02 | [call_llm_stream](agents/02_call_llm_stream/) | SSE 流式输出，打字机效果完整拆解 |
| ✅ 03 | [call_llm_cot](agents/03_call_llm_cot/) | CoT + Few-shot 引导结构化 JSON 输出 |
| ✅ 04 | [call_llm_temperature](agents/04_call_llm_temperature/) | temperature 对照实验，量化随机性 |
| ✅ 05 | [chat_session](agents/05_chat_session/) | 多轮对话：记忆 = 全量重发 messages |

### 第二阶段 · Agent Loop 与框架基础

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 06 | [react_basic](agents/06_react_basic/) | 手写 ReAct：Thought→Action→Observation |
| ✅ 07 | [agent_loop](agents/07_agent_loop/) | 生产级循环：事件流 + scratchpad + 三类终止 |
| ✅ 09 | [langchain_agent](agents/09_langchain_agent/) | LangChain 托管循环 + 工具沙箱 |
| ✅ 10 | [session_persist](agents/10_session_persist/) | 会话持久化：保存→恢复→断点续跑 |

### 第三阶段 · 工具系统

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 11 | [function_calling](agents/11_function_calling/) | 协议级工具调用，告别正则解析 |
| ✅ 12 | [tool_registry](agents/12_tool_registry/) | Registry 模式：加工具只加一个函数 |
| ✅ 13 | [error_handling](agents/13_error_handling/) | 错误分类、重试预算、大结果卸载 |
| ✅ 14 | [mcp_integration](agents/14_mcp_integration/) | MCP 协议：三步握手 + 动态发现工具 |
| ✅ 15 | [hitl_approval](agents/15_hitl_approval/) | HITL：三档策略 + 人工确认 + 审计日志 |

### 第四阶段 · 记忆与上下文工程 ✅

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 16 | [context_injection](agents/16_context_injection/) | Identity+Memory+Tools 组装 System Prompt |
| ✅ 17 | [memory](agents/17_memory/) | 滑动窗口 + 向量库检索注入 |
| ✅ 18 | [context_compression](agents/18_context_compression/) | 截断 vs 摘要 vs 不压缩对照实验 |
| ✅ 19 | [memory_update](agents/19_memory_update/) | 重要性判定 + 查重 + LLM 融合 |

### 第五阶段 · RAG 检索增强生成（20 ✅ · 21-23 待实现）

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| 20 | 文档加载与切分 | 加载器 + 语义分块 |
| 21 | 向量化存储 | Embedding + Chroma 相似度检索 |
| 22 | Agentic RAG | 检索工具 + 知识库问答 + 拒答 |
| 23 | RAG 重排序 | Rerank 模型提升检索精度 |

### 第六阶段 · 多 Agent 协同（待实现）

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| 24 | LangGraph 状态管理 | StateGraph 有状态工作流 |
| 25 | 多 Agent 协作 | Manager-Worker 任务分解与委派 |
| 26 | 工作流编排 | Fan-out/Fan-in + 反思评审迭代 |
| 27 | 多智能体辩论 | 专家角色讨论 + 投票共识 |

### 第七阶段 · 工程化、安全与可观测性（待实现）

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| 28 | Agent HTTP 服务化 | FastAPI + SSE 流式对话服务 |
| 29 | Agent 安全防护 | 注入检测 + 内容过滤 + 沙箱 |
| 30 | 可观测性与评估 | OpenTelemetry Trace + 评估集 + 优化闭环 |

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
├── README.md          # 教程：为什么 / 一图看懂 / 快速开始 / 核心概念 / 面试要点
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

- 19 个已完成实验在本机（Ollama + qwen3.8:latest）全部跑通，交互脚本以
  管道输入方式回归验证；
- 修复过的真实 bug：项目 05 的 EOF 死循环、项目 09 的推理模型空答案
  （`reasoning=False`）、项目 14 的 MCP 废弃包名与裸 sleep、项目 15 的
  交互模式缺入口；
- 14 张架构图全部通过 Archify showcase 九项校验与多视口（1440/1600/1920/
  2048）浏览器零溢出检查；SVG 画布按内容实测边界紧裁（四周 24px 均匀留白，
  Chrome getBBox 实测 + 像素级背景覆盖验证），HTML 交互版 viewBox 同步收紧
  并保持最小宽高比 1.6 以免页面溢出。
