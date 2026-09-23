# 🎛️ Harness AI（Agent Harness）18 小项目学习清单 · Todo List

> 通过 18 个小项目（每项目 80-300 行代码）亲手造一个类 Claude Code 的 Agent Harness，重点吃透 **Harness AI 与 Agentic AI 的区别**
> 本机 Ollama 免 Key 可跑（复用 `qa/llm.py` 的 OpenAI 兼容约定），零云依赖、零新增安装
> 串联机制：全部项目共同生长为 `harness/mh/` mini-harness 包，每阶段末 ⛓️ 集成接线，项目 17 🏁 终极总装
> 预计周期：4 周（每天 2-3 小时）

---

## ⚡ 先答核心问题：Harness AI vs Agentic AI

2026 年的行业共识（Databricks / Salesforce / Winder.AI / VS Code / Microsoft 六方术语趋同）：

| 维度 | Agentic AI | Harness（AI） |
|:--|:--|:--|
| **定位** | 范式：AI 自主感知→规划→行动达成目标 | 工程层：包裹 LLM 的**运行时**基础设施 |
| **回答的问题** | agent 做什么、为什么（the what） | 怎么做、在哪做、**被允许做什么**（the how） |
| **性质** | 概率性推理（模型=大脑） | 确定性规则（权限/预算/护栏/恢复=身体与工作空间） |
| **代表形态** | ReAct 循环、LangGraph/CrewAI 编排的工作流 | Claude Code、Codex CLI、OpenCode、Goose |
| **一句话** | Frameworks **compose** agents | Harnesses **run** them |

- 核心公式：**Agent = Model + Harness**。模型负责推理，harness 负责执行、记忆、权限与规则强制
- 三代演进：① RAG（只读检索）→ ② Agentic 框架（预定义编排，"和工作流图一样僵化"）→ ③ **Harness Engineering**（只定义约束边界，释放模型："The model decides what to do. The harness decides what's allowed."）
- 实证数据（为什么 harness 值得单独学）：同一模型换 scaffold 得分 **42% vs 78%**；Vercel 删掉 80% 工具后成功率 80%→100%、延迟 724s→141s；论文固定模型只变 harness 版本，解决率原地踏步（~30.5%）而 **token 消耗 391K→668K 近乎翻倍**——生产事故大多"来自 harness，而非模型本身"
- 与本仓库已有两线的关系：`agents/` 线 = framework 视角（设计时组合能力），`qa/` 线 = 问题实证视角（能讲清），**本线 = harness 视角（能造出）**——见文末关系表

---

## 🏗️ 终极蓝图（项目 17 完成时的 mini-harness）

```
                ┌──────────────────────────────────────┐
                │      mini-harness CLI (项目 17 🏁)     │
                │     REPL · /命令 · 端到端真实任务        │
                └──────────────────┬───────────────────┘
   ┌─────────┬─────────┬─────────┬──┴──────┬─────────┬─────────┐
   │permission│ hooks  │compaction│ session │ memory  │subagent │
   │ (项目7)  │ (项目8) │ (项目10) │ (项目11) │(项目12) │ (项目13)│
   └────┬────┴────┬────┴────┬────┴────┬────┴────┬────┴────┬────┘
        └─────────┴────┬────┴─────────┴────┬────┴─────────┘
                       │      budget/skills/MCP        │
                       │      (项目9/14/15)             │
                ┌──────┴──────────────────────────────┐
                │        agent loop (项目 4-6)          │
                │    while 循环 · 工具契约 · 沙箱执行      │
                └──────────────────┬──────────────────┘
                ┌──────────────────┴──────────────────┐
                │      LLM (Ollama qwen3.8, 免 Key)    │
                └─────────────────────────────────────┘
```

每个项目给 `harness/mh/` 包加一个模块，`harness/NN_xxx/` 放该项目的验收脚本与实验记录；项目 16 的评测台负责量化每一次演进。

## 🤖 AI 辅助提示词速查

| 场景 | 提示词 |
|:---|:---|
| **开始一个新项目** | `我要开始 Agent Harness 项目「[名称]」，目标是 [目标]。请给我完整 Python 代码约 [行数] 行（Python 3.11+，LLM 走 OpenAI 兼容接口：base_url/model 从环境变量 LLM_BASE_URL/LLM_MODEL 读取，默认 http://localhost:11434/v1 + qwen3.8:latest，支持 MOCK=1 离线），复用 /Users/hyhit/Desktop/workspace/projects/hands-on-agentic-ai/qa/llm.py 的 chat() 客户端，含验收断言与运行命令。只输出代码。` |
| **排障** | `我的 mini-harness 出现 [现象]，报错/日志：[粘贴]。请分析是模型问题还是 harness 问题，给修复代码。` |
| **对照 Claude Code 设计** | `我正在自研 harness 的 [模块]（当前实现：[粘贴代码]）。Claude Code 源码中同类机制是这样设计的：[资料要点]。请指出我的实现差距并给改进版代码。` |
| **评测设计** | `我要为 harness 做回归评测，任务是 [描述]。请给我评分器代码：解决率/token 消耗/轮次三个指标，输出 markdown 对比表。只输出代码。` |

