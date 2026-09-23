# 06 · ReAct 模式：Thought → Action → Observation 的推理循环

> 不依赖任何框架，用纯 `requests` + 正则解析，手写一个 ReAct（Reason + Act）
> 循环：模型先说 Thought（下一步打算），再说 Action（调哪个工具），本地
> 执行后把 Observation（结果）喂回去，直到模型给出最终答案。

## What

ReAct 在推理链里插入**行动**：模型的每一步思考都可以落地为一次真实的
工具调用，观察结果后再继续想。主循环：LLM 产出文本 → 正则解析出
Thought/Action/Answer → 是 Action 就执行工具，Observation 以 user 消息
回喂继续推理；是 Answer 就终止；解析失败走错误回喂重试。

三个出口的终止条件：

| 出口 | 条件 | 行为 |
| :--- | :--- | :--- |
| 正常终止 | 解析到 `Answer:` | 返回答案 |
| 步数上限 | `step >= max_steps(6)` | 强制停止，如实报告未完成 |
| 解析失败 | 格式不符 | 错误回喂重试（消耗步数） |

与 CoT 的对比：

| 维度 | CoT（项目 03） | ReAct（本篇） |
| :--- | :--- | :--- |
| 信息来源 | 模型参数内知识 | 参数知识 + 实时工具返回 |
| 输出 | 一次给全 | 每轮一段，循环多轮 |
| 准确性 | 算术/事实易幻觉 | 工具结果可信 |
| 延迟 | 单次调用 | 多次调用成倍增加 |

心智模型一句话：**ReAct = 用 prompt 约定一种文本协议，再用一个 while
循环解析并执行它。**

## Why

CoT（项目 03）只会"想"，不会"查"——模型的知识停留在训练截止日，算不
准 238*17，也不知道实时数据。ReAct 是 Agent 最核心的运行时模式，
LangChain/LangGraph 内部转的还是它。手写一遍，框架对你才不是魔法。

## How

```bash
cd agents/06_react_basic
python react.py                              # 默认问题：成都+深圳人口
python react.py --demo                       # 离线模式：内置回复，不需要 Ollama
```

脚本依次做四件事：

1. 注入 System Prompt（约定 Thought/Action/Answer 格式 + 工具清单）；
2. 模型输出 `Thought: ... Action: Calculator(2126+1768)`；
3. 正则解析 → 查 `TOOLS` 注册表 → 本地执行 → 打印 `Observation: 3894`；
4. Observation 回喂，直到模型输出 `Answer: 成都和深圳的人口加起来是
   3894 万`。

预期输出：逐步打印 `>> Thought / >> Action / >> Observation`，最多 6 步。

**文本协议**：System Prompt 约定三种行前缀——`Thought:`（推理）、
`Action: 工具名(入参)`（行动）、`Answer:`（终止）。解析器逐行扫描这三种
前缀，把自由文本变成可执行指令。**协议约定的可靠性完全取决于 prompt
工程与解析器的容错**。

**解析器：和真实模型搏斗**。`parse_react_output()` 要处理一地鸡毛：
qwen3.8 会先吐 `<think>...</think>`（要先剥掉）、把 `Thought` 写成
`Thinking Process`、冒号用全角、参数带 `key=value` 或 JSON。生产经验：
**解析器必须按"最常见变体清单"逐一兼容，并给解析失败留重试通道**——
把格式错误作为 user 消息回喂，模型下次会改。

**工具注册表与安全计算器**。`TOOLS` 是 `名字 → (函数, 描述)` 的字典；
描述会拼进 system prompt，模型据此选工具。`tool_calculator` 用正则白名单
`^[\d\s+\-*/.()^]+$` 校验后才 `eval`——**LLM 输出永远不可信**，字符串
直接进 `eval` 等于把 shell 交给模型。

工具执行与回喂的形态：

```python
def execute_tool(action, action_input):
    tool = TOOLS.get(action)
    if not tool:
        return f"Unknown tool: {action}. Available: {list(TOOLS)}"  # 错误也回喂
    return tool["fn"](action_input)

# Observation 回喂的形态（以 user 角色回到 messages）:
messages.append({"role": "user",
                 "content": f"Observation: {result}"})
```

## Deep Dive

**ReAct 本质是有限状态机**：Think → Act → Observe 循环，Answer 是唯一
"正常"出口，`max_steps` 是防死循环的保险丝。

踩坑清单：

- 解析出 Answer 后要直接 return，否则会走到"已达最大步数"分支打印误导
  信息；
- Observation 用 user 角色回喂是文本 ReAct 的惯例（API 没有"工具结果"
  角色，协议级的做法见项目 11 的 `role: "tool"`）；
- `temperature=0.3`：格式任务低温更稳，但要留一点弹性处理追问；
- 工具结果直接拼接进 prompt，超长结果要先截断（项目 13 专治这个）。

## Q&A

**Q1: ReAct 的核心思想是什么？**

让推理（Reason）与行动（Act）交替进行：模型生成 Thought 与 Action，
环境返回 Observation，循环直至答案。用外部行动修正推理，降低幻觉。

**Q2: 手写 ReAct 需要哪几个组件？**

协议 system prompt、输出解析器、工具注册表、执行器、循环控制（终止条件
+ 步数上限）。

**Q3: 模型输出格式不合法怎么办？**

把解析错误作为消息回喂让模型自纠；多次失败则终止并如实报告；长期方案
是换 Function Calling（协议级保证格式）。

**Q4: 为什么工具执行结果要用 user 角色回喂？**

文本 ReAct 建立在"对话"之上，API 的可选角色只有 user/assistant；用
user 角色携带 Observation 前缀即可让模型"看到"执行结果。

**Q5: max_steps 应该设多大？**

与任务复杂度和预算相关；关键是必须有上限并如实报告"未完成"，而不是
静默截断。
