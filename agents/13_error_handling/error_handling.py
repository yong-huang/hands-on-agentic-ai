"""
工具调用错误处理与重试 — 异常捕获、错误反馈、大结果卸载

项目 11-12 的工具执行没有错误处理：异常直接崩溃，大结果撑爆上下文。
本项目实现:
  - ToolError: 结构化错误类型（timeout / invalid / not_found / internal）
  - SafeExecutor: 包装工具调用，捕获异常后返回结构化错误信息
  - ResultManager: 大结果自动卸载为占位符（超过阈值替换为 <file:xxx>）
  - 重试机制: 可重试错误自动重试，不可重试错误直接反馈给模型

核心概念:
- 优雅降级: 工具失败后，模型获得清晰错误信息，可以调整策略
- 占位符替换: 大结果（>MAX_RESULT_SIZE）写入临时文件，替换为引用标记
- 重试策略: timeout 等暂时性错误自动重试，invalid 等永久性错误不重试
"""

import os
import re
import sys
import tempfile
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
HEADERS = {"Content-Type": "application/json"}

MAX_RESULT_SIZE = 200  # Demo 用小阈值；生产环境建议 80000


# ============================================================
# 结构化错误类型
# ============================================================

class ToolError(Exception):
    """Structured tool error with category and retry hint."""

    CATEGORIES = {
        "timeout": {"retryable": True, "message": "Tool timed out"},
        "invalid": {"retryable": False, "message": "Invalid parameters"},
        "not_found": {"retryable": False, "message": "Resource not found"},
        "internal": {"retryable": True, "message": "Internal error"},
    }

    def __init__(self, category: str, detail: str, tool_name: str = ""):
        self.category = category
        self.detail = detail
        self.tool_name = tool_name
        info = self.CATEGORIES.get(category, {})
        self.retryable = info.get("retryable", False)
        super().__init__(f"[{category}] {detail}")

    def to_dict(self) -> dict:
        return {
            "error": True,
            "category": self.category,
            "tool": self.tool_name,
            "detail": self.detail,
            "retryable": self.retryable,
        }


# ============================================================
# SafeExecutor — 安全执行工具调用
# ============================================================