## 📊 总进度

进度：██████████████████ 18/18 (100%)

| 阶段 | 项目数 | 已完成 |
|:---|:---:|:---:|
| 第一阶段：概念破题——Harness 与 Agentic AI 的分界 | 3 | 3 |
| 第二阶段：最小可运行 Harness | 3 | 3 |
| 第二阶段：最小可运行 Harness | 3 | 0 |
| 第三阶段：控制面——权限、Hook、预算 | 3 | 3 |
| 第四阶段：上下文工程与记忆 | 3 | 3 |
| 第五阶段：扩展机制 | 3 | 3 |
| 第六阶段：评测与总装 | 3 | 3 |
| **合计** | **18** | **18** |

---

## 🗂️ 第一阶段：概念破题——Harness 与 Agentic AI 的分界（项目 1-3）

> **目标**：不用一句空话，用自己跑出来的失败日志和对照数据，讲清"Harness AI 和 Agentic AI 差在哪"

### [x] 项目 1：无 Harness 基线——裸 LLM 的多步任务失败实录

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~150 |
| **核心知识点** | 裸模型缺陷、失败模式分类（工具幻觉/死循环/上下文漂移/无状态）、基线思维 |
| **产出模块** | `harness/01_no_harness_baseline/`（实验脚本 + `FAILURES.md` 失败实录） |
| **技术栈** | Python 标准库 + `qa/llm.py`（已实测 ✅） |
| **验收标准** | 让裸 LLM（仅 prompt，无工具执行层）完成"在 tmp 目录创建 3 个文件并统计行数"的多步任务 10 次：≥3 种经典失败模式各有 1 份日志证据存入 FAILURES.md；对照组（手写 10 行的"给它 bash 工具"最简循环）成功率显著更高并有数字对比 |
| **⚠️ 风险** | 本地小模型失败更快，属正常实验现象，不是 bug |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「无 Harness 基线」。请给我完整 Python 代码约 150 行：一个 runner 让裸 LLM 通过对话（无工具执行、无重试控制）尝试完成多步文件任务，自动记录每轮对话与结果；另加一个 10 行的对照组（直接 exec 模型输出的 bash 命令）。输出失败分类统计表。复用 qa/llm.py 的 chat()，支持 MOCK=1。附验收命令。只输出代码。`

**完成日期**：2026-09-18（真机 qwen3.8 10×2：A 组 0/10，B 组 10/10，见 `harness/01_no_harness_baseline/results/`）
**踩坑记录**：① 模型"命令+任务完成"同轮时先判完成导致命令漏执行——harness 动作必须先于模型结论；② qwen3:4b 混合推理把 1200 token 配额全花在思考上 content 为空（/no_think 兜底）；③ 系统代理把 localhost:11434 劫持到 :7890 致跑批静默卡死（NO_PROXY 豁免）；④ mock 自检会污染真机 results/（自检改写临时目录）

---

### [x] 项目 2：拆解工业 Harness——Claude Code 分层地图

| 项目信息 | 详情 |
|:---|:---|
| **行数** | 报告 ~600 字 + 架构图 1 张 |
| **核心知识点** | Harness 分层架构（权限门/上下文管理/查询引擎/工具系统/多 agent）、framework vs harness vs platform 四层模型 |
| **产出模块** | `harness/02_harness_anatomy/REPORT.md` + `anatomy.svg` 架构图 |
| **前置** | 项目 1 |
| **验收标准** | REPORT.md 含：① Claude Code 至少 7 个 harness 模块的职责表（启动链路/Prompt 装配/主循环/工具契约/文件编辑约束/权限决策/压缩与记忆）② 500 字「framework 组合 agent、harness 运行 agent、platform 托管 harness」对照论述 ③ 一张分层架构图，能对着图 3 分钟讲完区别 |
| **⚠️ 风险** | 源码拆解资料为二手（2026-03 npm source map 泄露事件后的分析文），以文末来源链接为准，不臆造源码细节 |

**🤖 开始提示词**：
> `我在学 Agent Harness，刚做完「无 Harness 基线」实验。请基于以下资料要点（我会粘贴 Databricks/Salesforce/Winder.AI/Claude Code 源码拆解的摘要），帮我起草 REPORT.md：Claude Code harness 分层职责表、framework/harness/platform 四层对照论述、以及"Agentic AI 是范式、Harness 是运行时工程层"的区别论述。要求每个论断标注来源。`

**完成日期**：________
**踩坑记录**：________

---

### [x] 项目 3：固定模型变 Harness——亲手复现"换 harness 比换模型影响大"

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 |
| **核心知识点** | 受控变量法（固定模型只变 scaffold）、解决率/token/轮次三指标、Agent QA 思想 |
| **产出模块** | `harness/03_scaffold_ab_test/`（任务集 + 两配置 runner + 对比表） |
| **前置** | 项目 1 |
| **技术栈** | 复用 qa 线已验证的评测套路（已实测 ✅） |
| **验收标准** | 固定 `qwen3.8:latest`，同一 10 任务集跑两种 harness 配置（A：无工具描述优化+无错误回传；B：schema 校验+错误回传+结果截断）：产出 markdown 对比表，含解决率/平均 token/平均轮次三行，两配置差异全部量化；任务集与跑批脚本可一键重跑 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「固定模型变 Harness 对照实验」。请给我完整 Python 代码约 200 行：10 个可自动判分的文件操作任务、两个 harness 配置（A 裸奔 / B 有工具契约治理），固定 qwen3.8 跑批，输出解决率/token/轮次对比表。复用 qa/llm.py，支持 MOCK=1。附验收命令。只输出代码。`

