# 31 · Code Execution / Code Mode：让 Agent 写代码调工具

> 项目 14 的 MCP 把工具暴露为独立的 JSON schema，每个工具一次 LLM 往返——
> 中间结果全过上下文。Anthropic 2025.11 热文提出 **Code Mode**：把工具函数
> 预载到沙箱命名空间，Agent 写一段 Python 代码直接调用——中间结果留在沙箱
> 不过上下文。实测 LLM 调用 8 次 → 2 次。

## 1. 为什么需要它

工具越多，逐个调用的开销越大：每次往返把中间结果全量塞进上下文（token 膨胀），
LLM 需要在多轮间"记住"中间值（容易遗忘）。Code Mode 的洞察是：**与其给模型
N 个工具的 N 份 schema，不如给模型一个代码编辑器和 N 个函数签名**——代码
天然支持变量传递、条件逻辑和循环，一次写入搞定所有工具调用。Anthropic 实测
token 省 98.7%，工具越多差距越大。

## 2. 总览：核心机制一图看懂

![Code Execution vs 标准工具调用](images/code_execution.workflow.svg)

**怎么看这张图**：上方是 v1 标准调用（每工具一次 LLM 往返，中间结果全过
上下文）；下方是 v2 Code Mode（Agent 写代码 → 沙箱 exec → 只回传最终结果）。
关键差别在执行层：沙箱把 N 次往返压缩为 1 次代码写入 + 1 次 exec。

心智模型一句话：**与其让模型逐个点菜，不如给模型一个厨房自己炒菜。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/31_code_execution/images/code_execution.workflow.html)（或本地打开 [`images/code_execution.workflow.html`](images/code_execution.workflow.html)）。

## 3. 快速开始

```bash
cd agents/31_code_execution
python code_execution.py --demo   # 离线：MockLLM 走完两版流程
python code_execution.py          # 真实：qwen3.8 + 沙箱代码执行
```

**真机实测**：v1 标准调用用了 **8 次 LLM 调用**（每个工具一次往返），v2
Code Mode 仅 **2 次**（写代码 + 汇总回答），上下文字符从 1140 降到 1244——
LLM 调用减少 75%，上下文效率提升 20%。

## 4. 核心概念

### 4.1 沙箱执行：安全与效率的平衡

`exec(code_text, sandbox)` 在受控命名空间里运行 Agent 写的代码。沙箱只
预载工具函数和白内建，**不暴露 os/sys 等系统模块**。生产环境应使用容器级
隔离（Docker / gVisor / Firecracker microVM），本篇的 dict 沙箱是教学最小版。

### 4.2 工具感知的代码生成

代码里引用的函数签名必须与沙箱预载的一致——Agent 看到的是函数签名（而非
JSON Schema），代码即接口文档。模型天然擅长写 Python，比自己拼 JSON 参数
更不容易出错。

### 4.3 对比逐个 JSON 调用

| 维度 | v1 标准调用 | v2 Code Mode |
| :--- | :--- | :--- |
| LLM 调用次数 | N 工具 × N 步 = 8 | 1 写代码 + 1 汇总 = 2 |
| 中间结果 | 全过上下文（token 膨胀） | 留在沙箱，只回传 result |
| 多工具协作 | 需多轮编排 | 代码内顺序/循环/条件自然表达 |
| 安全 | schema 层约束 | 需沙箱隔离 |
| 适用规模 | 工具少、结果小 | 工具多、数据大、需组合逻辑 |

## 5. 代码关键部分

```python
SANDBOX_PRELUDE = {"__builtins__": __builtins__,
                   "query_sales": query_sales,
                   "compute_revenue": compute_revenue}

def run_v2(task):
    raw = _chat([{"role": "system", "content": CODE_MODE_PROMPT},
                 {"role": "user", "content": task}])
    code_text = re.search(r"```(?:python)?\s*(.*?)```", raw, re.S).group(1)
    sandbox = dict(SANDBOX_PRELUDE)
    exec(code_text, sandbox)                    # 沙箱执行
    result = sandbox.get("result")              # 取回最终结果
```

坑清单：

- `exec` 沙箱只预载白名单函数，`__builtins__` 可进一步收窄（禁 open/os）；
- 代码可能抛异常——`try/except` 捕获后回传错误信息让模型自纠（项目 13）；
- 长代码用 `ast.parse` 预检语法，避免 exec 整段崩溃。

## 6. 文件结构

```
31_code_execution/
├── README.md                                    # 本篇教程
├── code_execution.py                            # 主脚本（约 200 行）：v1/v2 对照
└── images/
    ├── code_execution.workflow.json             # 图源
    ├── code_execution.workflow.html             # 交互版架构图
    └── code_execution.workflow.svg              # 双主题矢量图
```

## 7. 深入要点

- **Q: Code Mode 为什么能大幅节省 token？**
  A: 标准调用每工具一次 LLM 往返、中间结果全过上下文；Code Mode 让 Agent
  写代码在沙箱里直接调工具，中间结果留在执行环境，只有最终 result 出站。
- **Q: 沙箱隔离怎么做才够安全？**
  A: 教学用受控命名空间即可；生产必须容器隔离（Docker/gVisor）、网络白名单、
  CPU/内存限额——代码来自 LLM 输出，永不可信。
- **Q: Code Mode 的适用边界？**
  A: 工具多、数据大、需要组合逻辑的场景收益最大；工具只有一两个且结果极小
  时，标准调用反而更简单。
- **Q: Agent 写的代码有语法错误怎么办？**
  A: try/except 捕获后把错误信息回传模型自纠（项目 13 的错误处理模式）；
  多次失败则降级为标准调用。
- **Q: 与 Function Calling 的关系？**
  A: 互补不冲突——FC 定义工具的能力边界（schema 层），Code Mode 改变工具
  的调用方式（执行层）。Anthropic 的做法是把 MCP 工具转为 TypeScript API
  文件供代码引用。

## 8. 总结

Code Mode 的核心洞察是"给模型一个厨房而不是菜单"：代码天然支持变量传递、
条件逻辑和循环，一次写入搞定所有工具调用。这是 Anthropic 为解决 MCP 工具
规模膨胀提出的官方方案，也是 2026 年 Agent 架构的重要演进方向。下一篇进入
A2A 协议——让 Agent 之间也能互发现、互调用。
