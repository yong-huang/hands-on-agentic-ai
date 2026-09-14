# hands-on-agentic-ai · 亲手构建 AI Agent（两条学习线）

> 一个仓库，两条线，**61 个可跑项目**：
>
> | 线 | 目录 | 定位 | 项目数 |
> |:--|:--|:--|:--:|
> | 🛠️ **技能主线** | [agents/](agents/README.md) | LangChain 视角，从裸调 API 到服务化的 30 项渐进实验 | 30 |
> | 🎯 **面试攻坚** | [interview/](interview/README.md) | 高频面试真题一题一项目，含攻防对照与真机反常数据 | 31 |
>
> 两条线互相印证：agents 教你"怎么一步步做出来"，interview 给你"每道
> 面试题的最小可跑实证"（重复考点两边 README 互相链接）。

## 仓库结构

```
hands-on-agentic-ai/
├── agents/              # 🛠️ 技能主线: 7 阶段 30 实验 (索引见 agents/README.md)
│   └── 01_call_llm ... 30_observability_eval
│       每个实验四件套: README 教程 + 主脚本 + 架构图三件套
├── interview/           # 🎯 面试攻坚: 8 阶段 31 项目 (索引见 interview/README.md)
│   ├── 01_cot_compare ... 31_checkpoint_resume
│   ├── run_all.sh       # 全量测试跑批器 (mock/real 双模式)
│   └── llm.py           # 两线共用的 OpenAI 兼容客户端 (本地 Ollama)
├── docs/                # 两线的题单/清单文档
│   ├── agent.md             # agents 线学习清单 (15/30 进度)
│   └── agent_interview.md   # interview 线题单 (31/31 完成, 含全部踩坑记录)
└── scripts/             # 公共脚本 (模型预载等)
```

## 环境要求（两线共用）

安装 [Ollama](https://ollama.com/download) 后预拉两个本地模型（无需 API Key）：

```bash
ollama pull qwen3.8:latest           # 默认对话模型（约 17GB）
ollama pull nomic-embed-text:latest  # 向量嵌入（agents 17-19 / interview 08-10-28）
ollama serve                         # http://localhost:11434
```

- **agents 线**：Python 3.11+，按项目需要装 `requests / langchain / chromadb /
  fastapi / opentelemetry`（明细见 [agents/README.md](agents/README.md)）。
- **interview 线**：Python 3.10+，仅需 `jsonschema`（项目 15）与 `mcp`
  （项目 19/20）；绝大多数项目纯标准库。
- 无 Ollama 时，两线大量项目支持离线模式（agents 的 `--demo`、interview
  的 `MOCK=1`）。

## 快速开始

```bash
# 🛠️ agents 线: 从 01 开始按编号顺序做
python agents/01_call_llm/call_llm.py

# 🎯 interview 线: 任选考点切入, 或一键全量回归
MOCK=1 python interview/04_loop_guard/loop_guard.py   # 离线
bash interview/run_all.sh mock                        # 31 个 lab 离线回归
bash interview/run_all.sh real                        # 全量真机 (需 Ollama)
```

## 该从哪条线开始？

- **想系统学 Agent 开发** → 从 [agents/01](agents/01_call_llm/README.md)
  按编号顺序推进，每步只引入一个新概念。
- **准备 Agent 面试** → 直接看
  [interview/README.md](interview/README.md) 的考点→项目速查表，
  按面试主线三段（ReAct 手写 / 记忆+RAG / 系统设计）切入。
- **两条线的关系**：interview 的题单文档
  [agent_interview.md](docs/agent_interview.md) 里有与 docs/agent.md（agents 线
  清单）的详细对照——重叠考点以 interview 的实证为准，LangChain 专属
  内容回 agents 线补。