**完成日期**：2026-09-18（真机 qwen3.8 10 任务×2 配置：A/B 均 10/10，轨迹完全一致——零差异是主发现）
**踩坑记录**：① 强模型+顺任务域测不出契约治理差异（40 调用零失败），A/B"惩罚"一次未被触发——后续实验必须注入扰动或分难度档；② 修复预算 0 次使用；③ temperature=0 轨迹逐字可复现，评测需温度>0 或难度梯度才有分布信息

---

## 🗂️ 第二阶段：最小可运行 Harness（项目 4-6）

> **目标**：从 0 长出 `harness/mh/` 包的骨架：agent loop + 工具契约 + 安全执行，`Agent = Model + Harness` 里的 Harness 正式存在

### [x] ⛓️ 项目 4：最小 Agent Loop——mini-harness v0.1

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 |
| **核心知识点** | agent 主循环、工具调用协议（tool_calls 解析）、停止条件、消息历史管理 |
| **产出模块** | `harness/mh/loop.py` + `harness/04_min_loop/demo.py` |
| **技术栈** | Ollama 原生支持 function calling（qwen3.8，已实测 ✅） |
| **验收标准** | `python harness/04_min_loop/demo.py` 一条命令：agent 自主完成"在 /tmp/mh_demo 创建 hello.py（内容打印日期）并运行它"两步任务，全程零人工干预，`--trace` 参数能看到每一轮的完整消息历史 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「最小 Agent Loop」。请给我完整 Python 代码约 180 行：harness/mh/loop.py 实现 run_agent(task, tools, max_turns) 主循环（LLM→tool_calls→执行→结果回填→继续，直到 finish 或超轮次），内置一个 run_bash 工具，demo.py 演示两步文件任务。复用 qa/llm.py 的 base_url/model 环境变量约定，Ollama function calling 格式。附验收命令。只输出代码。`

**完成日期**：2026-09-18（mh/ 包诞生：loop.py ~60 行，真机 3 轮 2 调用全自主过验收）
**踩坑记录**：① qwen3.8 经 Ollama 返回 content 为空、推理在独立 thinking 字段——10 压缩要治理；② 接口预留 chat_fn/on_event/cwd 注入点，后续模块零侵入接入

---

### [x] 项目 5：工具契约层——注册、校验、错误回传自纠

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 |
| **核心知识点** | 工具注册表、JSON Schema 参数校验、错误信息回传设计、模型自纠循环 |
| **产出模块** | `harness/mh/tools.py` |
| **前置** | 项目 4 |
| **技术栈** | `jsonschema`（已装 ✅，qa/15 同款） |
| **验收标准** | 故意让模型首次调用传错参数类型：日志可见"校验失败→错误回传→第二次调用成功"完整两轮，任务最终完成；`mh/tools.py` 被项目 4 的 loop 无侵入替换后原 demo 仍通过 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「工具契约层」。请给我完整 Python 代码约 200 行：harness/mh/tools.py 提供 @tool 装饰器（函数→schema 自动生成）、jsonschema 参数校验、错误回传格式（让模型能读懂怎么改），并把项目 4 的 demo 切换到新注册表重跑。附验收命令（含"首次错参也能自纠"的日志断言）。只输出代码。`

**完成日期**：2026-09-18（故障注入对照真机过验收；loop 零改动换装）
**踩坑记录**：① 循环内包装工具时闭包晚绑定——所有 poisoned 共享最后一个 base，write_file 实际调到 count_lines，用工厂函数修复；② 27B 模型下原始 TypeError 与翻译后错误自愈表现相同（第 2 次独立验证"harness 价值∝故障密度"）；③ 质心 -8.8% 略超 ±5% 阈值（左右留白对称，视觉可接受）

---

