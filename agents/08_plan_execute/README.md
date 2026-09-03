# 08 · Plan-and-Execute：先规划，后执行

> 项目 06/07 的 ReAct 是"边想边做"：每一步走完才靠 LLM 决定下一步，多步任务
> 就要过多次 LLM。本篇换一种主流架构 **Plan-and-Execute**：先让 LLM 一次性把
> 任务分解成 JSON 计划，再按计划逐步执行本地工具（{{N}} 引用解决步骤间数据
> 依赖），最后汇总所有结果作答。规划 1 次、汇总 1 次，中间零 LLM 调用。

## 1. 为什么需要它

ReAct 灵活但有两个成本：每步一次 LLM 调用（慢、贵），且"走一步看一步"缺少
全局视图——做了三步才发现路线不对。Plan-and-Execute 把"想"和"做"彻底分开：
规划阶段输出可审计、可并行、可修改的计划；执行阶段是确定性的本地循环。
LangGraph 生态的 plan-and-execute 模式、Claude Code 的 TodoWrite，都是这个
架构。理解它，你就拥有了第二种 Agent 架构的"手动挡"。

## 2. 总览：核心机制一图看懂

![Plan-and-Execute 工作流](images/plan_execute.workflow.svg)

**怎么看这张图**：规划层把用户任务变成 JSON 计划；执行层按计划逐步调用本地
工具，`{{N}}` 引用替换解决步骤间数据依赖（calculator 只取数值部分）；汇总层
把全部步骤结果交给 LLM 生成最终答案。

心智模型一句话：**规划 1 次看清全局，执行阶段零 LLM，汇总收口——想、做、
说三段分离。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/08_plan_execute/images/plan_execute.workflow.html)（或本地打开 [`images/plan_execute.workflow.html`](images/plan_execute.workflow.html)）。

## 3. 快速开始

```bash
cd agents/08_plan_execute
python plan_execute.py --demo                    # 离线：预置计划 + 真实本地工具
python plan_execute.py                           # 真实：默认任务（两城市人口求和）
python plan_execute.py "成都、深圳、广州三个城市的人口总和是多少？"
```

**真机实测**（qwen3.8 生成计划）：模型输出 4 步计划——三次 `get_population`
加一步 `calculator({{1}} + {{2}} + {{3}})`；执行阶段自动替换引用得到
`calculator(2126 + 1768 + 1881) -> 5775`，汇总器给出"三城人口总和 5775 万"。
换任何人口/计算类任务，计划形状都会跟着变——这就是"动态规划"的含义。

## 4. 核心概念

### 4.1 两种 Agent 架构的对照

| 维度 | ReAct（06/07） | Plan-and-Execute（本篇） |
| :--- | :--- | :--- |
| LLM 调用次数 | 每步 1 次（N 步 = N 次） | 规划 1 次 + 汇总 1 次 |
| 全局视图 | 无，走一步看一步 | 有，计划可审计、可修改 |
| 步骤间数据传递 | 靠对话历史 | `{{N}}` 显式引用 |
| 适合任务 | 探索型、信息不全 | 结构明确的多步计算/查询 |
| 失败恢复 | 下一步自然调整 | 需要重规划（replan）机制 |

### 4.2 JSON 计划：结构化输出（复用项目 03）

规划器的输出是一份 JSON：`{"steps": [{"tool", "input", "why"}]}`。提取用两级
回退（代码围栏优先 → 全文花括号兜底）。**计划即数据**——可以打印、存档、
人工修改后再执行，这是文本协议（06）做不到的。

### 4.3 `{{N}}` 引用：步骤间的数据依赖

真实任务里后一步要用前一步的结果。规划器在入参里写 `{{N}}` 引用第 N 步的
输出，执行器在调用工具前替换。替换是**工具感知**的：calculator 的引用只
提取数值（"2487万人" → "2487"），文本类工具原样替换。

**实测的坑**：替换若不做工具感知，`calculator("2487万人 + 2189万人")` 会被
白名单拒绝；初版兜底逻辑只提取了第一个数，`{{1}} + {{2}}` 被替换成
`"2487"`——第二个数静默丢失，靠汇总器 LLM 碰巧算对。**静默的数据丢失比
报错更危险**，修正后 calculator 拿到完整算式 `2487 + 2189 -> 4676`。

### 4.4 与 ReAct 的架构选型

结构明确的任务（"查三个城市的人口再求和"）用 Plan-and-Execute：便宜、快、
可审计。信息不全的探索任务（"这个 bug 是什么原因"）用 ReAct：每步根据观察
调整方向。生产系统常两者混合：先规划，执行中偏差过大时触发重规划（replan）。

## 5. 代码关键部分

```python
def substitute(arg, results, tool):
    """把入参里的 {{N}} 引用替换成第 N 步的输出。
    calculator 只接受纯数字: 引用替换时从步骤输出里提取数值部分。"""
    def fill(m):
        n = int(m.group(1))
        out = next((r["output"] for r in results if r["step"] == n), m.group(0))
        if tool == "calculator":
            num = re.search(r"-?\d+(?:\.\d+)?", str(out))
            return num.group(0) if num else str(out)
        return str(out)
    return re.sub(r"\{\{(\d+)\}\}", fill, str(arg))
```

坑清单：

- 规划器输出的 JSON 必须做两级回退提取（围栏 → 全文），模型偶尔会加说明文字；
- 汇总器兼任安全网：某步执行失败时，LLM 仍可基于其余结果作答并说明缺失；
- 计划的步数上限（2-4 步）写进规划提示词，防止模型生成无法执行的空泛计划。

## 6. 文件结构

```
08_plan_execute/
├── README.md                            # 本篇教程
├── plan_execute.py                      # 主脚本（约 200 行）：规划器 + 执行器 + 汇总器
└── images/
    ├── plan_execute.workflow.json       # 图源：workflow 类型（规划/执行/汇总三层）
    ├── plan_execute.workflow.html       # 交互版架构图
    └── plan_execute.workflow.svg        # 双主题矢量图
```

## 7. 面试要点

- **Q: Plan-and-Execute 与 ReAct 的本质区别是什么？**
  A: 推理与执行的耦合方式——ReAct 每步交错推理（N 步 N 次 LLM），P&E 先
  一次性规划再确定性执行（固定 2 次 LLM）；前者灵活，后者高效且可审计。
- **Q: 步骤间的数据依赖怎么解决？**
  A: 计划入参支持 `{{N}}` 引用前序步骤输出，执行器在调用前做工具感知的
  替换（数值类工具提取数字，文本类工具原样传递）。
- **Q: 什么任务适合 Plan-and-Execute？什么任务不适合？**
  A: 适合结构明确、可预先分解的多步任务；不适合信息不全、需要边探索边调整
  的任务——那种场景每步的观察会推翻计划，应使用 ReAct 或加 replan 机制。
- **Q: 计划生成的可靠性怎么保证？**
  A: 结构化输出（JSON）+ 两级回退提取 + 步数/工具白名单约束 + 解析失败
  时的降级路径（重试或提示用户）。
- **Q: 生产系统里这份计划还有什么用？**
  A: 人工审批的对象（危险计划先审后跑）、并行执行的依据（无依赖步骤并发）、
  进度展示与审计追溯的数据源。

## 8. 总结

把"想"和"做"分离：JSON 计划让任务全局可见，`{{N}}` 引用让步骤间数据流动，
确定性执行器让中间过程零 LLM 成本。与 06/07 的 ReAct 互为补充——至此你手上
有了两种手写 Agent 架构。下一篇把循环完全交给 LangChain 框架，体会"托管"的
代价与便利。
