# 09 · LangChain Agent：把循环交给框架

> 把手写循环全部交给 LangChain（主流的大模型应用开发框架）：`@tool`
> 装饰器自动生成工具 schema，`create_agent()`（底层 LangGraph）托管整个
> tool-calling 循环。读完本篇，你能分清框架到底替你做了什么、哪些事它
> 永远不会替你做——比如安全边界。

## Background

在没有框架之前，一个智能体的循环要自己写：用正则（regular expression，用模式串匹配并提取文本的工具）解析模型输出的自定义文本协议，手写 while 循环与终止判定，手动往消息列表里 append 每一步结果（这套做法见 06/07 实验）。

理解原理时它很有价值，工程上却意味着长期维护一堆与业务无关的模板代码——解析器、重试、状态管理，换一个模型还常常要改解析逻辑。

手写方案的痛点积累到一定程度，框架化成为必然：LangChain 把工具定义、协议解析、循环控制这些通用部分标准化，开发者只写工具本身。模型输出也从自定义文本协议升级为结构化的工具调用请求，不再需要正则。

但框架没有解决所有问题，甚至引入了新问题：模型兼容性差异、行为黑盒化，以及"工具能访问文件系统"这类安全问题——框架不会替你划安全边界。本篇的文件工具全部穿过一道自建校验，并用一次真实的路径穿越攻击验证它有效。

## What

本篇用 LangChain 实现同一个文件管理智能体。四个部件各司其职：

- **`create_agent`**：框架提供的智能体构造器，是"大脑"——底层由
  LangGraph（LangChain 生态的编排库，用状态机——即"按当前状态决定下一
  步"的程序结构——管理流程）托管整个 tool-calling 循环（模型发起工具调
  用、代码执行、结果回喂的循环）；
- **`ChatOllama`**：模型客户端，是"引擎"——Ollama 是在本地运行开源大模
  型的工具，`ChatOllama` 是 LangChain 连接它的客户端类；
- **`@tool` 装饰器**（加在函数定义上方、用来自动包装函数的 Python 语法）：
  把函数签名 + docstring（写在函数体首行的说明字符串）变成 schema——
  schema 即工具的机器可读描述（工具叫什么、接收什么参数），自动注册给
  模型；
- **`_safe_path` 校验**：文件工具的安全边界，每次文件操作前把活动范围
  钉死在 `workspace/` 目录内。

大脑与引擎的分工只到"决策与执行"为止——和真引擎不同的是，ChatOllama
这台"引擎"随时可能给出不可预测的输出，所以安全边界必须独立于模型行为
单独把守。

心智模型一句话：**框架托管循环，你只负责写工具——和划安全边界。**

## When to Use

这节回答：什么时候该把循环交给框架，什么时候手写更好。

典型场景：

- **从原型走向工程化时**：不想再维护解析器、重试、状态管理这些模板
  代码，希望升级模型或换模型时不用改解析逻辑；
- **工具数量多、迭代频繁时**：新工具用 `@tool` 一行注册，签名和
  docstring 写好即可，不用手写工具描述；
- **要接入框架生态时**：消息状态管理、多家模型客户端、上层编排能力
  都是现成的。

何时不用：学习原理阶段，手写一遍（06/07 实验）的收益不可替代；需要完全
自定义终止条件、事件流时，框架抽象反而构成约束。

框架托管的代价（选型时要计入）：抽象泄漏（框架内部细节从接口缝隙里露出
来，不读内部源码就排查不了问题）时排查成本高——消息结构、模型兼容性
问题都藏在框架内部；定制终止条件或事件流必须顺着框架的扩展点走。

手写与框架的逐项对照：

| 维度 | 手写（06/07 实验） | LangChain（本篇） |
| :--- | :--- | :--- |
| 工具定义 | 手写函数 + 手写描述 | `@tool` 从签名/docstring 自动推断 schema |
| 协议解析 | 手写正则、兼容各种变体 | 框架解析结构化 tool_calls |
| 循环控制 | 手写 while + 终止判定 | LangGraph 状态机托管 |
| 消息状态 | 手动 append | 框架管 state |
| 可定制性 | 完全可控 | 受框架抽象约束 |

## Quick Start

前置条件：装有 Python 3 与 pip；本地已安装并启动 Ollama、拉取了模型
（默认为 qwen3 系列本地模型）。先装本篇仅有的两个依赖：

```bash
pip install langchain langchain-ollama      # 本篇的两个依赖
cd agents/09_langchain_agent
python langchain_agent.py --demo            # 离线：直接调用工具 + 攻击测试 + schema 打印
python langchain_agent.py "列出 workspace 目录，写一个 hello.txt 内容为 hi，再读回确认"
```

`--demo` 依次做八件事：写 `hello.txt` → 读回 → 写 `notes/plan.md` →
列目录 → 搜关键词 → 计算器。

