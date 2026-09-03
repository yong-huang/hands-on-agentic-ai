"""
Function Calling 基础 — Ollama 原生 Function Calling

项目 06 用正则解析 "Action: xxx" 文本格式调用工具，模型需要学习特殊格式。
项目 09 用 LangChain 框架自动管理 tool calling。
本项目直接使用 Ollama 原生的 Function Calling 协议:
  - tools 参数: JSON Schema 描述工具（名称、描述、参数）
  - tool_calls 响应: 模型结构化输出要调用的工具和参数
  - role: "tool": 工具执行结果回传

核心优势:
  不需要正则解析，不需要特殊格式，模型原生理解工具调用
  参数类型安全（JSON Schema 约束）
  支持并行工具调用（一次返回多个 tool_calls）
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置 — 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
HEADERS = {"Content-Type": "application/json"}


# ============================================================
# 工具定义 — 函数 + JSON Schema
# ============================================================

def get_weather(city: str) -> str:
    """模拟天气查询工具。"""
    weather_db = {
        "beijing": "Sunny, 28C, humidity 45%",
        "shanghai": "Cloudy, 31C, humidity 72%",
        "shenzhen": "Rainy, 29C, humidity 85%",
        "tokyo": "Partly cloudy, 26C, humidity 60%",
        "new york": "Rainy, 22C, humidity 78%",
        "london": "Overcast, 18C, humidity 80%",
        "paris": "Sunny, 25C, humidity 55%",
    }
    city_lower = city.lower().strip()
    for k, v in weather_db.items():
        if k in city_lower or city_lower in k:
            return v
    return f"No weather data for '{city}'"


def get_population(city: str) -> str:
    """模拟人口查询工具。"""
    pop_db = {
        "beijing": "21.5 million",
        "shanghai": "24.9 million",
        "shenzhen": "17.6 million",
        "tokyo": "13.9 million",
        "new york": "8.3 million",
        "london": "8.9 million",
        "paris": "2.1 million",
    }
    city_lower = city.lower().strip()
    for k, v in pop_db.items():
        if k in city_lower or city_lower in k:
            return v
    return f"No population data for '{city}'"


# 工具注册表: name -> {fn, schema}
TOOLS = {
    "get_weather": {
        "fn": get_weather,
        "schema": {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "City name, e.g. Beijing, Tokyo",
                        }
                    },
                    "required": ["city"],
                },
            },
        },
    },
    "get_population": {
        "fn": get_population,
        "schema": {
            "type": "function",
            "function": {
                "name": "get_population",
                "description": "Get population of a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "City name, e.g. Beijing, Tokyo",
                        }
                    },
                    "required": ["city"],
                },
            },
        },
    },
}


# ============================================================
# Function Calling Agent Loop
# ============================================================

def call_ollama(messages: list, tools_schema: list = None) -> dict:
    """Call Ollama chat API with optional tools."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "options": {"temperature": 0.3, "num_predict": 512},
        "stream": False,
    }
    if tools_schema:
        payload["tools"] = tools_schema
    try:
        resp = __import__('requests').post(
            BASE_URL, headers=HEADERS, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def execute_tool_call(tc: dict) -> str:
    """Execute a single tool call from model response."""
    func_info = tc.get("function", {})
    name = func_info.get("name", "")
    arguments = func_info.get("arguments", {})
    tool_entry = TOOLS.get(name)
    if not tool_entry:
        return f"Unknown tool: {name}"
    try:
        result = tool_entry["fn"](**arguments)
        return result
    except Exception as e:
        return f"Tool error: {e}"


def run_agent(question: str, max_rounds: int = 5):
    """Run function calling agent loop."""
    print(f"\nUser: {question}\n")

    messages = [{"role": "user", "content": question}]
    tools_schema = [TOOLS[name]["schema"] for name in TOOLS]
    round_num = 0

    while round_num < max_rounds:
        round_num += 1
        print(f"--- Round {round_num} ---")

        resp = call_ollama(messages, tools_schema)
        if "error" in resp:
            print(f"API Error: {resp['error']}")
            return

        message = resp.get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")

        # No tool_calls -> final answer
        if not tool_calls:
            print(f"Agent: {content}")
            return

        # Execute each tool call
        messages.append(message)
        for tc in tool_calls:
            func_info = tc.get("function", {})
            name = func_info.get("name", "")
            args = func_info.get("arguments", {})
            print(f"  >> Tool call: {name}({args})")
            result = execute_tool_call(tc)
            print(f"  >> Result: {result}")
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": result,
            })

    print("Max rounds reached")


