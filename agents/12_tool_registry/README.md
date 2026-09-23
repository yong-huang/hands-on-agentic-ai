# 12 · 工具注册表：Registry 模式与开闭原则

> 用 Registry 模式把工具定义收敛为一处——`@tool_def` 装饰器从类型注解和
> docstring 自动生成 schema，`ToolRegistry` 统一注册、发现、分发，Agent
> 循环零改动。

## What

`ToolDefinition` 是工具的单一事实源——一个对象携带模型侧
（name/description/parameters）和本地侧（handler），**描述与实现物理上
不可能漂移**：

```python
@dataclass
class ToolDefinition:
    name: str                 # 工具名（模型可见）
    description: str          # docstring 第一行（模型可见）
    parameters: dict          # {参数名: JSON Schema 片段}
    handler: Callable         # 本地执行函数（模型不可见）
```

注册表区域里，`@tool_def` 装饰器把带注解的函数注册成 `ToolRegistry` 中的
`ToolDefinition`；注册表对外只开两个口——向上给模型 `get_tools_schema()`，
向内给 Agent 循环 `dispatch(name, args)` 执行对应 handler。

开闭原则的收益（对比项目 11 硬编码字典）：

| 操作 | 项目 11（硬编码字典） | 本篇（Registry） |
| :--- | :--- | :--- |
| 新增工具 | 改 3 处 | 加 1 个带注解的函数 |
| 修改描述 | 同步函数注释和 schema 两处 | 只改 docstring |
| Agent 循环 | 引用具体工具 dict | 只依赖 registry.dispatch |

心智模型一句话：**Registry 是工具的"电话总机"：模型报名字，总机转接。**

## Why

工具数量是 Agent 生产力的重要维度，而"加一个工具的成本"决定了你愿意造
多少工具。当工具定义散落在函数、schema 字典、prompt 清单三处时，它们
必然漂移（描述和实现对不上）。Registry 模式把工具的**声明、描述、分发**
收敛到一个对象上：加工具 = 加一个带注解的函数。

## How

```bash
cd agents/12_tool_registry
python tool_registry.py --demo                  # 离线：注册/分发/容错/模拟选型
python tool_registry.py "上海天气怎么样？人口多少？"   # 真实调用本地 Ollama
```

`--demo` 依次做六件事：①打印注册表签名清单；②直接 dispatch 四个工具；
③dispatch 不存在的工具展示容错（返回可用列表而非崩溃）；④打印自动生成
的 Ollama schema；⑤模拟模型两问（"上海天气+人口"触发两个工具、
"ReAct 是什么+2^10"触发 search+calculator）；⑥总结 Registry 对比项目 11
的四条优势。

**`@tool_def` 装饰器：注解即 schema**——`TYPE_MAP =
{str: "string", int: "integer", float: "number", bool: "boolean"}` 覆盖
绝大多数工具参数；复杂约束（enum/pattern）可以后续手动补。装饰器在
import 时就完成注册——**模块加载即装配**：

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

**dispatch：统一入口与防御式执行**——未知工具返回可用列表（模型拿到列表
会自纠）；handler 抛异常返回错误字符串。**工具层永不抛异常，错误以字符串
形式进入对话**：

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

## Deep Dive

**dispatch 为什么不抛异常**：工具层错误对模型是有效反馈——以字符串回传
让 Agent 有机会换参数/换工具自纠；抛异常会中断整个循环。

踩坑清单：

- `to_schema()` 把 `required` 设为全部参数键——简单但对可选参数不友好，
  生产可用 `typing.Optional` 区分；
- 注册表是进程内单例，跨进程共享工具要走 MCP（项目 14）；
- `calculator` 的正则白名单（`^[\d\s+\-*/.()^]+$`）依旧不可省——Registry
  解决的是组织问题，不是安全问题。

## Q&A

**Q1: 工具描述写不好会怎样？**

模型选错工具、填错参数。描述要写"做什么、什么时候用、参数含义"，它是
模型可见的唯一文档。

**Q2: 什么时候该从本地 Registry 升级到 MCP？**

当工具需要跨语言/跨进程共享、独立部署或由第三方提供时——协议级发现与
调用，见项目 14。
