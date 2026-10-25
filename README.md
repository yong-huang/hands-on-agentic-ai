# hands-on-agentic-ai · 亲手构建 AI Agent（五条学习线）

> 一个仓库，五条线，**109 个可跑项目**
> （RAG 检索增强方向已独立为同级仓库 [hands-on-rag](../hands-on-rag/)，15 项渐进实验）：
>
> | 线 | 目录 | 定位 | 项目数 |
> |:--|:--|:--|:--:|
> | 🛠️ **技能主线** | [agents/](agents/README.md) | LangChain 视角，从裸调 API 到服务化的 27 项渐进实验 | 27 |
> | 🎯 **问题实证** | [qa/](qa/README.md) | 31 个高频问题一问一项目，含攻防对照与真机反常数据 | 31 |
> | 🎛️ **Harness 攻坚** | [harness/](harness/README.md) | 自研 mh/ mini-harness，18 项运行时实验 | 18 |
> | 🧪 **AI 测试** | [aitest/](aitest/README.md) | 测试 AI 系统：评测集/断言/红队/门禁的 21 项渐进实验 | 21 |
> | 🔧 **框架内核** | [langchain/](langchain/README.md) | LangChain 1.x / LangGraph 内核机制的 12 项深度实验 | 12 |
>
> 五条线互相印证：agents 教你"怎么一步步做出来"，qa 给你"每个问题的
> 最小可跑实证"，harness 把它们组装成可管控的运行时，aitest 给运行时
> 造测试台，langchain 下钻框架内核（重叠问题各线 README 互相链接）。

## 仓库结构

```
hands-on-agentic-ai/
├── agents/              # 🛠️ 技能主线: 7 阶段 27 实验 (索引见 agents/README.md)
│   └── 01_call_llm_basics ... 27_skills_disclosure
│       每个实验四件套: README 教程 + 主脚本 + 架构图三件套
├── qa/                  # 🎯 问题实证: 8 阶段 31 项目 (索引见 qa/README.md)
│   ├── 01_cot_compare ... 31_checkpoint_resume
│   ├── run_all.sh       # 全量测试跑批器 (mock/real 双模式)
│   └── llm.py           # 各线共用的 OpenAI 兼容客户端 (本地 Ollama)
├── harness/             # 🎛️ Harness 攻坚: 18 实验 (自研 mh/ 包, 清单见 docs/harness.md)
├── aitest/              # 🧪 AI 测试: 5 阶段 21 实验 (testbench/ 测试台, 索引见 aitest/README.md)
├── langchain/           # 🔧 框架内核: 4 阶段 12 实验 (LangChain 1.x / LangGraph, 索引见 langchain/README.md)
├── docs/                # 各线的题单/清单文档
│   ├── agent.md             # agents 线学习清单 (24/24 完成, 25-27 为后续前沿补充)
│   ├── qa.md                # qa 线题单 (31/31 完成, 含全部踩坑记录)
│   ├── harness.md           # harness 线学习清单 (18/18 完成, 含 Harness vs Agentic AI 速览)
│   ├── aitest.md            # aitest 线学习清单 (21/21 完成, 含与 qa/agent/harness 三线关系表)
│   ├── langchain.md         # langchain 线学习清单 (12/12 完成, 含环境配置版本清单)
│   └── pi-agent.md          # pi coding agent 源码精读 17 项目学习清单
└── scripts/             # 公共脚本 (模型预载等)
```

## 环境要求（三线共用）

安装 [Ollama](https://ollama.com/download) 后预拉两个本地模型（无需 API Key）：

```bash
ollama pull qwen3.8:latest           # 默认对话模型（约 17GB）
ollama pull nomic-embed-text:latest  # 向量嵌入（agents 15/17 / hands-on-rag 系列 / qa 08/10/28）
ollama serve                         # http://localhost:11434
```

- **agents 线**：Python 3.11+，按项目需要装 `requests / langchain / chromadb /
  fastapi / opentelemetry`（明细见 [agents/README.md](agents/README.md)）。
- **qa 线**：Python 3.10+，仅需 `jsonschema`（项目 15）与 `mcp`
  （项目 19/20）；绝大多数项目纯标准库。
- **harness 线**：零新增依赖，复用 qa 线客户端（见
  [harness/README.md](harness/README.md)）。
- **aitest 线**：零新增安装（pytest/pyyaml/numpy 均已在环境中），被测对象
  复用 harness 的 mh 包（见 [aitest/README.md](aitest/README.md)）。
- **langchain 线**：依赖装在仓库根 `.venv`，版本清单与安装命令见
  [docs/langchain.md](docs/langchain.md)「环境配置」节。
- 无 Ollama 时，五条线大量项目支持离线模式（agents 与 langchain 的
  `--demo`、qa/harness/aitest 的 `MOCK=1`）。

## 快速开始

```bash
# 🛠️ agents 线: 从 01 开始按编号顺序做
python agents/01_call_llm_basics/call_llm_basics.py

# 🎯 qa 线: 任选问题切入, 或一键全量回归
MOCK=1 python qa/04_loop_guard/loop_guard.py   # 离线
bash qa/run_all.sh mock                        # 31 个 lab 离线回归
bash qa/run_all.sh real                        # 全量真机 (需 Ollama)

# 🎛️ harness 线: 从 01 的失败实录开始, 或一键全量回归
bash harness/run_all.sh mock

# 🧪 aitest 线: 从 01 搭测试台开始 (被测对象 = harness 的 mh)
MOCK=1 python aitest/01_testbench_sut/testbench_sut.py   # 离线

# 🔧 langchain 线: 从 01 LCEL 开始按编号顺序做
python langchain/01_lcel/lcel.py             # 真机 (需 Ollama)
python langchain/01_lcel/lcel.py --demo      # 离线
```

## 该从哪条线开始？

- **想系统学 Agent 开发** → 从 [agents/01](agents/01_call_llm_basics/README.md)
  按编号顺序推进，每步只引入一个新概念。
- **想做 RAG 检索增强** → 从同级仓库 [hands-on-rag](../hands-on-rag/README.md)
  的 labs/01_doc_splitting 开始，15 项覆盖索引到评估门禁全链路。
- **想按问题深入** → 直接看
  [qa/README.md](qa/README.md) 的问题→项目速查表，
  按三条问题主线（ReAct 手写 / 记忆+RAG / 系统设计）切入。
- **想理解 Agent = Model + Harness** → 从
  [harness/01](harness/01_no_harness_baseline/README.md) 的失败实录开始，
  亲手把 harness 造出来。
- **想测 AI 系统（评测/断言/红队/门禁）** → 从
  [aitest/01](aitest/01_testbench_sut/README.md) 搭建 testbench 测试台，
  被测对象就是仓库现成的 mh 运行时。
- **想吃透 LangChain/LangGraph 框架内核** → 从
  [langchain/01](langchain/01_lcel/README.md) 开始（有 agents 线基础更顺）。
- **三条线的关系**：qa 的题单文档
  [qa.md](docs/qa.md) 里有与 docs/agent.md（agents 线
  清单）的详细对照——重叠问题以 qa 的实证为准，LangChain 专属
  内容回 agents 线补。
