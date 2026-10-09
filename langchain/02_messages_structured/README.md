# 02 · 消息体系、提示模板与结构化输出：让模型按 schema 说话

> 大模型输出的是纯文本，而程序需要的是字段与类型明确的"数据对象"。本篇把文本到对象的路径拆成三步：用消息与模板组织输入、用 Pydantic（Python 数据校验库）声明想要的 schema（字段与类型的数据结构声明）、解析失败时把错误回喂模型重试。
> 实验离线部分用假模型构造"先输出坏 JSON、再输出好 JSON"，验证重试机制；真机部分用 `with_structured_output`（LangChain——大模型应用开发框架——的结构化输出快捷方法：传入 Pydantic 类，直接返回校验过的对象）从中文句子中抽取人物对象。
> 读完你能为任何抽取/分类任务写出"可校验、可重试"的输出管线。

## Background

让模型返回结构化数据的最早做法是"叮嘱 + 手动解析"：提示词里写"请输出 JSON"，拿到回复后用 `json.loads` 解析、再逐个字段检查。模型偶尔加一句"好的，以下是 JSON："，`json.loads` 直接抛异常；字段类型错了也没人拦。

另一种做法是自定义文本协议（比如让模型输出 `姓名: 张三` 再按冒号切分），格式解释成本更高，模型一旦自由发挥，解析器全崩。两种做法的共同问题是：**校验不在管线里，而在人脑里**。

随后框架把这件事标准化：消息有了明确的角色类型，模板负责拼装消息，解析器负责把输出映射到声明好的 schema，失败可以编程处理。本篇的实验就是这套标准的三个部件。

## What

结构化输出是一条"文本进、校验过的对象出"的管线：提示模板负责给模型塞格式说明，模型生成文本，解析器（把文本映射为数据结构、失败时抛错的组件）按 schema 校验。

可以把 schema 想象成收货单——仓库（模型）发什么货不管，收货单（Pydantic 模型）规定必须有哪些字段、什么类型，对不上就拒收。但和收货单不同的是：拒收不是终点，管线可以把"哪里对不上"写回给模型，让它重发一次。

三个部件的分工：

| 部件 | 角色 | 实验中的体现 |
|:--|:--|:--|
| 消息类型 | 区分发言者：`SystemMessage`（规则）、`HumanMessage`（用户）、`AIMessage`（模型） | 打印出的消息序列 |
| 提示模板 | 把变量与示例拼成消息列表 | `MessagesPlaceholder`（模板里预留的插槽，运行时填入一段消息列表）注入 few-shot（先给模型看几个示例再提问） |
| 解析器 | 文本 → 对象，失败抛 `OutputParserException`（解析器专用异常类，供程序捕获处理） | `PydanticOutputParser`（按指定 Pydantic 类解析文本的解析器）返回 Pydantic 对象，失败可捕获 |

## When to Use

典型场景：

1. 信息抽取：从简历、工单、邮件里抽出姓名、日期、金额等固定字段。
2. 分类路由：把用户问题分类为几类之一，下游按类别分派处理。
3. 多步管线的接口：上一步的输出是下一步的输入时，结构化对象比自由文本可靠。

何时不用：回答本身就是给人读的自然语言（如文章摘要），套 schema 只会限制表达；字段完全固定的简单场景，正则匹配更便宜。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
|:--|:--|:--|
| 正则 / 字符串切分 | 零依赖，但模型一变措辞就失效 | 输出格式极其固定且可控 |
| 提示词 + `json.loads` | 无校验，坏输出直接崩 | 一次性脚本 |
| 解析器管线（本篇） | 校验、报错、可重试 | 需要稳定性的生产路径 |

## Quick Start

前置条件：依赖已装在仓库根 `.venv`（版本清单见 [docs/langchain.md](../../docs/langchain.md) 的「环境配置」节）。

真机模式需要本机 Ollama（在本地运行大语言模型的服务）已启动且已拉取 `qwen3.8:latest`。

```bash
cd langchain/02_messages_structured
source ../../.venv/bin/activate         # 依赖装在仓库根 .venv；也可直接用 ../../.venv/bin/python
python3 messages_structured.py          # 真机：A/B 离线 + C 调模型
python3 messages_structured.py --demo   # 全程离线（假模型）
```

真实输出（节选：省略全部分隔线）：

```text
[02] 消息体系、提示模板与结构化输出
模式: 真机（qwen3.8:latest）

[A] 消息体系与 MessagesPlaceholder（离线）
  不带示例的消息序列：
    SystemMessage  你是工单分诊员，把问题分类为 代码/数学/通用 之一，只输出分类词。
    HumanMessage   这段代码怎么优化？
  ✅ 无示例时 = [System, Human]
  注入 2 组示例后共 6 条消息：
    SystemMessage  你是工单分诊员，把问题分类为 代码/数学/通用 之一，只输出分类词。
    HumanMessage   循环里查数据库是不是有问题？
    AIMessage      代码
    HumanMessage   1+1 等于几？
    AIMessage      数学
    HumanMessage   这段代码怎么优化？
  ✅ 示例按 Human/AI 成对插入到占位符位置

[B] 坏输出重试：解析失败 → 错误回喂 → 再解析（离线）
  第 1 次解析失败异常: OutputParserException
  第 2 次得到: name='张三' age=30 city='杭州'
  ✅ 坏输出抛出 OutputParserException 并被捕获
  ✅ 回喂错误后第 2 次解析成功
  ✅ 连续坏输出 3 次后放弃 — attempts=3

[C] 真机：结构化输出与 few-shot 风格
  with_structured_output -> name='李雷' age=28 city='杭州'（尝试 1 次）
  ✅ 真机返回严格 Pydantic 对象 — name=李雷, age=28, city=杭州
  正式风格: 该方案存在明显缺陷，难以满足当前需求。
  活泼风格: 这方案恐怕不太行得通。
  ✅ 两种 few-shot 风格产出不同结果

验收: 7/7 通过 ✅
```

