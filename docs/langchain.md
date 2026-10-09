# 🔗 LangChain / LangGraph 框架深度 12 小项目学习清单 · Todo List

> 通过 12 个框架深度实验（每项目 80-250 行代码）吃透 LangChain 1.x / LangGraph 1.x 内核：LCEL 原语、结构化输出、`create_agent`、Middleware、状态图与 Reducer、持久化、中断、流式、Send 子图、多智能体路由、回调追踪与本地服务化
> 与 [docs/agent.md](agent.md)（30/30，入门级）互补：不重复基础用法，直击框架内部机制与 1.x 新范式（分工见文末关系表）
> 纯本机零云：Ollama 本地模型 + SQLite checkpointer + `langgraph dev` 本地服务，零 LangSmith / 云依赖 / API Key
> 串联机制：知识体系型——阶段即能力等级；项目 12 🏁 把前 11 项关键能力组装进一个本地部署的迷你研究助手
> 预计周期：3-4 周（每天 2-3 小时）

---

## 🤖 AI 辅助提示词速查

| 场景 | 提示词 |
|:---|:---|
| **开始一个新项目** | `我要开始 LangChain/LangGraph 深度项目「[名称]」，目标是 [目标]。环境：Python 3.13 + langchain 1.4.0 + langgraph 1.2.11 + ChatOllama(model="qwen3.8:latest", reasoning=False)。请给我完整可运行代码约 [行数] 行，附验收断言命令。只输出代码。` |
| **API 已过时** | `这段代码在 langchain 1.x / langgraph 1.x 上报 [报错]。注意这是 2025-10 之后的 1.0+ 版本，AgentExecutor / create_react_agent 等旧 API 已弃用。请按 1.x 当前 API 给出修复版。` |
| **排障** | `我的 [项目/图] 出现 [现象]，报错/日志：[粘贴]。请分析根因并给修复。` |
| **图状态调试** | `我的 LangGraph 图在 [节点] 后状态不对。当前 state：[打印]，期望：[期望]。请帮我定位是 reducer、边还是节点返回值的问题。` |

---

## 📊 总进度

进度：░░░░░░░░░░░░░░░░░░░░ 0/12 (0%)

| 阶段 | 项目数 | 已完成 |
|:---|:---:|:---:|
| 第一阶段：LangChain 1.x API 体系 | 4 | 0 |
| 第二阶段：LangGraph 编排内核 | 4 | 0 |
| 第三阶段：多智能体与 Agentic RAG | 2 | 0 |
| 第四阶段：可观测、评测与部署 | 2 | 0 |
| **合计** | **12** | **0** |

---

## 🗂️ 第一阶段：LangChain 1.x API 体系（项目 1-4）

> **目标**：吃透 1.x 的 Runnable 原语与 `create_agent` + Middleware 定制范式，理解框架在会话循环里到底托管了什么

---

