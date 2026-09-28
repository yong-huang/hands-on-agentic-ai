# 12 · 工具注册表：Registry 模式与开闭原则

> 用 Registry 模式（注册表模式）把工具定义收敛为一处：`@tool_def` 装饰器
> 从类型注解和 docstring 自动生成 schema，`ToolRegistry` 统一注册、发现、
> 分发，Agent 循环零改动。读完本篇，你能把"加一个工具"的成本降到
> 一个函数定义，并说出工具层为什么要永不抛异常。

## Background

在注册表模式之前，一个工具的信息通常写在三处：函数本体、给 API 的 schema 字典（工具说明书，见 11 实验）、以及提示词里的工具清单。加一个工具要把三处各改一遍，改函数签名却忘改 schema 是常态。

三处定义必然漂移（描述和实现对不上）：schema 说参数是整数、函数实际要字符串，模型按说明书填参就会失败，而排查者看到的两份"文档"各自都说自己是对的。更实际的后果是加工具太贵——工具数量是智能体生产力的重要维度，成本一高，愿意造的工具就少，能力上限随之被压低。

Registry 模式把工具的声明、描述、分发收敛到一个对象上，这是开闭原则（对扩展开放、对修改关闭的设计原则：加功能靠加代码，不改已有代码）在工具层的应用。工具数量因此不再是负担：加工具 = 加一个带注解的函数。

## What

ToolRegistry（工具注册表）是一种集中登记、查找、分发工具的结构。它的核心是 `ToolDefinition`——**工具的单一事实源**（single source of truth，唯一的权威定义处，其他一切从它派生）。

一个对象同时携带模型侧信息和本地实现，工具的 schema（机器可读的工具说明书：名字、参数与类型）与实现在物理上不可能漂移。下面这个 dataclass（`@dataclass`，Python 标准库的数据类语法，自动生成构造与比较方法）就是那个对象：

```python
@dataclass
class ToolDefinition:
    name: str                 # 工具名（模型可见）
    description: str          # docstring 第一行（模型可见）
    parameters: dict          # {参数名: JSON Schema 片段}
    handler: Callable         # 本地执行函数（模型不可见）
```

带注解的函数经 `@tool_def` 装饰器注册成注册表里的 `ToolDefinition`。注册表对外只开两个口：向上给模型 `get_tools_schema()`（生成工具清单），向内给 Agent 循环 `dispatch(name, args)`（按名字找到并执行对应 handler）。

可以把 Registry 想象成公司的电话总机：模型报工具名，总机转接到对应分机（handler）。但和总机不同的是，报错名字不会转错人——总机会把"可用分机列表"回给对方，让对方自己纠正。

心智模型一句话：**Registry 是工具的"电话总机"：模型报名字，总机转接。**

## When to Use

这节回答：工具多到什么程度值得引入注册表，什么规模还不必。

典型场景：

- **工具数量持续增长、增删频繁时**：新工具只需一个带注解的函数，不需要
  再同步维护 schema 字典和提示词清单；
- **多人协作开发工具时**：描述与实现绑定在同一个对象上，不会各改各的
  导致漂移；
- **同一批工具要喂给多个 Agent 复用时**：注册表是中立的一层，谁接入
  谁调用 `get_tools_schema()` 与 `dispatch()`。

何时不用：只有两三个固定工具的小脚本，手写字典更直接；工具需要跨进程、
跨语言共享时，本地注册表不适用，应走协议方案（见下表 MCP 行与
Pitfalls 的升级时机）。

与硬编码（写死在代码里）字典的逐项对比（原方案见 11 实验）：

| 操作 | 11 实验（硬编码字典） | 本篇（Registry） |
| :--- | :--- | :--- |
| 新增工具 | 改 3 处 | 加 1 个带注解的函数 |
| 修改描述 | 同步函数注释和 schema 两处 | 只改 docstring |
| Agent 循环 | 引用具体工具 dict | 只依赖 registry.dispatch |

## Quick Start

前置条件：本地装有 Python 3；`--demo` 为离线演示，不调用外部接口；真实模式需要本地 Ollama（本地运行开源大模型的工具）已启动且模型支持工具调用。

```bash
cd agents/12_tool_registry
python tool_registry.py --demo                  # 离线：注册/分发/容错/模拟选型
python tool_registry.py "上海天气怎么样？人口多少？"   # 真实调用本地 Ollama
```