诚实预期：`[B]` 段的重试是离线构造的确定性场景（假模型先坏后好），不依赖网络，也不受模型波动影响。真机段 `[C]` 耗时约 5-10 秒（模型已在内存时）。

Ollama 未启动时真机部分跳过（退出码 2）并提示改用 `--demo`；Ollama 已启动但未拉取模型时会报 `model '...' not found`，先执行 `ollama pull qwen3.8:latest`。

## How It Works

### 消息序列与占位符

`ChatPromptTemplate.from_messages` 收到的是"配方"而不是字符串：`("system", ...)` 与 `("human", "{question}")` 分别声明角色。

`MessagesPlaceholder("examples", optional=True)` 则是示例列表的插槽，`optional=True` 表示插槽缺省时模板照常工作。

调 `invoke` 时，模板做两件事：把变量填进字符串，把示例列表展开成真正的 `HumanMessage`/`AIMessage` 序列。

输出里"注入 2 组示例后共 6 条消息"就是证据：1 条 system + 4 条示例 + 1 条当前问题。

### 解析、校验与回炉重试

重试管线的形状是"解析失败不抛弃、把错误写回对话再试一次"，结构如下图：

![结构化输出管线：解析失败回炉重试](images/messages.workflow.svg)

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/langchain/02_messages_structured/images/messages.workflow.html)
> （或本地打开 [`images/messages.workflow.html`](images/messages.workflow.html)）。

`invoke_with_retry` 的三步：调结构化链；捕获 `OutputParserException`（解析器对坏输出抛出的专用异常）；把异常摘要作为新的 `HumanMessage` 追加到对话里，再调一次。

重试有次数上限（实验里 3 次），到达上限抛 `RetryExhausted` 并携带每次的错误——这防止坏输出陷入死循环。

### 真机的 with_structured_output

真机段不用手写"调用 + 解析"两段代码，而是 `llm.with_structured_output(Person)`：框架把格式说明拼进请求、把返回文本直接解析成 `Person` 实例。它是 LangChain 提供的快捷封装，内部仍是"提示 + 解析"同一条管线。

`get_format_instructions()` 生成的说明文本被放进 system 消息（见脚本），输出里"尝试 1 次"说明这次模型一次就给出了合法 JSON——真实模型在简单 schema 上通常一次成功，重试机制是兜底而非常态。

## Pitfalls & Q&A

### 踩坑清单

1. **两种解析器的返回值不同**。现象：`JsonOutputParser(pydantic_object=Person).parse(...)` 返回 `dict`，取 `person.name` 报 `AttributeError`。原因：该解析器只保证"是 JSON 且键匹配"，不构造对象。解法：需要 Pydantic 实例时用 `PydanticOutputParser`，脚本最初写错后已更换。
2. **推理模型的思考过程吃光输出预算**。现象：真机段返回空文本。原因：qwen3 系列默认把推理写在独立通道，而推理内容同样按 token（模型处理文本的最小单位，单次生成长度上限也按它计算）计数，输出预算因此被消耗。解法：`reasoning=False`（脚本已内置）。
3. **重试不加次数上限会死循环**。现象：坏输出持续时脚本永远不结束。原因：模型可能反复给出同类错误。解法：`max_attempts=3` 后抛 `RetryExhausted`，实验里 `[B]` 段专门验证了这条路径。

### 深入问答

**Q：为什么让模型输出 JSON，而不是直接输出 Python 对象？**

模型与程序之间只有文本通道，不存在"直接传对象"。JSON 的优势是结构明确、几乎所有模型都见过大量示例、解析器生态成熟。让模型写 Python 字面量也有项目这么做（如 Literal eval），但安全与稳定性都不如 JSON。

**Q：`with_structured_output` 和工具调用（function calling）是什么关系？**

不少模型厂商支持让模型输出"工具调用请求"，其参数必须是合法 JSON——于是框架可借这条通道做结构化输出，比"提示词逼 JSON + 文本解析"更稳。`with_structured_output` 的实现按模型能力选择通道：支持工具调用的模型走工具通道，否则退回提示 + 解析。对调用者来说接口不变。

**Q：坏输出除了重试，还有什么处理策略？**

三类：预防——把 schema 精简、给 few-shot 正例；修复——把坏输出的具体问题写回（本篇做法），或让另一个模型只负责"把这段文本修成合法 JSON"；降级——重试失败后返回默认值或转人工，并留下错误日志。生产管线通常三类叠加。
