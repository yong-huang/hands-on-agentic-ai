# 01 · LCEL 与 Runnable 协议：一条链，三种调用方式

> LCEL（LangChain Expression Language，用竖线把组件拼成链的声明式写法）是 LangChain（大模型应用开发框架）1.x 的地基：提示词、模型、解析器（把模型输出转成目标格式的组件）拼进链后，都实现同一套 Runnable 协议（定义组件如何被调用的统一接口）。
> 本篇写两条链验证这一点：一条纯计算链在 invoke（单次调用）/ batch（一批输入、保序返回多条输出）/ stream（流式分块返回）三种方式下结果一致；一条真机"分诊链"按关键词把问题路由到三条分支。
> 读完你能读懂任意 LCEL 链的结构，并用三种调用方式之一驱动它。

## Background

在 LCEL 之前，把"提示词 → 模型 → 解析结果"串起来的做法是嵌套函数调用：`parse(llm(prompt(x)))`。步骤超过三个后，代码变成括号套括号；想加批处理或流式输出，每个环节都要手写循环。

批处理和流式其实是通用能力：无论链里跑的是什么，调用方都想要"给一批输入、拿一批输出"和"边生成边返回 token（文本生成的最小单位）"。手写方案把这份通用逻辑复制进每个项目，步骤一换就得重写。

LCEL 把两件事固定下来：用 `|` 声明组件顺序，用统一的 Runnable 协议定义组件怎么被调用。通用能力随协议一起下发，链的作者只关心每一步算什么。

## What

LCEL 是一种"用管道语法组装链、用统一协议调用链"的写法：任何实现了 Runnable 协议的对象都能用 `|` 拼接，拼出的链自身也是 Runnable。

可以把 Runnable 想象成流水线上的工位——每道工序只关心"把进来的东西加工成出去的东西"，流水线可以任意加长。但和流水线不同的是：Runnable 还把整条线的三种运行方式（单件、批量、边做边交）一起定义好，而不是只定义加工本身。

协议只有三个核心方法：

| 方法 | 语义 | 返回值 |
|:--|:--|:--|
| `invoke(x)` | 单个输入 → 单个输出 | 输出对象 |
| `batch([x1, x2])` | 一批输入 → 保序的一批输出 | 列表 |
| `stream(x)` | 单个输入 → 输出分片迭代器（逐段拿结果） | 迭代器 |

拼链的四种常用原语：

| 原语 | 作用 | 例子 |
|:--|:--|:--|
| `RunnablePassthrough` | 原样透传输入 | 把字符串放进 `{"question": ...}` |
| `RunnableLambda` | 把普通函数变成 Runnable | `RunnableLambda(len)` |
| `RunnableParallel` | 同一输入并行喂多条子链 | 同时算字符数和词数 |
| `RunnableBranch` | 按顺序检查条件并选择子链 | 关键词命中哪条走哪条 |

## When to Use

典型场景：

1. 组合固定流程：问题先过提示词模板、再进模型、再解析成文本或结构化对象。
2. 一条逻辑多路复用：同一个链既要支持命令行单次调用，又要支持测试批量回归。
3. 流式界面：需要逐 token 显示模型输出时，链末端接 `stream` 即可，中间步骤不用改。

何时不用：单个 `llm.invoke()` 就能解决的问题不需要链；带循环、分支回退、需要保存中间状态的编排，应改用 LangGraph（把工作流编排成状态图的框架，见本系列后续实验）。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
|:--|:--|:--|
| 手写函数嵌套 | 无统一接口，批处理/流式自己写 | 只有一两步、一次性脚本 |
| LCEL（本篇） | 管道语法 + 三种调用方式统一 | 线性或轻度分支的组合 |
| LangGraph | 显式状态与图结构 | 循环、人工审批、断点恢复 |

## Quick Start

前置条件：依赖已装在仓库根 `.venv`（版本清单见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）。

真机模式需要本机 Ollama（在本地运行大语言模型的服务）已启动且已拉取 `qwen3.8:latest`——安装、`ollama serve` 启动与 `ollama pull qwen3.8:latest` 拉取命令见仓库根 README。

```bash
cd langchain/01_lcel
source ../../.venv/bin/activate    # 依赖装在仓库根 .venv；也可直接用 ../../.venv/bin/python
python3 lcel.py          # 真机：调用本地模型
python3 lcel.py --demo   # 离线：FakeListChatModel 演示同一条链
```

真实输出（节选：省略全部分隔线、`输入:` 与 `stream 拼接:` 两类过程行、分诊链前两条问答；6 条断言与结论行完整保留）：