### [x] 项目 6：执行安全沙箱——超时、截断、隔离

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 |
| **核心知识点** | 子进程执行、超时杀死、输出截断、工作目录隔离、危险模式前置拦截 |
| **产出模块** | `harness/mh/sandbox.py` |
| **前置** | 项目 5 |
| **验收标准** | ① 让 agent 跑 `while True` 死循环：3 秒被杀、harness 存活并继续下一轮 ② 输出超 8KB 被截断且模型收到"[输出已截断]"提示 ③ 所有命令 cwd 锁定在沙箱目录，断言沙箱外文件零改动 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「执行安全沙箱」。请给我完整 Python 代码约 180 行：harness/mh/sandbox.py 用 subprocess 实现带超时（默认 3s）、输出截断（8KB）、cwd 隔离的 bash 执行器，集成进工具契约层；附三个验收场景脚本（死循环/超长输出/越界写入探测）。macOS 兼容。只输出代码。`

**完成日期**：2026-09-18（三场景全绿：3.0s 处决无孤儿/8KB 截断有告知/越界零改动；--agent 真机过）
**踩坑记录**：① 真 bug：as_loop_entry 包装函数 **args 吞掉 cwd 形参签名，loop 的 cwd 注入静默失效，沙箱隔离整条链路断——前两篇实验全通过所以没暴露，隐式签名协议必须有测试钉死；② 词法守卫挡不住绝对路径写（诚实边界，归 07 权限门）；③ 大文件误写进 lab 目录（bug 现场证据），已清理

---

## 🗂️ 第三阶段：控制面——权限、Hook、预算（项目 7-9）

> **目标**：给 harness 装上"被允许做什么"的确定性边界——这是 harness 与裸 agentic 循环的分水岭

### [x] 项目 7：权限门——allow / ask / deny 三档 + HITL

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~220 |
| **核心知识点** | 权限规则引擎（glob 匹配）、HITL 中断、敏感操作审批、审计日志 |
| **产出模块** | `harness/mh/permissions.py` + `permissions.yaml` |
| **前置** | 项目 6 |
| **验收标准** | 规则文件三条（`rm*`→deny、`pip install*`→ask、`ls*`→allow）全命中：rm 被自动拒绝且上下文收到拒绝原因、pip install 挂起等 tty 输入 y/n、ls 直通；`audit.log` 三条记录各含规则名与时间戳 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「权限门」。请给我完整 Python 代码约 220 行：harness/mh/permissions.py 从 YAML 读 allow/ask/deny 规则（fnmatch 模式匹配命令），在工具执行前拦截：deny 自动拒绝并把原因回传模型、ask 暂停等终端 y/n、allow 直通；写 audit.log。附验收脚本一次演示三条规则。只输出代码。`

**完成日期**：2026-09-19（三档验收 + 真机 rm 拦截/改道/如实汇报，audit 10 条）
**踩坑记录**：① 黑名单可绕过：rm 被拒后模型立刻改用 python3 os.remove——解释器必须一并 deny，生产要白名单+容器；② 第一版无良性白名单时 default=deny 让模型空转 7 轮——规则集要成对设计（deny 危险 + allow 良性）；③ Ollama 服务再次挂掉（open -a Ollama 拉起恢复）

---

### [x] 项目 8：Hook 系统——pre/post 工具钩子与可阻断执行

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 |
| **核心知识点** | 生命周期钩子、hook 返回协议（放行/阻断+反馈注入）、关注点分离 |
| **产出模块** | `harness/mh/hooks.py` |
| **前置** | 项目 7 |
| **验收标准** | 写一个"禁止编辑 .env"的 pre-hook 后让 agent 改 .env：断言文件 mtime 未变、模型上下文出现 hook 反馈消息、agent 随后改用别的文件完成原任务；post-hook 演示一次"结果脱敏"（自动抹掉输出中的 token 字符串） |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「Hook 系统」。请给我完整 Python 代码约 200 行：harness/mh/hooks.py 支持 pre/post 工具钩子注册，pre-hook 可返回 {block: true, feedback: str} 阻断执行并把 feedback 注入模型上下文，post-hook 可改写工具结果。附 .env 保护 pre-hook 与输出脱敏 post-hook 两个验收场景。只输出代码。`

**完成日期**：2026-09-19（两场景+真机三断言全绿；.env 字节级未变）
**踩坑记录**：① 意外收获：post-hook 让模型"零知识"——真实密钥从未进上下文；② 断言里脱敏前缀字符数写错(保留 6 字符)导致假失败，验收断言也要对齐实现；③ 脱敏只换 token 保结构，post 改写必须保证模型仍可解析

---

### [x] 项目 9：预算与止损——token 计量、步数上限、优雅降级

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 |
| **核心知识点** | 用量计量、预算中断、HANDOFF 摘要（部分结果交接）、防死循环收敛 |
| **产出模块** | `harness/mh/budget.py` |
| **前置** | 项目 4 |
| **验收标准** | 把步数上限调成 5 跑一个 10 步任务：断言 harness 恰好在第 5 轮后停止、输出包含已完成部分与剩余工作的 HANDOFF 摘要（而非报错崩溃）；token 预算同理可触发 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「预算与止损」。请给我完整 Python 代码约 180 行：harness/mh/budget.py 统计每轮 token 用量与轮次，超限时不抛异常，而是向模型注入"预算即将耗尽"的系统提醒并在下一轮强制收尾，产出 HANDOFF 摘要（已完成/未完成/关键文件）。集成进主循环。附验收脚本。只输出代码。`

