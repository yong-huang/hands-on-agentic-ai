# REPORT · Claude Code 式 Agent Harness 解剖报告

> 验收产出：`docs/harness.md` 项目 2。资料来源见文末，所有论断标注出处；
> 未直接读过 Claude Code 闭源源码，二手拆解结论均已注明"据转述"。

## 1. 一张图：harness 分层架构

见 [README.md](README.md) 内嵌架构图（交互版 `images/harness_anatomy.html`）。
核心读法：**LLM 在区域外，只负责推理；区域内九个模块全是确定性工程**——
这就是 "Agent = Model + Harness" 的图形化。

## 2. Harness 模块职责表（≥7 个，验收项①）

| # | 模块 | 职责 | 失效时的症状（对应本项目 01 实验） |
|:--|:--|:--|:--|
| 1 | 启动链路 | CLI/REPL 入口、会话初始化、斜杠命令分发 | 无统一入口，行为不可预期 |
| 2 | Prompt 装配 | 组装系统提示、CLAUDE.md 类项目规则、Skills 按需注入 | 模型不知道"自己是谁、在哪、被允许做什么" |
| 3 | 查询引擎（主循环） | ReAct 循环、停止条件、消息历史管理 | 死循环、无收敛（01 实验 A 组实锤） |
| 4 | 工具系统（契约） | 工具注册、schema 生成与校验、错误信息回传设计 | 参数幻觉、错误后无法自纠（项目 05 治理） |
| 5 | 权限门 | allow/ask/deny 规则、敏感操作 HITL 审批、审计日志 | 危险命令直通，无组织策略（项目 07） |
| 6 | 沙箱与执行 | 隔离执行、超时杀死、输出截断、目录约束 | 死循环脚本拖垮宿主（项目 06 治理） |
| 7 | 上下文管理 | 阈值触发压缩、旧工具结果占位符化 | context rot，长任务遗忘（项目 10） |
| 8 | 会话与记忆 | checkpoint 持久化、崩溃恢复、跨会话 MEMORY.md | 断电丢全部进度（项目 11/12） |
| 9 | 扩展机制 | 子代理调度、Hooks 生命周期、MCP 动态工具、Skills 懒加载 | 能力写死，无法挂载外部工具（项目 13-15） |

其中 1-2-3 构成"主干道"，4-5-6 构成"执行面"，7-8 构成"续航面"，9 是"挂载点"。
据源码拆解文章转述，Claude Code 内部为五层（权限门/上下文管理/查询引擎/
工具系统/多 agent 输出），与本表一一对应——本系列把它们拆成 9 个可动手的实验。

## 3. Model / Harness / Framework / Platform 四层对照（验收项②）

**模型**解决"会不会"：给定上下文，预测下一个 token。它是概率性的、无状态的、
任务无关的。**Harness** 解决"做不做得到、被允许做什么"：围绕单个 agent 的
运行时——执行循环、工具、沙箱、权限、上下文与记忆管理，全部是确定性代码。
**Framework** 解决"怎么组合多个 agent"：LangGraph/CrewAI 这类库提供蓝图，
让你声明角色、工作流图、交接条件——它是**设计时**概念。**Platform** 解决
"怎么在组织里跑一堆 harness"：持久执行、成本归因、治理与审计——它是
**组织级**概念。Winder.AI 的总结最锋利：**"Frameworks compose agents.
Harnesses run them."**

四层的分界可以用一句话测试：换掉这一层，其余要不要重写？换模型不用改
harness（模型无关性是 harness 的卖点）；换 harness 不改模型（01 实验里
15 行执行层就是最小 harness）；换 framework 通常要改 harness 交互方式；
换 platform 不改任何一个 agent。**竞争护城河在 harness 与 platform，不在
模型**——模型终会商品化，而"沙箱、权限、预算、审计编码的是组织政策，
模型升级不会废除它们"（Winder.AI）。

## 4. Harness AI vs Agentic AI：区别论述（验收项③）

Agentic AI 是**范式**：AI 系统自主感知→规划→行动以达成目标，ReAct 循环
和 LangGraph 编排的工作流都是它的实现形态，回答的是"agent 做什么、为什么"。
Harness（AI）是**工程层**：包裹 LLM 的运行时基础设施，回答"怎么做、在哪做、
被允许做什么"。Salesforce 的表述：**agent 管 what/why（概率性推理），
harness 管 how/where（确定性规则）**。三代演进讲的是同一件事：第一代 RAG
只读不写；第二代 Agentic 框架把一切预定义进工作流图，"该 agent 与你为它
画的工作流图一样僵化"；第三代 Harness Engineering 反转设计哲学——
**"The model decides what to do. The harness decides what's allowed."**
不预定义行为，只定义约束边界，把模型放进去跑。

实证上两者不是并列概念而是包含关系：agentic 系统建立在"推理与执行分离"
之上（Databricks），harness 正是那个执行层。同一模型在不同 scaffold 下
得分 42% vs 78%；生产故障大多"来自 harness 而非模型"。**学 Agentic AI
告诉你 agent 能干什么，学 Harness 告诉你为什么它干不成——以及怎么让它
干成。** 本系列就是后者的动手版。

## 5. 对本系列后续实验的映射

| 解剖发现 | 落地实验 |
|:--|:--|
| 主循环 + 停止条件 | 04 min_loop |
| 工具契约与错误回传 | 05 tool_contract |
| 沙箱与输出治理 | 06 sandbox |
| 权限门 + HITL | 07 permissions |
| Hooks 生命周期 | 08 hooks |
| 预算（论文实证：token 通胀 391K→668K） | 09 budget |
| 上下文压缩 | 10 compaction |
| checkpoint/记忆 | 11/12 |
| 子代理/MCP/Skills | 13-15 |
| Agent QA（支架质量回归） | 16 eval |

## 6. 来源

- Databricks: What is an AI Agent Harness? —— 八大组件、失败模式、"Agent = Model + Harness"
- Salesforce: What Is an Agent Harness? —— what/why vs how/where、权限五步、HITL interrupts
- Winder.AI: A Comparison of AI Agent Harnesses in 2026 —— 四层架构、九大 harness 对比
- InterSystems: 3rd Generation of Agents —— 三代演进、Claude Code 五层架构转述、guides/sensors/ratchet
- suedbroecker.net: Agent Harness in 2026 —— 六方术语趋同证据
- alphaXiv 2607.03691 —— 固定模型变 scaffold 的 3500 次受控实验
- awesome-ai-agent（GitHub）—— Claude Code 源码拆解文章索引（转述来源）