### [ ] 项目 1：LCEL 与 Runnable 协议

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~150 行 |
| **核心知识点** | Runnable 统一协议（invoke/batch/stream）、`RunnablePassthrough` / `RunnableLambda` / `RunnableParallel` / `RunnableBranch`、`\|` 管道组合、用 LCEL 重写一条含分支的链 |
| **验收标准** | 同一条链在 invoke / batch / stream 三种调用方式下结果一致（断言批量输出与逐条调用相等）；`RunnableBranch` 按输入走不同支路且可断言分支命中 |
| **⚠️ 风险** | 无外部依赖，纯框架 API；若某原语在 1.4.0 签名有变，用速查表里的「API 已过时」提示词修复 |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「LCEL 与 Runnable 协议」。请给我完整 Python 代码约 150 行：用 RunnablePassthrough/Lambda/Parallel/Branch 拼一条含并行与分支的链（一个"分诊"链：按问题类型路由到不同 prompt 处理），演示 invoke/batch/stream 三种调用方式，并附断言脚本验证 batch 结果与逐条 invoke 一致、分支路由命中正确。模型用 ChatOllama(model="qwen3.8:latest", reasoning=False)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 2：消息体系、提示模板与结构化输出

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~150 行 |
| **核心知识点** | 消息类型（System/Human/AI/Tool）、`ChatPromptTemplate` 与 `MessagesPlaceholder`、Few-shot 示例注入、`with_structured_output`（Pydantic）、解析失败与校验重试 |
| **验收标准** | 输出严格匹配 Pydantic 模型（字段类型全对，可断言）；人为构造不合法输出时解析器抛错且重试策略生效（重试计数 ≥1）；同一个模板传不同 few-shot 示例产出不同风格（可对比断言） |
| **技术栈** | pydantic 2.13.5 ✅已装；`with_structured_output` ✅已实测（qwen3.8 与 qwen3:4b 均通过） |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「消息体系、提示模板与结构化输出」。请给我完整 Python 代码约 150 行：定义 Pydantic 输出模型（如工单分类结果），用 ChatPromptTemplate + MessagesPlaceholder 构建可注入 few-shot 示例的模板，用 with_structured_output 拿到严格校验的结构化对象；实现一个"坏输出自动重试"包装（解析失败时把错误回喂模型重试，记录重试次数）；附 pytest/assert 验收。模型用 ChatOllama(model="qwen3.8:latest", reasoning=False)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 3：create_agent——工具绑定与 Agent Loop 内核

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | `@tool` 装饰器与 schema 自动生成、`bind_tools`、`create_agent(model, tools, system_prompt, response_format)`、多步工具循环、工具报错回馈模型 |
| **验收标准** | 真机完成「模型→工具→模型」多轮收敛（消息里能数到 tool_calls 且最终答案正确）；注入一个必然抛错的工具后，模型收到错误文本并改用备用工具，不崩溃 |
| **前置** | 项目 2 |
| **⚠️ 风险** | qwen3:4b 实测**不触发工具调用**（直出文本）→ 工具类项目统一用 qwen3.8:latest + reasoning=False（仓库 agents/09 同款约定） |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「create_agent 工具绑定与 Agent Loop 内核」。请给我完整 Python 代码约 180 行：用 @tool 定义 3 个工具（其中 1 个是"故障工具"固定抛异常、1 个备用工具），用 langchain.agents.create_agent 组装 agent；任务设计成必须多步调用工具才能完成；演示工具报错后模型改用备用工具；并打印消息序列证明"模型→工具→模型"循环，附断言。模型用 ChatOllama(model="qwen3.8:latest", reasoning=False, num_predict=1024)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 4：Middleware——agent 运行时钩子

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | `AgentMiddleware` 钩子（before_agent / before_model / wrap_model_call / wrap_tool_call / after_model / after_agent）、自定义 middleware、预置 middleware（Summarization / ModelCallLimit / ToolRetry / PII 选装 2 个） |
| **验收标准** | 自定义 middleware 准确统计一次运行的 model_calls=2、tool_calls=1（✅ 实测同款断言）；装配 `ModelCallLimitMiddleware` 后超限行为可观测（日志或返回值可证），关闭后行为恢复 |
| **前置** | 项目 3 |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「Middleware：agent 运行时钩子」。请给我完整 Python 代码约 200 行：继承 langchain.agents.middleware.AgentMiddleware 写一个自定义 middleware（before_model 计数 + wrap_tool_call 记录/拦截指定工具），再对照装配 ModelCallLimitMiddleware 与 ToolRetryMiddleware 观察行为变化；用同一个 agent 跑两次（带/不带 middleware）对比；附断言脚本。模型用 ChatOllama(model="qwen3.8:latest", reasoning=False, num_predict=1024)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

## 🗂️ 第二阶段：LangGraph 编排内核（项目 5-8）

> **目标**：掌握状态图 / 持久化 / 中断 / 流式四大内核支柱，理解"durable execution"在代码里长什么样

---