class SafeExecutor:
    """Wraps tool calls with error handling and retry."""

    def __init__(self, max_retries: int = 2, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.history: list[dict] = []

    def execute(self, tool_name: str, handler: callable,
                args: dict) -> dict:
        """Execute tool with error handling. Returns result dict."""
        attempts = 0
        last_error = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                result = handler(**args)
                # Check result size
                result = ResultManager.check_size(
                    tool_name, result, max_size=MAX_RESULT_SIZE)
                self._record("success", tool_name, args, result, attempts)
                return {"success": True, "result": result, "attempts": attempts}
            except ToolError as e:
                last_error = e
                self._record("error", tool_name, args, e.to_dict(), attempts)
                if not e.retryable or attempts > self.max_retries:
                    break
                time.sleep(self.retry_delay)
            except Exception as e:
                last_error = ToolError("internal", str(e), tool_name)
                self._record("error", tool_name, args, last_error.to_dict(), attempts)
                if attempts > self.max_retries:
                    break
                time.sleep(self.retry_delay)

        return {
            "success": False,
            "error": last_error.to_dict() if last_error else "Unknown error",
            "attempts": attempts,
        }

    def _record(self, status, tool, args, output, attempts):
        self.history.append({
            "status": status, "tool": tool,
            "args": args, "output": output, "attempts": attempts,
        })

    def summary(self) -> str:
        ok = sum(1 for h in self.history if h["status"] == "success")
        fail = sum(1 for h in self.history if h["status"] == "error")
        return f"Executor: {ok} success, {fail} error, {len(self.history)} total"


# ============================================================
# ResultManager — 大结果卸载
# ============================================================

class ResultManager:
    """Offload large results to temp files, replace with placeholders."""

    _temp_dir = None
    _file_counter = 0

    @classmethod
    def _get_temp_dir(cls):
        if cls._temp_dir is None:
            cls._temp_dir = tempfile.mkdtemp(prefix="agent_result_")
        return cls._temp_dir

    @classmethod
    def check_size(cls, tool_name: str, result: str,
                   max_size: int = 80000) -> str:
        if len(result) <= max_size:
            return result
        # Offload to file
        cls._file_counter += 1
        fname = f"{tool_name}_{cls._file_counter}.txt"
        fpath = os.path.join(cls._get_temp_dir(), fname)
        with open(fpath, "w") as f:
            f.write(result)
        placeholder = (
            f"<file:{fpath}> ({len(result)} chars offloaded. "
            f"Use read_file tool to retrieve.)"
        )
        return placeholder

    @classmethod
    def reset(cls):
        """Clean up temp files."""
        if cls._temp_dir and os.path.isdir(cls._temp_dir):
            for f in os.listdir(cls._temp_dir):
                os.remove(os.path.join(cls._temp_dir, f))


# ============================================================
# 模拟工具（带可触发错误的场景）
# ============================================================

def tool_search(query: str) -> str:
    """Search knowledge base. May raise ToolError."""
    if not query or len(query) < 2:
        raise ToolError("invalid", "Query must be at least 2 characters", "search")
    db = {
        "python": "Python is a high-level language by Guido van Rossum.",
        "react": "ReAct: Reasoning + Acting, alternates LLM reasoning and tool use.",
        "agent": "AI Agent: autonomous system that perceives, reasons, and acts.",
    }
    for k, v in db.items():
        if k in query.lower():
            return v
    raise ToolError("not_found", f"No results for '{query}'", "search")


def tool_weather(city: str) -> str:
    """Get weather. Simulates timeout."""
    if city.lower() == "timeout":
        raise ToolError("timeout", "Weather API timed out after 30s", "weather")
    db = {
        "beijing": "Sunny, 28C, humidity 45%",
        "shanghai": "Cloudy, 31C, humidity 72%",
    }
    for k, v in db.items():
        if k in city.lower():
            return v
    raise ToolError("not_found", f"No data for '{city}'", "weather")


def tool_big_data(topic: str) -> str:
    """Simulate a tool that returns large results."""
    base = f"Comprehensive data about {topic}:\n"
    lines = [f"Entry {i}: {'x' * 50}" for i in range(20)]
    return base + "\n".join(lines)


# ============================================================
# Agent loop（集成 SafeExecutor）
# ============================================================

def call_ollama(messages: list) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "options": {"temperature": 0.3, "num_predict": 512},
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
    tools = {"search": tool_search, "weather": tool_weather,
             "big_data": tool_big_data}
    executor = SafeExecutor(max_retries=2)

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
            handler = tools.get(name)
            if not handler:
                result = f"Unknown tool: {name}"
            else:
                outcome = executor.execute(name, handler, args)
                if outcome["success"]:
                    result = outcome["result"]
                else:
                    err = outcome["error"]
                    result = (f"Error [{err.get('category', '?')}]: "
                              f"{err.get('detail', '')}")
                    print(f"  >> Attempts: {outcome['attempts']} "
                          f"(retryable: {err.get('retryable', '?')})")
            print(f"  >> {name}({args}) -> {result[:80]}")
            messages.append({"role": "tool", "tool_name": name, "content": result})

    print(f"\n{executor.summary()}")


# ============================================================
# Demo 模式 — 无需 Ollama
# ============================================================

def run_demo():
    print("=" * 60)
    print("Error Handling & Retry -- Demo Mode (no Ollama)")
    print(f"MAX_RESULT_SIZE = {MAX_RESULT_SIZE} chars")
    print("=" * 60)

    executor = SafeExecutor(max_retries=2, retry_delay=0.1)

    # 1) Normal call
    print("\n--- [1] Normal call ---")
    r = executor.execute("search", tool_search, {"query": "python"})
    print(f"  search('python') -> {r}")

    # 2) Invalid parameters (not retryable)
    print("\n--- [2] Invalid parameters (not retryable) ---")
    r = executor.execute("search", tool_search, {"query": ""})
    print(f"  search('') -> {r}")

    # 3) Not found (not retryable)
    print("\n--- [3] Not found (not retryable) ---")
    r = executor.execute("search", tool_search, {"query": "quantum"})
    print(f"  search('quantum') -> {r}")

    # 4) Timeout (retryable, but demo always fails)
    print("\n--- [4] Timeout (retryable, 2 retries) ---")
    r = executor.execute("weather", tool_weather, {"city": "timeout"})
    print(f"  weather('timeout') -> {r}")

    # 5) Large result offload
    print("\n--- [5] Large result offload ---")
    r = executor.execute("big_data", tool_big_data, {"topic": "climate"})
    result_text = r["result"]
    print(f"  big_data('climate') ->")
    if "<file:" in result_text:
        print(f"    {result_text[:120]}...")
    else:
        print(f"    {result_text[:80]}...")

    # 6) Execution history
    print(f"\n--- [6] Execution history ---")
    print(f"  {executor.summary()}")
    for h in executor.history:
        status = h["status"]
        tool = h["tool"]
        attempts = h["attempts"]
        marker = "OK" if status == "success" else "ERR"
        output_preview = str(h["output"])[:50]
        print(f"  [{marker}] {tool}: attempts={attempts} | {output_preview}")

    # 7) Cleanup
    ResultManager.reset()
    print(f"\n{'='*60}")
    print("Key patterns:")
    print("  - ToolError: structured error with category + retry hint")
    print("  - SafeExecutor: catches exceptions, retries if retryable")
    print("  - ResultManager: offloads large results to <file:...>")
    print("  - Model receives error messages, can adjust strategy")
    print(f"{'='*60}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
        if q:
            run_agent(q)
        else:
            print("Usage: python error_handling.py [--demo | 'question']")