**完成日期**：2026-09-19（三组对照验收全绿；force 轮撤 tools + HANDOFF 三行）
**踩坑记录**：① 强模型批量执行：qwen3.8 两条 bash 干完 5 目录，预算自然不触发——演示口径改为低于自然轮次，16 评测台任务集须含串行依赖；② 中途 system 消息会被 qwen3.8 无视，force 指令须用对话尾部 user 角色；③ token 计量先用字符估算，精确计量归 16

---

## 🗂️ 第四阶段：上下文工程与记忆（项目 10-12）

> **目标**：让 harness 跑得久、摔不死、记得住——上下文工程三件套

### [x] 项目 10：上下文压缩 Compaction——阈值触发 + 摘要 + 工具结果治理

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~250 |
| **核心知识点** | context rot、阈值触发压缩、历史摘要、旧工具结果占位符替换 |
| **产出模块** | `harness/mh/compaction.py` |
| **前置** | 项目 4、9 |
| **验收标准** | 跑一个 ≥60 轮的长任务：断言每轮峰值上下文 token 稳定在阈值 ×1.2 以内；压缩发生后任务仍能引用早期关键事实（预设 3 个暗桩：文件名/数字/路径，脚本自动检查摘要中 ≥2 个存活） |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「上下文压缩」。请给我完整 Python 代码约 250 行：harness/mh/compaction.py 在上下文超过阈值时，把早期轮次压缩为结构化摘要（保留关键事实），旧工具结果替换为"[已截断, 原始 N 字符]"占位符；压缩事件本身作为系统消息告知模型。附 60 轮长任务验收脚本与暗桩检查。只输出代码。`

**完成日期**：2026-09-20（14 次压缩，三暗桩全存活，峰值≤阈值×1.12，loop 零改动）
**踩坑记录**：① 真 bug：qwen3.8 长任务过度思考，1200 token 全进 thinking 字段，content/tool_calls 双空——/no_think 提示词拦不住，Ollama 服务端 think:false 才可靠（已固化进 mh/llm.py）；② 断言设计错误：早期摘要不可能含尚未发生的暗桩，改为任务级存活检查；③ 摘要器调用也消耗成本，阈值不能太低

---

### [x] 项目 11：会话持久化与崩溃恢复——checkpoint / resume

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~220 |
| **核心知识点** | 会话快照、崩溃恢复、幂等重放、断点续跑 |
| **产出模块** | `harness/mh/session.py` |
| **前置** | 项目 10 |
| **⚠️ 风险** | 与 qa/31_checkpoint_resume 同主题——本版是**进阶**：恢复的不是问答记录而是**带工具状态的 agent 会话**（已执行的工具调用及其副作用要识别并跳过） |
| **验收标准** | 任务执行中途 `kill -9` 进程，`--resume` 重启后：断言已完成的文件写操作不重复执行（按 mtime+内容 hash 判断）、任务最终完成、恢复事件写入会话日志 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「会话持久化与崩溃恢复」。请给我完整 Python 代码约 220 行：harness/mh/session.py 每轮把完整 agent 状态（消息、已执行工具调用、文件副作用清单）原子写入 checkpoint.json，--resume 时加载并识别已完成的副作用跳过重放。附 kill -9 恢复验收脚本。只输出代码。`

**完成日期**：2026-09-20（13s kill -9 于 6/8 处，恢复后续跑 6 轮补齐，mtime 铁证，五断言全绿）
**踩坑记录**：① 悬空尾部：崩溃卡在 assistant(tool_calls) 与 tool 结果之间，恢复后模型输出全空——resume_messages 裁剪悬空调用；② wrapper 双坑复发：闭包晚绑定(05 同款)+cwd 静默丢失(06 同款)，包装器模式每次重写都要重测；③ 原子写 tmp+rename 是 kill 一致性的唯一保障

---

