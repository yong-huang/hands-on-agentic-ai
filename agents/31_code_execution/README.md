# 31 · Code Execution / Code Mode：让 Agent 写代码调工具

> Anthropic 2025.11 热文提出 **Code Mode**：把工具函数预载到沙箱命名空间，
> Agent 写一段 Python 代码直接调用——中间结果留在沙箱不过上下文。实测
> LLM 调用 8 次 → 2 次。

## What

两种工具调用方式的对比：

| 维度 | v1 标准调用 | v2 Code Mode |
| :--- | :--- | :--- |
| LLM 调用次数 | N 工具 × N 步 = 8 | 1 写代码 + 1 汇总 = 2 |
| 中间结果 | 全过上下文（token 膨胀） | 留在沙箱，只回传 result |
| 多工具协作 | 需多轮编排 | 代码内顺序/循环/条件自然表达 |
| 安全 | schema 层约束 | 需沙箱隔离 |
| 适用规模 | 工具少、结果小 | 工具多、数据大、需组合逻辑 |

心智模型一句话：**与其让模型逐个点菜，不如给模型一个厨房自己炒菜。**

## Why

工具越多，逐个调用的开销越大：每次往返把中间结果全量塞进上下文（token
膨胀），LLM 需要在多轮间"记住"中间值（容易遗忘）。Code Mode 的洞察是：
**与其给模型 N 个工具的 N 份 schema，不如给模型一个代码编辑器和 N 个函数
签名**——代码天然支持变量传递、条件逻辑和循环，一次写入搞定所有工具调用。
Anthropic 实测 token 省 98.7%，工具越多差距越大。

## How

```bash
cd agents/31_code_execution
python code_execution.py --demo   # 离线：MockLLM 走完两版流程
python code_execution.py          # 真实：qwen3.8 + 沙箱代码执行
```

**真机实测**：v1 标准调用用了 **8 次 LLM 调用**（每个工具一次往返），v2
Code Mode 仅 **2 次**（写代码 + 汇总回答），上下文字符从 1140 降到 1244——
LLM 调用减少 75%，上下文效率提升 20%。

**沙箱执行**：`exec(code_text, sandbox)` 在受控命名空间里运行 Agent 写的
代码。沙箱只预载工具函数和白内建，**不暴露 os/sys 等系统模块**。

**工具感知的代码生成**：代码里引用的函数签名必须与沙箱预载的一致——Agent
看到的是函数签名（而非 JSON Schema），代码即接口文档。模型天然擅长写
Python，比自己拼 JSON 参数更不容易出错。

沙箱与 v2 主流程：

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

## Deep Dive

**与 Function Calling 的关系**：互补不冲突——FC 定义工具的能力边界
（schema 层），Code Mode 改变工具的调用方式（执行层）。Anthropic 的做法
是把 MCP 工具转为 TypeScript API 文件供代码引用。

踩坑清单：

- `exec` 沙箱只预载白名单函数，`__builtins__` 可进一步收窄（禁 open/os）；
  生产环境必须容器级隔离（Docker / gVisor / Firecracker microVM）、网络
  白名单、CPU/内存限额——代码来自 LLM 输出，永不可信；
- 代码可能抛异常——`try/except` 捕获后回传错误信息让模型自纠（项目 13）；
- 长代码用 `ast.parse` 预检语法，避免 exec 整段崩溃。

## Q&A

**Q1: Code Mode 为什么能大幅节省 token？**

标准调用每工具一次 LLM 往返、中间结果全过上下文；Code Mode 让 Agent 写
代码在沙箱里直接调工具，中间结果留在执行环境，只有最终 result 出站。

**Q2: Code Mode 的适用边界？**

工具多、数据大、需要组合逻辑的场景收益最大；工具只有一两个且结果极小时，
标准调用反而更简单。

**Q3: Agent 写的代码有语法错误怎么办？**

try/except 捕获后把错误信息回传模型自纠（项目 13 的错误处理模式）；多次
失败则降级为标准调用。