`--demo` 依次做六件事：

1. 打印注册表签名清单（每个工具的名字与参数列表）；
2. 直接 dispatch 四个工具；
3. dispatch 不存在的工具展示容错（返回可用列表而非崩溃）；
4. 打印自动生成的 Ollama schema；
5. 模拟模型两问（"上海天气+人口"触发两个工具、"ReAct 是什么+2^10"触发 search+calculator）；
6. 总结 Registry 对比 11 实验的四条优势。

真实模式的诚实预期：模型读到注册表给的工具清单后自主选工具作答。若模型
不发起工具调用，先确认所用模型支持 tools 参数。第 3 件事的容错输出长什么
样、为什么这样设计，见 How It Works 的 dispatch 小节。

## How It Works

### `@tool_def` 装饰器：注解即 schema

装饰器（加在函数定义上方、用来自动包装函数的 Python 语法）从类型注解
（参数名后 `: str` 这类标注）生成参数 schema。

`TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}` 覆盖
绝大多数工具参数；复杂约束（enum 枚举取值 / pattern 正则模式）可以在
生成的 schema 上手动补。

装饰器在 import 时就完成注册——**模块加载即装配**：Python 执行到
`import` 语句的那一刻，下面这段代码就把函数登记进注册表，不需要任何
手工调用：

```python
@tool_def(registry)
def get_weather(city: str) -> str:
    """查询指定城市的天气"""
    ...

def tool_def(registry):
    def decorator(fn):
        params = {name: TYPE_MAP[tp] for name, tp in fn.__annotations__.items()}
        registry.register(ToolDefinition(fn.__name__, fn.__doc__.strip().splitlines()[0],
                                          params, fn))
        return fn
    return decorator
```

`--demo` 第 4 部分打印的 schema 与第 1 部分签名清单，都是这条注册链路的
产出：函数名进了 `name`，docstring 首行进了 `description`，类型注解进了
`parameters`。

### `dispatch`：统一入口与防御式执行

`get_tools_schema()` 把每个 `ToolDefinition` 转成 schema 喂给 API 的
tools 参数；`dispatch(name, arguments)` 是执行的唯一入口。

它是防御式的：未知工具返回可用列表（模型拿到列表会自纠）；handler 抛异常则返回错误
字符串。**工具层永不抛异常，错误以字符串形式进入对话**：

```python
class ToolRegistry:
    def get_tools_schema(self):
        return [t.to_schema() for t in self._tools.values()]   # 喂给 API tools 参数

    def dispatch(self, name, arguments):
        tool = self._tools.get(name)
        if not tool:
            return f"Unknown tool: {name}. Available: {list(self._tools)}"
        try:
            return tool.handler(**arguments)
        except Exception as e:
            return f"Tool '{name}' error: {e}"
```

dispatch 不抛异常的原因：工具层错误对模型是有效反馈——错误字符串回传
后，Agent 有机会换参数或换工具自纠；抛异常则中断整个循环，模型连补救
的机会都没有。你在 `--demo` 第 3 部分看到的"返回可用列表而非崩溃"，正是
这条设计决策的直接呈现。

## Pitfalls & Q&A

踩坑清单，每条按"现象 → 原因 → 解法"：

- **现象：可选参数在模型侧总被要求填写。** 原因：`to_schema()` 把
  `required` 设为全部参数键——简单但对可选参数不友好。解法：生产可用
  `typing.Optional` 区分必填与可选。
- **现象：想让另一个进程也用这批工具，发现做不到。** 原因：注册表是进程
  内单例（整个进程里只有一份的实例），生命周期不跨进程。解法：跨进程
  共享工具要走 MCP（Model Context Protocol，连接外部工具的开放协议）。
- **现象：引入 Registry 后计算器仍被执行了恶意表达式。** 原因：误以为
  注册表能挡安全问题——它解决的是组织问题，不是安全问题。解法：
  `calculator` 的正则白名单（`^[\d\s+\-*/.()^]+$`，只放行数字与运算符）
  依旧不可省。

**Q: 工具描述写不好会怎样？**

模型选错工具、填错参数。描述要写"做什么、什么时候用、参数含义"——它是
模型可见的唯一文档。

**Q: 什么时候该从本地 Registry 升级到 MCP？**

当工具需要跨语言/跨进程共享、独立部署或由第三方提供时——用协议级的
发现与调用替代进程内的字典查找，见 14 实验。
