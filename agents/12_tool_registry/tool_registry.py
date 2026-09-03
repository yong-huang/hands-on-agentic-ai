"""
多工具注册与调度 — 工具注册表（Registry）模式

项目 11 实现了 Function Calling 基础，但工具以字典硬编码，添加新工具需改多处代码。
本项目实现 Registry 模式:
  - ToolDefinition: 工具元数据（名称、描述、参数 Schema、处理函数）
  - ToolRegistry: 工具注册表（register / dispatch / list / get_schema）
  - 统一调度接口: dispatch(name, **kwargs) → 结果
  - Ollama Function Calling 集成: 自动将已注册工具转为 API tools 参数

核心概念:
- 开放注册: @tool_def 装饰器或 registry.register() 动态添加
- 类型分发: dispatch(name, **kwargs) 按名称路由到对应处理函数
- Schema 聚合: get_tools_schema() 生成 API 请求的 tools 参数
"""

import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
HEADERS = {"Content-Type": "application/json"}


# ============================================================
# ToolDefinition & ToolRegistry
# ============================================================

class ToolDefinition:
    """Single tool metadata + handler."""

    def __init__(self, name: str, description: str,
                 parameters: dict, handler: callable):
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON Schema properties
        self.handler = handler

    def execute(self, **kwargs) -> str:
        return self.handler(**kwargs)

    def to_schema(self) -> dict:
        """Convert to Ollama function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.parameters.keys()),
                },
            },
        }


class ToolRegistry:
    """Tool registry with register / dispatch / list."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, name: str, description: str,
                 parameters: dict, handler: callable) -> ToolDefinition:
        tool = ToolDefinition(name, description, parameters, handler)
        self._tools[name] = tool
        return tool

    def dispatch(self, name: str, **kwargs) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"Unknown tool: {name}. Available: {list(self._tools.keys())}"
        try:
            return tool.execute(**kwargs)
        except Exception as e:
            return f"Tool '{name}' error: {e}"

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def get_tools_schema(self) -> list[dict]:
        """All tool schemas for Ollama API 'tools' parameter."""
        return [t.to_schema() for t in self._tools.values()]

    def describe(self) -> str:
        lines = []
        for name, tool in self._tools.items():
            params = ", ".join(tool.parameters.keys())
            lines.append(f"  {name}({params}): {tool.description}")
        return f"Registry ({len(self._tools)} tools):\n" + "\n".join(lines)


def tool_def(registry: ToolRegistry):
    """Decorator: register a function as a tool."""
    def decorator(fn):
        params = fn.__annotations__.copy()
        # Remove return type if present
        params.pop("return", None)
        # Convert type annotations to JSON Schema type strings
        TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}
        json_params = {}
        for pname, ptype in params.items():
            json_params[pname] = {"type": TYPE_MAP.get(ptype, "string")}
        registry.register(
            name=fn.__name__,
            description=(fn.__doc__ or "").strip().split('\n')[0],
            parameters=json_params,
            handler=fn,
        )
        return fn
    return decorator


# ============================================================
# Build registry with multiple tools
# ============================================================

registry = ToolRegistry()


@tool_def(registry)
def calculator(expression: str) -> str:
    """Evaluate a math expression safely."""
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)\^]+$', expression):
        return f"Error: invalid expression '{expression}'"
    try:
        return str(eval(expression.replace('^', '**')))
    except Exception as e:
        return f"Error: {e}"


@tool_def(registry)
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    db = {
        "beijing": "Sunny, 28C, humidity 45%",
        "shanghai": "Cloudy, 31C, humidity 72%",
        "shenzhen": "Rainy, 29C, humidity 85%",
        "tokyo": "Partly cloudy, 26C, humidity 60%",
        "london": "Overcast, 18C, humidity 80%",
    }
    for k, v in db.items():
        if k in city.lower() or city.lower() in k:
            return v
    return f"No data for '{city}'"


@tool_def(registry)
def search(query: str) -> str:
    """Search knowledge base for a topic."""
    kb = {
        "python": "Python is a high-level language by Guido van Rossum, 1991.",
        "react": "ReAct: Reasoning + Acting, alternates LLM reasoning and tool use.",
        "agent": "AI Agent: autonomous system that perceives, reasons, and acts.",
        "rag": "RAG: Retrieval-Augmented Generation, retrieves docs before answering.",
        "langchain": "LangChain: framework for building LLM applications with tools.",
    }
    for k, v in kb.items():
        if k in query.lower() or query.lower() in k:
            return v
    return f"No results for '{query}'"