# ============================================================
# Demo 模式 — 无需 Ollama，模拟 tool_calls 流程
# ============================================================

def run_demo():
    """Simulate function calling flow without Ollama."""
    print("=" * 60)
    print("Function Calling -- Demo Mode (no Ollama)")
    print("=" * 60)

    # Show tool schemas (what gets sent to API)
    print("\n[1] Tool Schemas (sent in API request 'tools' field):")
    for name, entry in TOOLS.items():
        print(f"\n  {name}:")
        schema = json.dumps(entry["schema"]["function"], indent=4)
        for line in schema.split('\n'):
            print(f"    {line}")

    # Simulate single tool call
    print("\n" + "=" * 60)
    print("[2] Simulate: user asks about weather")
    print("=" * 60)

    question = "What's the weather in Beijing?"
    print(f"\n  User: {question}")

    # Simulated model response with tool_calls
    mock_response = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": {"city": "Beijing"},
                    },
                }
            ],
        }
    }

    message = mock_response["message"]
    tool_calls = message.get("tool_calls", [])
    print(f"  Model response: tool_calls={len(tool_calls)}")

    for tc in tool_calls:
        func_info = tc["function"]
        name = func_info["name"]
        args = func_info["arguments"]
        print(f"  >> Tool call: {name}({args})")
        result = execute_tool_call(tc)
        print(f"  >> Result: {result}")

    # Simulate model's final answer after tool result
    print(f"\n  Agent: Beijing is sunny with 28C and 45% humidity.")

    # Simulate parallel tool calls
    print("\n" + "=" * 60)
    print("[3] Simulate: parallel tool calls")
    print("=" * 60)

    question2 = "Compare weather and population of Shanghai and Tokyo."
    print(f"\n  User: {question2}")

    mock_parallel = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": {"city": "Shanghai"},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_population",
                        "arguments": {"city": "Shanghai"},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": {"city": "Tokyo"},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_population",
                        "arguments": {"city": "Tokyo"},
                    },
                },
            ],
        }
    }

    tool_calls = mock_parallel["message"]["tool_calls"]
    print(f"  Model response: tool_calls={len(tool_calls)} (parallel)")
    for tc in tool_calls:
        func_info = tc["function"]
        name = func_info["name"]
        args = func_info["arguments"]
        print(f"  >> Tool call: {name}({args})")
        result = execute_tool_call(tc)
        print(f"  >> Result: {result}")

    print(f"\n  Agent: Shanghai: Cloudy 31C, pop 24.9M. Tokyo: Partly cloudy 26C, pop 13.9M.")

    # Show message flow
    print("\n" + "=" * 60)
    print("[4] Message Flow (what API sees)")
    print("=" * 60)
    flow = [
        {"role": "user", "content": "What's the weather in Beijing?"},
        {"role": "assistant", "tool_calls": [{"type": "function", "function": {"name": "get_weather", "arguments": {"city": "Beijing"}}}]},
        {"role": "tool", "tool_name": "get_weather", "content": "Sunny, 28C, humidity 45%"},
        {"role": "assistant", "content": "Beijing is sunny with 28C."},
    ]
    for i, msg in enumerate(flow):
        role = msg["role"]
        if role == "user":
            preview = msg["content"][:50]
        elif role == "assistant" and "tool_calls" in msg:
            preview = f"tool_calls: {len(msg['tool_calls'])}"
        elif role == "tool":
            preview = f"[{msg['tool_name']}] {msg['content'][:40]}"
        else:
            preview = msg["content"][:50]
        print(f"  [{i}] {role:<12} {preview}")

    print(f"\n{'='*60}")
    print("Key difference from project 06 (ReAct text parsing):")
    print("  - No 'Thought:/Action:/Observation:' text format")
    print("  - Model outputs structured tool_calls (JSON)")
    print("  - Tool results sent as role='tool' messages")
    print("  - Framework-free: direct Ollama API, no LangChain")
    print(f"{'='*60}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
        if q:
            run_agent(q)
        else:
            print("Usage: python function_calling.py [--demo | 'question']")
            print("  --demo   : Simulate without Ollama")
            print("  question : Ask a question (needs Ollama running)")