### [x] 项目 12：跨会话记忆——MEMORY.md 自动沉淀

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 |
| **核心知识点** | 长期记忆 vs 上下文、记忆写入时机、新会话注入、记忆污染防护 |
| **产出模块** | `harness/mh/memory.py` |
| **前置** | 项目 11 |
| **验收标准** | 会话 A 中用户声明一个偏好（如"测试一律用 pytest"）后，新起的会话 B 不做任何提示直接下任务：断言 B 的执行遵循该偏好（日志可见 MEMORY.md 注入事件）；反向用例：声明"忘掉该偏好"后 C 会话不再遵循 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「跨会话记忆」。请给我完整 Python 代码约 200 行：harness/mh/memory.py 在任务收尾时让模型判断是否值得沉淀事实到 MEMORY.md（带时间戳条目），新会话启动时自动注入文件内容为系统上下文；提供"忘掉某条"的删除入口。附跨会话验收脚本（A 写入→B 遵循→C 删除→D 不遵循）。只输出代码。`

**完成日期**：2026-09-20（真机四会话：A 沉淀/B 遵循/C 遗忘全绿，D 观察项无习惯残留）
**踩坑记录**：① 偏好选型要"异常可核查"——常见习惯(如 pytest)模型可能自发押中，B 通过也无法证明记忆生效；② 渲染器 forget→md 边反复触发 7px 微段 bug，删边用节点 tag 表意；③ walrus 表达式写进 f-string 的手滑

---

## 🗂️ 第五阶段：扩展机制（项目 13-15）

> **目标**：补齐工业 harness 的三个标志性扩展点：子代理、Skills、MCP

### [x] 项目 13：子代理调度——上下文隔离的任务分派

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~230 |
| **核心知识点** | 子代理 spawn、上下文隔离、结果摘要回收、任务描述作为"上下文防火墙" |
| **产出模块** | `harness/mh/subagent.py` |
| **前置** | 项目 10 |
| **验收标准** | 主代理把"统计本仓库 README 词频 top10"派给子代理：断言子代理 ≥5 轮的工具消息**不出现**在主代理上下文，主上下文只新增一条子代理摘要；两份上下文 trace 可 diff 验证 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「子代理调度」。请给我完整 Python 代码约 230 行：harness/mh/subagent.py 提供 spawn 子代理工具（入参=任务描述，返回=结果摘要），子代理拥有独立消息历史与自己的 loop 实例，结束后只把摘要回传主上下文。附主/子上下文 trace 输出与隔离断言脚本。只输出代码。`

**完成日期**：2026-09-20（真机：子代理 3 轮 3 调用，主上下文零泄漏，摘要数字与磁盘核对一致）
**踩坑记录**：① 隔离要从工具层开始：tools_factory 每次返回全新实例，共享注册表会串场；② MOCK 工厂没接 chat_fn 导致离线自检偷偷走真模型——注入点必须全线贯通；③ 断言③最初只查"有数字"，升级为磁盘核对后才是真验收

---

### [x] 项目 14：Skills 按需注入——触发匹配 + 懒加载

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 |
| **核心知识点** | SKILL.md frontmatter、触发词匹配、懒加载省 token、渐进式披露 |
| **产出模块** | `harness/mh/skills.py` + 2 个示例 skill |
| **前置** | 项目 9 |
| **验收标准** | 同一会话两次计量：未触发 skill 时上下文 token 中 skill 正文占比为 0，用户说出触发词后 skill 正文注入（差值 > 500 token 可测出）；写一个 skill 的 frontmatter 解析单测 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「Skills 按需注入」。请给我完整 Python 代码约 200 行：harness/mh/skills.py 扫描 skills/ 目录下 SKILL.md（YAML frontmatter 含 name/description/触发词），启动时只把名称+描述+触发词注入系统提示，命中触发词才加载正文；附 2 个示例 skill 与 token 差值验收脚本。只输出代码。`

**完成日期**：2026-09-20（菜单 145 字符常驻；加载前正文 0 字符，加载后 ≈512 est token；frontmatter 单测过）
**踩坑记录**：① 任务描述要禁住模型的手——"只依据规范作答"否则它会去调未注册的 run_bash 导致空轮；② menu:body ≈1:10 是懒加载经济性阈值，短知识直接写 system；③ 渲染器 micro-segment bug 第三次出现，统一用同高经点或删边处理

---

### [x] 项目 15：MCP 动态工具——在权限门下接入外部 server

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~220 |
| **核心知识点** | MCP 协议客户端、动态工具注册、外部工具过权限门、信任边界 |
| **产出模块** | `harness/mh/mcp_client.py` |
| **前置** | 项目 7、5 |
| **⚠️ 风险** | 与 qa/19-20 同主题——本版是**进阶**：MCP 工具不是"直接信"，而是必须先过项目 7 的 allow/ask/deny 权限门。复用 qa/19 的 MCP server 作夹具，无新增依赖（`mcp` 包已装 ✅） |
| **验收标准** | 连接本地 MCP server 后其工具动态出现在工具注册表：断言 ① 模型能发现并调用 ② 其中一个工具命中 ask 规则被拦截等审批 ③ 审批通过后调用成功、audit.log 有 MCP 工具记录 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「MCP 动态工具」。请给我完整 Python 代码约 220 行：harness/mh/mcp_client.py 启动本地 MCP server 子进程（复用 qa/19_mcp_server 的实现），list_tools 动态注册进 mh 工具表，每次调用前先过 permissions 门。附发现/拦截/放行三段式验收脚本。只输出代码。`

**完成日期**：2026-09-20（动态发现 3 工具；place_order ask 拦截→批准→订单 O001；audit 2 条）
**踩坑记录**：① anyio 上下文绑定创建任务——stdio_client 的 CM 跨协程持有即 Connection closed，须常驻协程持有会话生命周期；② 权限匹配串泛化为"command 或 工具名+参数"，否则 MCP 工具全被 default deny；③ 治理过严时模型主动暂停交易而非硬闯——行为红利再现

