# hands-on-agentic-ai · 亲手构建 AI Agent（三条学习线）

> 一个仓库，三条线，**79 个可跑项目**：
>
> | 线 | 目录 | 定位 | 项目数 |
> |:--|:--|:--|:--:|
> | 🛠️ **技能主线** | [agents/](agents/README.md) | LangChain 视角，从裸调 API 到服务化的 30 项渐进实验 | 30 |
> | 🎯 **问题实证** | [qa/](qa/README.md) | 31 个高频问题一问一项目，含攻防对照与真机反常数据 | 31 |
> | 🎛️ **Harness 攻坚** | [harness/](harness/README.md) | 自研 mh/ mini-harness，18 项运行时实验 | 18 |
>
> 三条线互相印证：agents 教你"怎么一步步做出来"，qa 给你"每个问题的
> 最小可跑实证"，harness 把它们组装成可管控的运行时（重复问题两边
> README 互相链接）。

## 仓库结构

```
hands-on-agentic-ai/
├── agents/              # 🛠️ 技能主线: 7 阶段 30 实验 (索引见 agents/README.md)
│   └── 01_call_llm ... 30_observability_eval
│       每个实验四件套: README 教程 + 主脚本 + 架构图三件套
├── qa/                  # 🎯 问题实证: 8 阶段 31 项目 (索引见 qa/README.md)
│   ├── 01_cot_compare ... 31_checkpoint_resume
│   ├── run_all.sh       # 全量测试跑批器 (mock/real 双模式)
│   └── llm.py           # 两线共用的 OpenAI 兼容客户端 (本地 Ollama)
├── harness/             # 🎛️ Harness 攻坚: 18 实验 (自研 mh/ 包, 清单见 docs/harness.md)
├── docs/                # 各线的题单/清单文档
│   ├── agent.md             # agents 线学习清单 (30/30 完成)
│   ├── qa.md                # qa 线题单 (31/31 完成, 含全部踩坑记录)
│   └── harness.md           # harness 线学习清单 (18/18 完成, 含 Harness vs Agentic AI 速览)
└── scripts/             # 公共脚本 (模型预载等)
```

## 环境要求（三线共用）

安装 [Ollama](https://ollama.com/download) 后预拉两个本地模型（无需 API Key）：

```bash
ollama pull qwen3.8:latest           # 默认对话模型（约 17GB）
ollama pull nomic-embed-text:latest  # 向量嵌入（agents 17-19 / qa 08-10-28）
ollama serve                         # http://localhost:11434
```

- **agents 线**：Python 3.11+，按项目需要装 `requests / langchain / chromadb /
  fastapi / opentelemetry`（明细见 [agents/README.md](agents/README.md)）。
- **qa 线**：Python 3.10+，仅需 `jsonschema`（项目 15）与 `mcp`
  （项目 19/20）；绝大多数项目纯标准库。
- **harness 线**：零新增依赖，复用 qa 线客户端（见
  [harness/README.md](harness/README.md)）。
- 无 Ollama 时，三条线大量项目支持离线模式（agents 的 `--demo`、qa 与
  harness 的 `MOCK=1`）。

## 快速开始

```bash
# 🛠️ agents 线: 从 01 开始按编号顺序做
python agents/01_call_llm/call_llm.py

# 🎯 qa 线: 任选问题切入, 或一键全量回归
MOCK=1 python qa/04_loop_guard/loop_guard.py   # 离线
bash qa/run_all.sh mock                        # 31 个 lab 离线回归
bash qa/run_all.sh real                        # 全量真机 (需 Ollama)

# 🎛️ harness 线: 从 01 的失败实录开始, 或一键全量回归
bash harness/run_all.sh mock
```

## 该从哪条线开始？

- **想系统学 Agent 开发** → 从 [agents/01](agents/01_call_llm/README.md)
  按编号顺序推进，每步只引入一个新概念。
- **想按问题深入** → 直接看
  [qa/README.md](qa/README.md) 的问题→项目速查表，
  按三条问题主线（ReAct 手写 / 记忆+RAG / 系统设计）切入。
- **想理解 Agent = Model + Harness** → 从
  [harness/01](harness/01_no_harness_baseline/README.md) 的失败实录开始，
  亲手把 harness 造出来。
- **三条线的关系**：qa 的题单文档
  [qa.md](docs/qa.md) 里有与 docs/agent.md（agents 线
  清单）的详细对照——重叠问题以 qa 的实证为准，LangChain 专属
  内容回 agents 线补。
