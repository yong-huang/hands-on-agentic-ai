# 09 · LangChain Agent：把循环交给框架

> 项目 06/07 手写了协议解析、循环控制、事件流。本篇把这些全部交给
> LangChain：`@tool` 装饰器自动生成工具 schema，`create_agent()`（底层
> LangGraph）托管整个 tool-calling 循环。删掉手写循环后你会更清楚框架
> 到底替你做了什么——以及哪些事它永远不会替你做（比如安全边界）。

## 1. 为什么需要它

手写循环的价值在理解原理，工程上却要维护解析器、重试、状态管理这些"-template
代码"。主流框架把这些标准化了：工具定义一处声明、循环托管、消息状态自动管。
**但框架也带来了新风险**：模型兼容性、黑盒行为、以及"工具能访问文件系统"
这类安全问题——框架不会替你划边界。本篇的文件工具全部穿过一道
`_safe_path` 安全校验，并用一次真实的路径穿越攻击验证它。

## 2. 总览：核心机制一图看懂

![LangChain Agent 组件栈](images/langchain_stack.architecture.svg)

**怎么看这张图**：`create_agent` 是大脑（LangGraph 状态机托管循环），
`ChatOllama` 是引擎；`@tool` 装饰器把函数签名+docstring 变成 schema 自动
注册；工具层的四个文件工具每次操作前都要过 `_safe_path` 校验，活动范围被
钉死在 `workspace/`。

心智模型一句话：**框架托管循环，你只负责写工具——和划安全边界。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/09_langchain_agent/images/langchain_stack.architecture.html)（或本地打开 [`images/langchain_stack.architecture.html`](images/langchain_stack.architecture.html)）。

## 3. 快速开始

```bash
pip install langchain langchain-ollama      # 本篇的两个依赖
cd agents/09_langchain_agent
python langchain_agent.py --demo            # 离线：直接调用工具 + 攻击测试 + schema 打印
python langchain_agent.py "列出 workspace 目录，写一个 hello.txt 内容为 hi，再读回确认"
```

`--demo` 依次做八件事：写 `hello.txt` → 读回 → 写 `notes/plan.md` → 列目录
→ 搜关键词 → 计算器 → **路径穿越攻击 `read_file("../../../etc/passwd")`
被拦截** → 打印 5 个工具的 JSON Schema（模型实际看到的东西）。

真实模式预期输出：Agent 自主完成"列目录→写文件→读回确认"，最后打印
`Agent: ✅ 1. ... 2. ... 3. ...` 与工具调用次数。

## 4. 核心概念

### 4.1 手写 vs 框架：逐项对照

| 维度 | 手写（项目 06/07） | LangChain（本篇） |
| :--- | :--- | :--- |
| 工具定义 | 手写函数 + 手写描述 | `@tool` 从签名/docstring 自动推断 schema |
| 协议解析 | 手写正则、兼容各种变体 | 框架解析结构化 tool_calls |
| 循环控制 | 手写 while + 终止判定 | LangGraph 状态机托管 |
| 消息状态 | 手动 append | 框架管 state |
| 可定制性 | 完全可控 | 受框架抽象约束 |

### 4.2 `@tool` 装饰器：docstring 即 schema

```python
@tool
def read_file(filepath: str) -> str:
    """Read the content of a file. Must be within the workspace directory."""
```

函数名→工具名、类型注解→参数 schema、docstring 首行→工具描述。`--demo`
里用 `get_input_schema().model_json_schema()` 把"模型看到的 JSON Schema"
打印出来——**模型的工具选择质量直接取决于这些描述的写法**。

### 4.3 `_safe_path`：Agent 文件操作的安全边界

```python
filepath = os.path.realpath(filepath)          # 解析 ../ 和符号链接
if not filepath.startswith(allowed + os.sep):  # 前缀校验
    return "ERROR: Path ... outside allowed directory"
```

`realpath` 归一化是关键——不解析 `../` 的话，`workspace/../../../etc/passwd`
的前缀检查形同虚设。`--demo` 里真实发起了一次攻击并展示拦截。**易错点**：
校验逻辑必须放在每个工具内部（而不是信任模型传参），且校验失败要返回错误
字符串（而不是抛异常），让模型有机会换路径重试。

### 4.4 推理模型的空回复坑（本篇修复的真实 bug）

qwen3.8 默认开启 thinking，最终回复可能整段耗在 thinking 通道，导致最后一条
AIMessage 的 `content` 为空。修复：`ChatOllama(model=..., reasoning=False)`
关掉思考直出正文；另留兜底——最终消息为空时回退到最后一条非空消息。

## 5. 代码关键部分

```python
llm = ChatOllama(model=model_name, reasoning=False)   # 见 4.4
agent = create_agent(model=llm, tools=[read_file, write_file, list_dir,
                                       search_files, calculator],
                     system_prompt="You are a file management assistant. ...")
result = agent.invoke({"messages": [{"role": "user", "content": question}]})
final = result["messages"][-1].content                # 最终答案
tool_msgs = [m for m in result["messages"] if getattr(m, "type", None) == "tool"]
print(f"Tool calls: {len(tool_msgs)}")                # 工具调用统计
```

坑清单：

- `create_agent(model="ollama:...")` 字符串写法会走 `init_chat_model`，
  传不了 `reasoning=False`，要自己构造 `ChatOllama` 实例；
- 工具 docstring 是给模型看的，写"做什么+约束"，别写成实现注释；
- 本地 Ollama 不支持部分高级特性（并行工具调用等），行为与云端模型有差异。

## 6. 文件结构

```
09_langchain_agent/
├── README.md                          # 本篇教程
├── langchain_agent.py                 # 主脚本（约 300 行）：5 个 @tool + create_agent
├── workspace/                         # 工具唯一允许读写的沙箱目录
└── images/
    ├── langchain_stack.architecture.json  # 图源：architecture 类型（组件+边界）
    ├── langchain_stack.architecture.html  # 交互版架构图
    └── langchain_stack.architecture.svg   # 双主题矢量图
```

## 7. 面试要点

- **Q: LangChain 的 create_agent 底层是什么？**
  A: LangGraph 状态机：模型节点 ↔ 工具节点循环，以 tool_calls 有无判定
  终止，消息列表即状态。
- **Q: `@tool` 装饰器做了什么？**
  A: 反射函数签名与 docstring，生成名称/描述/参数 JSON Schema，包装成
  结构化工具对象注册给 Agent。
- **Q: 给 Agent 文件工具时最重要的安全措施是什么？**
  A: 目录沙箱 + `realpath` 归一化的前缀校验，且校验在每个工具内部强制执行；
  生产再加容器级隔离。
- **Q: 框架托管循环的代价是什么？**
  A: 抽象泄漏时排查成本高（消息结构、模型兼容性）、定制终止条件/事件流
  要顺着框架扩展点走。
- **Q: 为什么最终答案可能是空字符串？**
  A: 推理模型把输出耗在 thinking 通道。解决：关闭思考直出（reasoning=False）
  或对最终消息做空值兜底。

## 8. 总结

框架接管了 schema 生成、协议解析与循环托管，你只写工具和安全边界——但
原理（项目 06/07）决定了你能否在框架行为不符预期时快速定位。下一篇回到
会话主题：给 Agent 加上跨重启的持久化能力。