---

## 🗂️ 第六阶段：评测与总装（项目 16-18）

> **目标**：用数据证明自己的 harness 变强了，然后总装交付、闭环"区别"主线

### [x] 项目 16：Harness 评测台——固定任务集回归（Agent QA）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~250 |
| **核心知识点** | Agent QA、回归评测、解决率/成本/轮次三维指标、防"功能演进但效率倒退" |
| **产出模块** | `harness/eval/`（任务集 + 评分器 + run.sh） |
| **前置** | 项目 3、13 |
| **验收标准** | `bash harness/eval/run.sh v0.1 v1.0` 一键对两个 git tag/快照跑同一 10 任务集：输出 markdown 对比表（解决率/平均 token/平均轮次三行 × 两列），任一指标回退时表格中红色标注并 exit 1 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 项目「Harness 评测台」。请给我完整代码约 250 行：harness/eval/ 下 10 个可自动判分任务（文件操作/信息提取/多步组合）、评分器（解决率/token/轮次）、run.sh 接收两个版本快照路径跑批对比，输出 markdown 表且回退指标标红 exit 1。复用项目 3 的判分思路。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [x] 🏁 项目 17：终极总装——mini-harness CLI（类 Claude Code 终端）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~300（大部分为接线，模块已就绪） |
| **核心知识点** | REPL、斜杠命令、system-reminder 注入、全模块总装、端到端交付 |
| **产出模块** | `harness/mh/cli.py`（`python -m mh` 可启动） |
| **前置** | 项目 4-16 全部 |
| **验收标准** | 一个真实端到端任务全程自主完成："给 scripts/load_resources.sh 加一个 --dry-run 参数并自测"——断言过程日志中权限门、压缩、预算、记忆四模块各至少触发一次且有据可查；REPL 支持 /help /context /budget /resume 四个斜杠命令 |

**🤖 开始提示词**：
> `我要开始 Agent Harness 终极项目「mini-harness CLI」。请给我完整 Python 代码约 300 行：harness/mh/cli.py 用 readline 实现交互式 REPL，接线 mh 包全部模块（loop/tools/sandbox/permissions/hooks/budget/compaction/session/memory/subagent/skills/mcp），实现 /help /context /budget /resume 斜杠命令。保持模块接口不变。附端到端验收脚本。只输出代码。`

**完成日期**：2026-09-20（端到端五断言全绿：--dry-run 实现并自测过；rm/mv/清空三次拦截全留痕）
**踩坑记录**：① 空回复是总装层真实现象——CLI 加兜底重试（视作 harness 职责）；② 演示 profile 允许 python3 导致 rm-deny 可绕过（rm→mv→清空三连被拒后模型没再试解释器，算守规），治理权衡已写入 README；③ 证据线是总装调试唯一可信来源

---

### [ ] 项目 18：收尾对照实验——同 Harness 异模型，闭环"区别"主线

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~120（复用评测台） |
| **核心知识点** | 双向受控实验（变模型 vs 变 harness）、harness 即护城河、选型结论 |
| **产出模块** | `harness/18_model_vs_harness/REPORT.md`（最终对照表） |
| **前置** | 项目 16、17 |
| **⚠️ 风险** | 第二模型用本地 `qwen3:4b`（已实测在位 ✅，零成本）；如需 DeepSeek API 对照为**可选项**，无 Key 不影响验收 |
| **验收标准** | REPORT.md 含一张 2×2 对照表：① qwen3.8+裸 loop ② qwen3.8+完整 harness ③ qwen3:4b+裸 loop ④ qwen3:4b+完整 harness 的解决率/token 对比，并回答"换模型和换 harness 哪个影响大"给出自己的量化结论（与项目 3 数据互相印证） |

**🤖 开始提示词**：
> `我要开始 Agent Harness 收尾项目「同 Harness 异模型对照」。请给我完整 Python 代码约 120 行：复用 harness/eval/ 评测台，LLM_MODEL 环境变量切换 qwen3.8 / qwen3:4b 跑 2×2 对照（裸 loop vs 完整 harness），汇总进 REPORT.md 模板（表格+结论段）。附一键跑批命令。只输出代码。`

**完成日期**：2026-09-20（2×2 真机 40 跑批：3.8 双 10/10；4b 裸 1/10→full 5/10；REPORT.md 三结论）
**踩坑记录**：① importlib.reload 才能让 LLM_MODEL 切换单元格生效；② rows.json 断点续跑救了两次中断；③ 4b 烧 11 倍 token 只换 1/10——无效推理成本有数字了

---

## 📅 周计划