@tool_def(registry)
def lookup_population(city: str) -> str:
    """Get population of a city."""
    db = {
        "beijing": "21.5M", "shanghai": "24.9M", "shenzhen": "17.6M",
        "tokyo": "13.9M", "london": "8.9M", "paris": "2.1M",
    }
    for k, v in db.items():
        if k in city.lower() or city.lower() in k:
            return v
    return f"No data for '{city}'"


# ============================================================
# Agent loop (Ollama Function Calling + Registry dispatch)
# ============================================================

def call_ollama(messages: list) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": registry.get_tools_schema(),
        "options": {"temperature": 0.3, "num_predict": 1024},
        "stream": False,
    }
    try:
        resp = __import__('requests').post(
            BASE_URL, headers=HEADERS, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def run_agent(question: str, max_rounds: int = 5):
    print(f"\nUser: {question}\n")
    messages = [{"role": "user", "content": question}]

    for rnd in range(max_rounds):
        print(f"--- Round {rnd + 1} ---")
        resp = call_ollama(messages)
        if "error" in resp:
            print(f"API Error: {resp['error']}")
            return

        message = resp.get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")

        if not tool_calls:
            print(f"Agent: {content}")
            return

        messages.append(message)
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            print(f"  >> Dispatch: {name}({args})")
            result = registry.dispatch(name, **args)
            print(f"  >> Result: {result}")
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": result,
            })

    print("Max rounds reached")


# ============================================================
# Demo 模式 — 无需 Ollama
# ============================================================

def run_demo():
    print("=" * 60)
    print("Tool Registry -- Demo Mode (no Ollama)")
    print("=" * 60)

    # 1) Show registry
    print(f"\n{registry.describe()}")

    # 2) Direct dispatch
    print("\n--- Direct Dispatch ---")
    cases = [
        ("calculator", {"expression": "2 + 3 * 4"}),
        ("get_weather", {"city": "Beijing"}),
        ("search", {"query": "react"}),
        ("lookup_population", {"city": "Shanghai"}),
    ]
    for name, kwargs in cases:
        result = registry.dispatch(name, **kwargs)
        print(f"  dispatch('{name}', **{kwargs}) -> {result}")

    # 3) Unknown tool
    print("\n--- Unknown Tool ---")
    result = registry.dispatch("nonexistent", x=1)
    print(f"  dispatch('nonexistent', x=1) -> {result}")

    # 4) Auto-generated tool schemas
    print("\n--- Tool Schemas (for Ollama API) ---")
    for schema in registry.get_tools_schema():
        fn = schema["function"]
        print(f"\n  {fn['name']}: {fn['description']}")
        print(f"    params: {list(fn['parameters']['properties'].keys())}")

    # 5) Simulate multi-tool question (model selects tools)
    print("\n--- Simulate: Model Auto-Selects Tools ---")
    print("  User: What's the weather in Shanghai and its population?")
    print("  Model decides: get_weather + lookup_population")
    for name, kwargs in [("get_weather", {"city": "Shanghai"}),
                          ("lookup_population", {"city": "Shanghai"})]:
        result = registry.dispatch(name, **kwargs)
        print(f"    >> {name}({kwargs}) -> {result}")

    print("\n  User: What is ReAct and how to calculate 2^10?")
    print("  Model decides: search + calculator")
    for name, kwargs in [("search", {"query": "react"}),
                          ("calculator", {"expression": "2^10"})]:
        result = registry.dispatch(name, **kwargs)
        print(f"    >> {name}({kwargs}) -> {result}")

    print(f"\n{'='*60}")
    print("Registry pattern advantages over project 11 (hardcoded dict):")
    print("  - @tool_def decorator: add tools with zero boilerplate")
    print("  - Unified dispatch(): one interface, all tools")
    print("  - get_tools_schema(): auto-generates API payload")
    print("  - Open/closed: add tools without modifying registry code")
    print(f"{'='*60}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
        if q:
            run_agent(q)
        else:
            print("Usage: python tool_registry.py [--demo | 'question']")