```text
[01] LCEL 与 Runnable 协议
模式: 真机（qwen3.8:latest）

[A] 纯计算链：invoke / batch / stream 结果一致
  逐条 invoke : ["'hello lcel world' -> 16 字符 / 3 词", "'Runnable 协议' -> 11 字符 / 2 词"]
  batch       : ["'hello lcel world' -> 16 字符 / 3 词", "'Runnable 协议' -> 11 字符 / 2 词"]
  ✅ batch 结果 == 逐条 invoke（顺序一致）
  ✅ stream 拼接 == invoke

[B] 分诊链：RunnableBranch 按关键词路由
  Q: 用一句话介绍巴黎。
  A: 巴黎是法国的首都，以其浪漫的氛围、丰富的艺术遗产和标志性地标如埃菲尔铁塔而闻名于世。
  ✅ 三个问题命中三条分支 — 命中=['code', 'general', 'math']
  ✅ batch 返回三条非空答案
  ✅ LLM 链 batch == 逐条 invoke
  首 token 延迟 0.12s，流式 16 字符：21 + 21 = 42

42
  ✅ LLM 链 stream 拼接 == invoke

验收: 6/6 通过 ✅
```

诚实预期：脚本末尾 6 条断言全绿才算通过，任何一条失败退出码为 1。真机耗时取决于模型状态：模型已在内存时整轮约 10 秒；首次加载 17GB 模型约多花 30 秒。Ollama 未启动时真机部分跳过（退出码 2）并提示改用 `--demo`；`--demo` 不调模型，全程离线。

## How It Works

### 三种调用方式为什么结果一致

一致性来自协议的分工：每个 Runnable 只需实现 `invoke`，`batch` 和 `stream` 由基类按默认语义派生——`batch` 逐个映射输入并保持顺序，`stream` 把内部各步骤的分片依次交出。

所以链和单步组件共享同一套调用面：`chain.stream(q)` 与 `chat_model.stream(q)` 用起来没有区别，这是链能任意嵌套的前提。

### 分诊链的路由判定

分诊链把问题文本按关键词送到三条子链，结构如下图：

![分诊链结构：RunnableBranch 关键词路由到三条分支](images/lcel.architecture.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/01_lcel/images/lcel.architecture.html)
> （或本地打开 [`images/lcel.architecture.html`](images/lcel.architecture.html)）。

`RunnableBranch` 按顺序检查 `(条件, 子链)` 对，第一个命中的条件胜出，最后一项是不带条件的兜底链。三个条件都是纯字符串判断，不调模型，因此路由结果可预测、可断言。

路由命中的证据：脚本在每条分支开头放了一个 `RunnableLambda` 标记，把分支名写进 `ROUTE_LOG`。输出里 `命中=['code', 'general', 'math']` 一行就是三条分支各被走过一次的证据。

### 链的拼装过程

```python
branch = RunnableBranch(
    (is_code, chains["code"]),      # 命中「代码」→ 审查链
    (is_math, chains["math"]),      # 命中「计算」→ 计算链
    chains["general"],              # 兜底：通用链
)
chain = {"question": RunnablePassthrough()} | branch
```

`{"question": ...}` 这种字典是 LCEL 的并行语法糖：每个键对输入跑一条子链。本实验只放一个键，作用是给后续提示词模板提供 `{question}` 变量；`RunnablePassthrough` 把原始字符串原样放进 `question`。

## Pitfalls & Q&A

### 踩坑清单

1. **推理模型的思考过程吃光输出预算**。现象：真机下最终回答为空或只有半句。原因：qwen3 系列默认开启 thinking（先把推理写在独立通道），token 预算被推理消耗。解法：构造模型时加 `reasoning=False`，脚本已内置；若仍为空，提高 `num_predict`。
2. **`stream` 拼接与 `invoke` 对不上**。现象：两次调用结果不同。原因：两次调用是两个独立请求，温度（temperature，采样随机性参数；0 表示每次取概率最高的 token）非 0 时天然不同。解法：对比时保持同一输入与 `temperature=0`，脚本的断言按此设置。
3. **有状态假模型在多路调用下响应错位**。现象：`--demo` 时 `batch == 逐条 invoke` 或流式对比断言偶发失败。原因：`FakeListChatModel` 每次调用按序消耗响应列表，而 `batch` 默认并发提交，消耗顺序可能与输入顺序错位；流式与 `invoke` 两次调用也会各消耗一次。解法：demo 下给 batch 加 `max_concurrency=1`，流式对比换单响应假模型；脚本已处理，连跑 10 次全绿。

### 深入问答

**Q：`batch` 是并发调用模型吗？**

是。LangChain 的 `batch` 默认用线程池并发提交各输入，可用 `config={"max_concurrency": 1}` 限制。真正同时执行的数量受模型服务端限制：本机 Ollama 默认排队处理。批量结果顺序仍与输入一一对应。

**Q：为什么流式首 token 只要 0.12 秒，而 `invoke` 整段要几秒？**

流式不等整段生成完：第一个 token 产生后立即返回，所以首 token 延迟（TTFT，Time To First Token）远小于总时长。`invoke` 必须拿到完整响应才返回。对交互界面来说，TTFT 决定"感受上的速度"。

**Q：什么时候该从 LCEL 升级到 LangGraph？**

出现这三类需求时：链里需要循环（评审不过重写）、需要在中间暂停等人工确认、需要保存执行状态以便断点恢复。LCEL 表达线性管道和静态分支很清晰；控制流一旦带状态，图结构更合适。