| 周次 | 内容 | 项目数 |
|:---|:---|:---:|
| **第 1 周** | 项目 1-4（失败基线 → 概念地图 → 对照实验 → 最小 loop） | 4 |
| **第 2 周** | 项目 5-9（工具契约、沙箱、权限门、Hook、预算——控制面成型） | 5 |
| **第 3 周** | 项目 10-14（压缩、恢复、记忆、子代理、Skills——长任务续航） | 5 |
| **第 4 周** | 项目 15-18（MCP、评测台、🏁 终极总装、收尾对照） | 4 |

## 🏆 里程碑

- [x] **完成项目 1-3** → 「区别」能讲带数据：手里有自己的失败实录与对照实验，不再是背概念
- [x] **完成项目 4-9** → 可信执行：Harness 从"能跑"到"敢跑"（权限/Hook/预算三道闸）
- [x] **完成项目 10-15** → 工业级扩展：跑得久（压缩）、摔不死（恢复）、记得住（记忆）、接得上（子代理/Skills/MCP）
- [x] **全部完成** → 拥有一个自研、可评测、类 Claude Code 的 harness，并用 2×2 对照实验给出"harness vs 模型谁重要"的最终答案

## 📝 每日日志

| 日期 | 项目 | 耗时 | 收获 | 踩坑 |
|:---|:---|:---:|:---|:---|
| | | | | |

## 🔧 环境配置

```bash
# 0. 已就绪（2026-09-17 实测）：
#    Python 3.13.9（anaconda）· Ollama: qwen3.8:latest(17GB) + qwen3:4b + nomic-embed-text
#    jsonschema / requests / mcp 已装 · qa/llm.py 共用客户端（环境变量切换 base_url/model）
# 1. 需安装：无（全清单零新增依赖；项目 18 的 DeepSeek API 对照为可选，无 Key 不影响验收）
# 2. 每项目开工前：
ollama list | grep qwen3.8        # 模型在位
python3 harness/NN_xxx/xxx.py --selftest 2>/dev/null || echo "本项目无 selftest, 直接跑验收脚本"
# 3. 离线跑法：MOCK=1（复用 qa 线约定）或 LLM_MODEL=qwen3:4b 降档提速
```

## ⚠️ 与已有清单的关系

| 已有清单 | 关系 |
|:---|:---|
| `docs/agent.md`（agents 线，30/30 ✅） | **互补视角**：agents 线 = LangChain framework 视角（设计时怎么组合出 agent 能力），本线 = harness 视角（运行时怎么管控 agent 行为）。正是 winder.ai 说的 "Frameworks compose agents, harnesses run them"。项目 5（工具契约）是 agents 线项目 15-18 的运行时进阶 |
| `docs/qa.md`（qa 线，31/31 ✅） | **互补+进阶**：qa 线解决"能讲清"，本线解决"能造出"。明确进阶项：项目 11 ≙ qa/31 进阶（恢复工具副作用而非问答记录）、项目 15 ≙ qa/19-20 进阶（MCP 工具过权限门）、项目 16 ≙ qa/27-28 评测的 harness 专项化；项目 8（Hook）两线均未覆盖，属全新 |
| 重叠规避 | agents/qa 线已完成的基础项（裸调 API、CoT/ReAct 推理、RAG、多 agent 协作框架对比）本清单**不再重复**，只在与 harness 交界处引用 |

## 📚 来源（2026-09-17 联网核实）

- [What is an AI Agent Harness? — Databricks](https://www.databricks.com/blog/ai-harness)：Agent = Model + Harness、八大组件、失败模式清单
- [What Is an Agent Harness? — Salesforce](https://www.salesforce.com/agentforce/ai-agents/agent-harness/)：agent 管什么 vs harness 管什么、权限五步流程、HITL interrupts
- [A Comparison of AI Agent Harnesses in 2026 — Winder.AI](https://winder.ai/ai-agent-harness-comparison/)：四层架构、九大 harness 对比、"Frameworks compose agents. Harnesses run them."、换 harness 比换模型影响大的实证
- [不应归咎于大语言模型：脚手架演进如何塑造编码智能体质量 — alphaXiv](https://www.alphaxiv.org/zh/abs/2607.03691v1)：固定模型变 scaffold 的 3500 次受控实验（解决率 ~30.5% 停滞、token 391K→668K 通胀）
- [Agent Harness in 2026: Hype Word, Industry Term, or Useful Technical Concept? — suedbroecker.net](https://suedbroecker.net/2026/08/30/agent-harness-in-2026-hype-word-industry-term-or-useful-technical-concept/)：VS Code/Microsoft/OpenAI/IBM/Google/Anthropic 六方术语趋同证据
- [3rd Generation of Agents: How 'Harness Engineering' Changed Games Again — InterSystems](https://community.intersystems.com/post/3rd-generation-agents-how-harness-engineering-changed-games-again)：三代 agent 演进、Claude Code 512k 行源码事件与五层架构、guides/sensors/ratchet 模式
- [awesome-ai-agent — GitHub](https://github.com/skyming/awesome-ai-agent)：Claude Code 源码拆解文章与复现版仓库索引（项目 2 的资料入口）