### [ ] 项目 5：StateGraph 三件套——State、Reducer 与条件边

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | TypedDict state、`Annotated` reducer（`add_messages` / `operator.add`）、节点/边/条件边、fan-out/fan-in、带轮次上限的循环 |
| **验收标准** | 先复现「并行分支同时写同一 key」报 `InvalidUpdateError`，加 reducer 后同样的图正确合并全部分支输出；条件边循环在达到轮次上限时退出（断言实际轮数） |
| **⚠️ 风险** | 实测踩坑原文：`At key 'msgs': Can receive only one value per step. Use an Annotated key` —— 这是本项目的教学素材，不是环境问题 |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「StateGraph 三件套」。请给我完整 Python 代码约 180 行：构建一个含并行分支（fan-out/fan-in）和条件边循环的图；先用无 reducer 的状态演示并行写同一 key 报 InvalidUpdateError（打印报错），再加 Annotated[list, operator.add] 修复；循环带最大轮次守卫；附断言脚本（分支合并完整性、轮数上限）。用 langgraph 1.2.11 当前 API。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 6：Checkpointer——断点恢复与时间旅行

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~150 行 |
| **核心知识点** | `InMemorySaver` vs `SqliteSaver`、thread_id 与 configurable、`get_state` / `get_state_history`、进程崩溃后恢复、`update_state` 从历史 checkpoint 分叉重放 |
| **验收标准** | 图跑到一半 kill 进程，用同一 thread_id 重启恢复且已完成步骤不重算（磁盘/日志可证）；从倒数第 2 个 checkpoint 用 `update_state` 改输入重放，得到不同分支且旧历史保留（检查点计数断言，实测 5 个检查点） |
| **技术栈** | langgraph-checkpoint-sqlite 3.1.1 ✅本次核查已装并实测 |
| **前置** | 项目 5 |
| **⚠️ 风险** | 与 qa/31 的"手写检查点管线"不同，本项目练的是框架内核对等能力（关系表见文末） |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「Checkpointer 断点恢复与时间旅行」。请给我完整 Python 代码约 150 行：用 SqliteSaver 给 StateGraph 加持久化，thread_id 固定；脚本支持 --crash-at N 在指定步后 os._exit 模拟崩溃；重启后从最后检查点续跑（已完成步骤跳过）；再用 get_state_history + update_state 从历史检查点分叉重放一个不同输入，对比新旧分支；附断言。用 langgraph 1.2.11 当前 API，SqliteSaver.from_conn_string。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 7：interrupt 与 Human-in-the-loop

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | `interrupt()` 动态中断值、`Command(resume=...)`、approve / edit / reject 三决策、节点级中断 vs `HumanInTheLoopMiddleware` 工具级中断 |
| **验收标准** | 危险工具执行前中断；approve 链路跑通（✅ 实测）；edit 场景断言工具实际收到编辑后的参数（日志可证）；reject 场景断言工具未执行、模型收到拒绝理由 |
| **前置** | 项目 6（中断必须有 checkpointer） |
| **⚠️ 风险** | 实测 resume 载荷格式：`Command(resume={"decisions": [{"type": "approve"}]})`；edit/reject 的 decisions 格式按 1.x 中间件文档实现，开工先探活 approve 链路（已实测通过） |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「interrupt 与 Human-in-the-loop」。请给我完整 Python 代码约 180 行：实现一个带危险工具（如删文件/发邮件）的 agent，用 HumanInTheLoopMiddleware(interrupt_on=...) + SqliteSaver 实现工具执行前审批；CLI 演示 approve/edit（修改工具参数）/reject 三种决策；approve 的 resume 载荷用 {"decisions": [{"type": "approve"}]}；每步打印工具实际收到的参数与是否执行；附断言。模型用 ChatOllama(model="qwen3.8:latest", reasoning=False)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 8：流式输出——四种 stream_mode 与事件流

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | `stream_mode=values / updates / messages / custom`、`astream_events`、token 级流、把更新流封装成 CLI 实时输出（为项目 12 的 SSE 打底） |
| **验收标准** | 同一图用 4 种模式各流式跑一次，输出结构可断言（messages 出现 token 增量、updates 按节点出现、custom 出现自定义事件、values 为完整状态快照）；流式结束后拼出的最终状态与 `invoke` 结果一致 |
| **前置** | 项目 5 |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「流式输出四种 stream_mode」。请给我完整 Python 代码约 180 行：构建一个带 LLM 节点和图内自定义事件的 StateGraph；分别用 stream_mode="values"/"updates"/"messages"/"custom" 流式运行并打印结构化输出；custom 模式用 get_stream_writer 发自定义进度事件；最后断言流式拼接结果与 invoke 一致；再演示 astream_events 过滤 LLM token 事件做打字机效果。模型用 ChatOllama(model="qwen3.8:latest", reasoning=False)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

## 🗂️ 第三阶段：多智能体与 Agentic RAG（项目 9-10）

> **目标**：用 Send / Command / 子图这三个原语表达动态扇出与监督者路由，并给检索加上"评分回炉"循环

---

