# 12 · 工具注册表：Registry 模式与开闭原则

> 项目 11 里新增一个工具要改三处：写函数、写 schema 字典、更新工具清单。
> 本篇用 Registry 模式收敛为一处——`@tool_def` 装饰器从类型注解和 docstring
> 自动生成 schema，`ToolRegistry` 统一注册、发现、分发，Agent 循环零改动。

## 1. 为什么需要它

工具数量是 Agent 生产力的重要维度，而"加一个工具的成本"决定了你愿意造多
多工具。当工具定义散落在函数、schema 字典、prompt 清单三处时，它们必然
漂移（描述和实现对不上）。Registry 模式把工具的**声明、描述、分发**收敛到
一个对象上：加工具 = 加一个带注解的函数，这就是开闭原则在 Agent 上的落地。

## 2. 总览：核心机制一图看懂

![工具注册表架构](images/registry.architecture.svg)

**怎么看这张图**：左边的注册表区域（虚线边界）里，`@tool_def` 装饰器把带
注解的函数注册成 `ToolRegistry` 中的 `ToolDefinition`；注册表对外只开两个
口——向上给模型 `get_tools_schema()`，向内给 Agent 循环 `dispatch(name, args)`
执行对应 handler。

心智模型一句话：**Registry 是工具的"电话总机"：模型报名字，总机转接。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/12_tool_registry/images/registry.architecture.html)（或本地打开 [`images/registry.architecture.html`](images/registry.architecture.html)）。

## 3. 快速开始

```bash
cd agents/12_tool_registry
python tool_registry.py --demo                  # 离线：注册/分发/容错/模拟选型
python tool_registry.py "上海天气怎么样？人口多少？"   # 真实调用本地 Ollama
```

`--demo` 依次做六件事：①打印注册表签名清单；②直接 dispatch 四个工具；
③dispatch 不存在的工具展示容错（返回可用列表而非崩溃）；④打印自动生成的
Ollama schema；⑤模拟模型两问（"上海天气+人口"触发两个工具、"ReAct 是什么
+2^10"触发 search+calculator）；⑥总结 Registry 对比项目 11 硬编码字典的
四条优势。

## 4. 核心概念

### 4.1 ToolDefinition：工具的单一事实源

```python
@dataclass
class ToolDefinition:
    name: str                 # 工具名（模型可见）
    description: str          # docstring 第一行（模型可见）
    parameters: dict          # {参数名: JSON Schema 片段}
    handler: Callable         # 本地执行函数（模型不可见）
```

一个对象携带模型侧（name/description/parameters）和本地侧（handler），
**描述与实现物理上不可能漂移**。

### 4.2 `@tool_def` 装饰器：注解即 schema

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

`TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}`
覆盖了绝大多数工具参数；复杂约束（enum/pattern）可以后续手动补。装饰器在
import 时就完成注册——**模块加载即装配**。

### 4.3 dispatch：统一入口与防御式执行

`dispatch(name, args)` 的两条防御规则：未知工具返回
`"Unknown tool: xxx. Available: [...]"`（模型拿到列表会自纠）；handler 抛
异常返回 `"Tool 'x' error: ..."`（错误也是信息）。**工具层永不抛异常，
错误以字符串形式进入对话**。

### 4.4 对比项目 11：开闭原则的收益

| 操作 | 项目 11（硬编码字典） | 本篇（Registry） |
| :--- | :--- | :--- |
| 新增工具 | 改 3 处 | 加 1 个带注解的函数 |
| 修改描述 | 同步函数注释和 schema 两处 | 只改 docstring |
| Agent 循环 | 引用具体工具 dict | 只依赖 registry.dispatch |

## 5. 代码关键部分

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

坑清单：

- `to_schema()` 把 `required` 设为全部参数键——简单但对可选参数不友好，
  生产可用 `typing.Optional` 区分；
- 注册表是进程内单例，跨进程共享工具要走 MCP（项目 14）；
- `calculator` 的正则白名单（`^[\d\s+\-*/.()^]+$`）依旧不可省——Registry
  解决的是组织问题，不是安全问题。

## 6. 文件结构

```
12_tool_registry/
├── README.md                        # 本篇教程
├── tool_registry.py                 # 主脚本（约 310 行）：ToolDefinition + Registry + 装饰器
└── images/
    ├── registry.architecture.json   # 图源：architecture 类型（组件+边界）
    ├── registry.architecture.html   # 交互版架构图
    └── registry.architecture.svg    # 双主题矢量图
```

## 7. 面试要点

- **Q: Registry 模式解决了 Agent 工具系统的什么问题？**
  A: 定义分散导致的漂移与高维护成本；把声明/描述/分发收敛到单一对象，
  新增工具只加一个函数（开闭原则）。
- **Q: 装饰器如何生成 JSON Schema？**
  A: 读 `__annotations__` 做类型映射、取 docstring 首行做描述，import 时
  注册——模块加载即完成装配。
- **Q: dispatch 为什么不抛异常？**
  A: 工具层错误对模型是有效反馈。以字符串回传让 Agent 有机会换参数/换
  工具自纠；抛异常会中断整个循环。
- **Q: 什么时候该从本地 Registry 升级到 MCP？**
  A: 当工具需要跨语言/跨进程共享、独立部署或由第三方提供时——协议级发现
  与调用，正是下一篇的主题。
- **Q: 工具描述写不好会怎样？**
  A: 模型选错工具、填错参数。描述要写"做什么、什么时候用、参数含义"，
  它是模型可见的唯一文档。

## 8. 总结

Registry 把工具系统从"改三处"变成"加一函数"，装饰器让 schema 永不漂移。
但 Registry 里的工具永远和 Agent 同生共死——下一篇把工具搬进独立进程，
用 MCP 协议实现真正的"即插即用"。