随后**路径穿越攻击
`read_file("../../../etc/passwd")` 被拦截** → 打印 5 个工具的 JSON Schema
（JSON 格式的结构描述标准，即模型实际看到的东西）。

真实模式的诚实预期：Agent 自主完成"列目录 → 写文件 → 读回确认"，最后
打印任务结果与工具调用次数。模型的每一步选择在本地运行，速度受机器
性能影响；模型偶尔会改变执行顺序，属于正常现象。

上面看到的三个现象——攻击被拦截、schema 能打印、调用次数能统计——分别
对应 How It Works 的三块机制。

## How It Works

先看把部件接起来的完整链路，每段在做什么见行内注释：

```python
llm = ChatOllama(model=model_name, reasoning=False)   # 推理模型直出正文
agent = create_agent(model=llm, tools=[read_file, write_file, list_dir,
                                       search_files, calculator],
                     system_prompt="You are a file management assistant. ...")
result = agent.invoke({"messages": [{"role": "user", "content": question}]})
final = result["messages"][-1].content                # 最终答案
tool_msgs = [m for m in result["messages"] if getattr(m, "type", None) == "tool"]
print(f"Tool calls: {len(tool_msgs)}")                # 工具调用统计
```

`invoke` 之后发生了什么：`create_agent` 底层是 LangGraph 状态机——模型
节点与工具节点循环，消息列表就是状态。模型节点决定调用哪个工具，工具
节点执行后把结果以 tool 消息回填，直到某轮模型不再发起 tool_calls（模型
返回的结构化工具调用请求），循环判定终止。

真实模式末尾打印的工具调用次数，就是对消息列表里 tool 类型消息的计数。

**机制一：`@tool` 装饰器，docstring 即 schema。** 函数名变成工具名，类型
注解变成参数 schema，docstring 首行变成工具描述：

```python
@tool
def read_file(filepath: str) -> str:
    """Read the content of a file. Must be within the workspace directory."""
```

`--demo` 里用 `get_input_schema().model_json_schema()` 把模型实际看到的
JSON Schema 打印出来。模型选择工具的准确率直接取决于这些描述的写法——
描述写得含糊，模型就会选错工具或传错参数。

**机制二：`_safe_path`，文件操作的安全边界。** 两步：先用 `realpath` 把
路径归一化（解析掉 `../` 和符号链接——指向另一个路径的"快捷方式"），
再做前缀校验：

```python
filepath = os.path.realpath(filepath)          # 解析 ../ 和符号链接
if not filepath.startswith(allowed + os.sep):  # 前缀校验
    return "ERROR: Path ... outside allowed directory"
```

`--demo` 第 7 件事发起的路径穿越攻击（用 `../../` 逐级跳出限定目录、
访问任意系统文件的经典手法），正是在 `realpath` 归一化之后现出原形、被
前缀校验拦下。不归一化的话，`workspace/../../../etc/passwd` 的字符串
前缀看起来合法，检查形同虚设。

## Pitfalls & Q&A

踩坑清单，每条按"现象 → 原因 → 解法"：

- **现象：最终回复为空字符串（本篇修复的真实 bug）。** 原因：qwen3.8 默认
  开启 thinking（模型先在内部思考通道输出推理过程），整段回复可能耗在
  thinking 通道，最后一条 AIMessage（框架里代表模型回复的消息对象）的
  `content` 为空。

  解法：`ChatOllama(model=..., reasoning=False)` 关掉思考直出正文；另留兜底——最终消息为空时回退到最后一条非空消息。
- **现象：想传 `reasoning=False` 却报错或无效。** 原因：
  `create_agent(model="ollama:...")` 的字符串写法会走 `init_chat_model`
  （框架按字符串构造模型客户端的辅助函数），它接收不了这个参数。解法：
  自己构造 `ChatOllama` 实例再传入。
- **现象：模型给出工作区外的路径也能读到文件。** 原因：校验逻辑没放在
  工具内部、或校验失败时抛了异常。解法：校验在每个工具内部强制执行
  （不信任模型传参）；失败时返回错误字符串而不是抛异常，让模型有机会
  换路径重试。
- **现象：模型频繁选错工具。** 原因：docstring 写成了实现注释。解法：
  docstring 是给模型看的，写"做什么 + 约束"。
- **现象：并行工具调用等特性行为与预期不符。** 原因：本地 Ollama 不支持
  部分高级特性。解法：了解本地与云端模型的行为差异，关键功能做兼容
  处理。

**Q: 给 Agent 文件工具时，最重要的安全措施是什么？**

目录沙箱（把活动范围限制在指定目录）+ `realpath` 归一化后的前缀校验，
且校验在每个工具内部强制执行；生产环境再加容器级隔离（用 Docker 一类
的容器技术把进程关在独立文件系统与权限空间里运行）。