### [ ] 项目 9：编排原语——Send 动态扇出与 Command 监督者路由

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~250 行 |
| **核心知识点** | 编译图作为节点（子图嵌套）、`Send` 动态扇出、N 项并行 map + reducer 聚合、`Command(goto=..., update=...)` 手写 supervisor、worker 间 handoff 交接、路由决策审计 |
| **验收标准** | ① send-map-reduce 图：N 由输入列表长度决定（N=3 与 N=7 各跑一次），并行分支数 = N（事件计数断言），聚合完整、子图状态不泄漏；② supervisor 图：按输入类型路由到 ≥2 个 worker 并汇总，handoff 后上下文不丢，每次 goto 目标可从 state 审计列举 |
| **前置** | 项目 5 |
| **⚠️ 风险** | `Send` 只能从条件边路由函数返回（实测踩坑：放进普通节点会报 Expected dict），从 `langgraph.types` 导入；选做：`pip install langgraph-supervisor` 做对照（非必需，开工探活） |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「编排原语：Send 动态扇出与 Command 监督者路由」。请给我完整 Python 代码约 250 行：①一个"批量文档处理"图——条件边路由函数返回 [Send("process", {"doc": d}) for d in docs] 动态扇出，process 节点用独立编译的摘要子图处理单条文档，reducer 聚合；②一个 supervisor 图——用 Command(goto=..., update=...) 路由到"研究员"和"统计员"两个 worker 子图，并演示 worker 间 handoff，记录每次路由目标到 state 供审计；附断言脚本（扇出数随输入变化、路由命中、上下文保留、审计列表）。模型用 ChatOllama(model="qwen3.8:latest", reasoning=False)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 10：Agentic RAG——检索 + 评分回炉循环

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~220 行 |
| **核心知识点** | 文档加载与切分（langchain-text-splitters）、OllamaEmbeddings + Chroma、检索工具、相关性评分节点、查询改写回炉、无法回答时拒答 |
| **验收标准** | 用本仓库 docs/ 建知识库，3 个问题中至少 2 个答案能引用正确来源文件；注入 1 个知识库外问题，评分循环触发 ≥1 次查询改写后仍无据可依 → 拒答（可断言） |
| **技术栈** | langchain-text-splitters 1.1.3、langchain-chroma 1.1.0、chromadb 1.5.9 ✅已装实测 |
| **前置** | 项目 5 |
| **⚠️ 风险** | 实测 nomic-embed-text 中文短文本检索**样本 top1 命中不准**（"编排工作流用什么"命中"Chroma 是轻量向量数据库"）→ 本项目必须对比 embedding 模型 / 查询改写 / rerank，用评分循环把质量拉回来；这是教学重点不是环境缺陷 |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「Agentic RAG 检索评分回炉」。请给我完整 Python 代码约 220 行：用 langchain-text-splitters 切分本仓库 docs/ 下的 md 文件，用 OllamaEmbeddings(model="nomic-embed-text") + langchain_chroma.Chroma 建本地库；构建 LangGraph 图：检索→相关性评分（LLM 打分）→不合格则改写查询重试（最多 2 次）→生成带来源引用的答案，无据时明确拒答；用 3 个可答问题 + 1 个库外问题验收（断言来源引用与拒答）。模型 ChatOllama(model="qwen3.8:latest", reasoning=False)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

## 🗂️ 第四阶段：可观测、评测与部署（项目 11-12）

> **目标**：让框架运行"看得见"（回调与追踪），并把前 11 项能力组装成一个可本地部署、可审批、可追踪的 Agent 服务

---

### [ ] 项目 11：回调系统与本地追踪 / 轻评测

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | `BaseCallbackHandler` 与 run tree 父子 span、`on_llm_start` / `on_tool_start` 钩子、token 与耗时统计、trace 落盘 JSON、≥10 用例评测跑批、两版对比（改善/劣化/持平） |
| **验收标准** | 一次 agent 运行落地结构化 trace（每次 LLM / 工具调用都有耗时与 token 字段）；评测跑批 ≥10 用例输出通过率，并对两版 prompt 或模型给出「改善 X / 劣化 Y / 持平 Z」对比 |
| **前置** | 项目 3 |
| **⚠️ 风险** | 按零云约束不使用 LangSmith；追踪全部自研（回调 + JSON 落盘）。与 aitest 线的完整测试台不同，这里只做框架回调视角的追踪与轻量回归 |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「回调系统与本地追踪/轻评测」。请给我完整 Python 代码约 200 行：实现自定义 BaseCallbackHandler，挂在模型与 agent 上，收集 run tree（父子 run、每次 LLM/工具的耗时与 token 数）并落盘 trace.json；再写一个评测跑批器：读取 ≥10 条用例数据集，对两版 system prompt 各跑一轮，输出通过率与「改善/劣化/持平」对比表；全程零云依赖。模型 ChatOllama(model="qwen3.8:latest", reasoning=False)。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 🏁 项目 12：本地服务化——langgraph dev 与 SDK 总装

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~250 行 |
| **核心知识点** | `langgraph.json` 配置、assistant / thread / run 资源模型、`langgraph-sdk` Python 客户端、interrupt 的远程处理与 resume、本地持久化（`.langgraph_api/` 落盘）、把 RAG + 危险工具审批 + 回调追踪装进一张图 |
| **验收标准** | `langgraph dev` 本地起服务（无云 key），SDK 完成 create thread → run → interrupt → resume 全流程；服务重启后同 thread 状态仍可查（实测重启后 state 保留）；总装图同时包含检索工具、危险工具审批、追踪回调三个前 11 项能力（集成断言） |
| **前置** | 项目 6、7、10、11 |
| **⚠️ 风险** | 官方文档称 dev server 需要免费 LangSmith key；但实测 0.4.33 无 key 可启动并跑通全流程（日志显示 "No license key ... skipping"）。若未来升级后强制要 key：fallback ① `LANGSMITH_TRACING=false` + 免费 key 仅作启动通行证（数据不出本机）；② 弃 dev server，用 FastAPI + 项目 8 的 SSE 能力自封装 |

**🤖 开始提示词**：
> `我要开始 LangChain/LangGraph 深度项目「本地服务化：langgraph dev 与 SDK 总装」。请给我：①一个 langgraph.json + 总装图（迷你研究助手：检索工具 + 危险工具审批 + 回调追踪三能力合一）；②一个 Python 客户端脚本用 langgraph_sdk.get_client 演示 create thread → runs.wait/stream → 处理 interrupt → Command resume 的完整流程；③验收脚本：langgraph dev --no-browser 起服务后跑通全流程，重启服务后再查同一 thread 状态。零云依赖，模型 ChatOllama(model="qwen3.8:latest", reasoning=False)。只输出代码与文件清单。`

**完成日期**：________
**踩坑记录**：________

---

## 📅 周计划

| 周次 | 内容 | 项目数 |
|:---|:---|:---:|
| **第 1 周** | 项目 1-4（LangChain 1.x API 体系） | 4 |
| **第 2 周** | 项目 5-8（LangGraph 编排内核） | 4 |
| **第 3 周** | 项目 9-11（编排原语/Agentic RAG/可观测） | 3 |
| **第 4 周** | 项目 12（总装部署）+ 缓冲与复盘 | 1 |

---

## 🏆 里程碑

- [ ] **完成项目 1-4** → 掌握 LangChain 1.x API 体系（LCEL / 结构化输出 / create\_agent / middleware）
- [ ] **完成项目 5-8** → 掌握 LangGraph 内核四大支柱（状态图 / 持久化 / 中断 / 流式）
- [ ] **完成项目 9-11** → 能编排动态子图与监督者路由，具备回调追踪与本地轻评测能力
- [ ] **完成项目 12** → 具备把框架能力组装为本地 Agent 服务并交付的能力

---

## 🔧 环境配置

```bash
# 0. 已就绪（2026-10-09 实测）：
#    Python 3.13.9(.venv) · langchain 1.4.0 · langchain-core 1.6.3 · langchain-ollama 1.1.0
#    langgraph 1.2.11 · langgraph-checkpoint 4.2.0 · langgraph-sdk 0.4.4 · pydantic 2.13.5
#    langgraph-checkpoint-sqlite 3.1.1 · langchain-text-splitters 1.1.3 · langchain-chroma 1.1.0
#    langgraph-cli 0.4.33（含 inmem dev server） · chromadb 1.5.9
#    Ollama: qwen3.8:latest（主力，工具调用） / qwen3:4b（降速，勿用于工具类） / nomic-embed-text（嵌入）

# 1. 需安装（本次环境核查已装入 .venv，换机时重装；走清华镜像）：
.venv/bin/pip install langgraph-checkpoint-sqlite langchain-text-splitters langchain-chroma "langgraph-cli[inmem]"

# 2. 每项目开工前：
curl -sf http://localhost:11434/v1/models >/dev/null || echo "⚠️ Ollama 未启动: ollama serve"
#    统一模型约定：ChatOllama(model="qwen3.8:latest", reasoning=False)
#    ⚠️ 工具调用类实验不要用 qwen3:4b（实测不触发工具调用）
```

---

## ⚠️ 与已有清单的关系

| 已有清单 | 关系 |
|:---|:---|
| [docs/agent.md](agent.md)（30/30 ✅） | **互补分工，不重复**：agent.md 是入门用法视角（agents/09 首次用 `create_agent`、agents/24 StateGraph 入门、agents/20-23 RAG 基础、agents/30 评测初步），本清单从项目 3/4 起是其**内核进阶**（middleware 定制、checkpointer、interrupt、stream_mode、Send/Command），RAG 只在项目 10/12 以"评分回炉 + 总装"形态出现，入门步骤**跳过** |
| [docs/qa.md](qa.md)（31/31 ✅） | qa/31 是**手写**检查点管线，本项目 6 是框架 checkpointer 的对等能力；qa/15 HITL 与 qa/21-27 多 Agent 是"能讲清"级，项目 7/9 是"用框架原语实现"级；本题单不重复面试考点梳理 |
| [docs/harness.md](harness.md)（17/18 ✅） | mh 是自研运行时（确定性规则管控），本清单是框架层（概率编排 + 官方运行时）；视角不同、无重叠项目 |
| [docs/aitest.md](aitest.md)（9/21） | 测试台视角在 aitest 线（断言/回归/红队/门禁）；项目 11 只做框架回调视角的 trace 与轻评测，**不建测试台**，测试 AI 系统方法论以 aitest 为准 |

---

## ⚠️ 能力覆盖速查表（2026-10-09 本机实测）

| 能力 | 计划用途 | 实测结论 |
|:---|:---|:---|
| `create_agent` + qwen3.8 工具循环 | 项目 3/4/7/12 | ✅ 真机跑通（tool_used=True，21+21=42，两轮收敛） |
| Ollama qwen3:4b 工具调用 | 降速档 | ⚠️ 实测不触发工具（直出文本）→ 工具类用 qwen3.8；4b 留给纯文本/批跑 |
| `with_structured_output` + Pydantic | 项目 2 | ✅ qwen3.8 与 qwen3:4b 均通过 |
| 自定义 AgentMiddleware 钩子 | 项目 4 | ✅ before_model×2 + wrap_tool_call×1，计数可断言 |
| HumanInTheLoopMiddleware | 项目 7/12 | ✅ interrupt 触发 + approve resume 通过；edit/reject 按文档实现待开工验证 |
| Send 动态扇出 + reducer | 项目 5/9 | ✅ N=2 扇出聚合；无 reducer 并行写报错已复现（教学素材） |
| interrupt / Command + SqliteSaver | 项目 6/7 | ✅ 中断→resume→重启恢复→5 个历史检查点全通过 |
| `langgraph dev`（0.4.33） | 项目 12 | ✅ 无云 key 启动 `/ok`；SDK thread/run 端到端；重启后 thread 状态保留（`.langgraph_api/` 落盘） |
| Chroma + nomic-embed-text 中文检索 | 项目 10 | ⚠️ 样本 top1 命中不准 → 需对比 embedding / 查询改写 / rerank（教学重点） |
| LangSmith 云追踪/评测 | ~~原可能方案~~ | ❌ 按零云约束排除，追踪自研（项目 11） |

---

## 📚 来源

- [LangChain and LangGraph Agent Frameworks Reach v1.0 — LangChain Blog](https://www.langchain.com/blog/langchain-langgraph-1dot0)：create\_agent、middleware、1.0 稳定承诺与包瘦身
- [What's new in LangChain v1 — 官方文档](https://docs.langchain.com/oss/python/releases/langchain-v1)：middleware 六钩子表、预置 middleware 清单
- [Agent Middleware — LangChain Blog](https://www.langchain.com/blog/agent-middleware)：middleware 设计动机与钩子语义
- [Graph API — LangGraph 文档](https://docs.langchain.com/oss/python/langgraph/graph-api)、[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)、[Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)、[Time Travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- [Run a local server — LangGraph CLI 文档](https://docs.langchain.com/oss/python/langgraph/local-server)、[CLI Commands](https://docs.langchain.com/langsmith/cli)：`langgraph dev` 与 `langgraph up` 的能力边界

---

## 📝 每日日志

| 日期 | 项目 | 耗时 | 收获 | 踩坑 |
|:---|:---|:---:|:---|:---|
| | | | | |
| | | | | |
| | | | | |
