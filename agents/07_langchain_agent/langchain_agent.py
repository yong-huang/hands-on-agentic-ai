"""
LangChain Agent — 使用 LangChain 框架创建带文件操作工具的 Agent

项目 06-08 手动实现了 ReAct 循环。本项目改用 LangChain 框架:
- @tool 装饰器定义工具（LangChain 自动提取函数签名和 docstring）
- create_agent() 创建 ReAct Agent（底层基于 LangGraph）
- 文件操作工具带安全路径约束（防止访问允许目录之外的文件）

对比:
  手动实现 (06-08)              LangChain 框架 (09)
  ──────────────────────       ─────────────────────────
  手写正则解析器               框架自动 tool calling
  手动循环 for/while           LangGraph 状态机
  手动消息管理                 框架管理 state
  手写 tool 函数               @tool 装饰器 + schema 推断
"""

import os
import sys

# LangChain imports
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_ollama import ChatOllama

# ============================================================
# 安全配置 — 限制文件操作仅在允许的目录内
# ============================================================

# 生产环境应使用更严格的沙箱（如 Docker / chroot）
ALLOWED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")


def _safe_path(filepath: str) -> str:
    """Resolve path and verify it's within ALLOWED_DIR."""
    if not os.path.isabs(filepath):
        filepath = os.path.join(ALLOWED_DIR, filepath)
    filepath = os.path.realpath(filepath)
    allowed = os.path.realpath(ALLOWED_DIR)
    if not filepath.startswith(allowed + os.sep) and filepath != allowed:
        return f"ERROR: Path '{filepath}' is outside allowed directory '{ALLOWED_DIR}'"
    return filepath


# ============================================================
# 工具定义 — @tool 装饰器
# LangChain 自动从函数签名和 docstring 提取:
#   - 参数名和类型
#   - 返回类型
#   - 工具描述（docstring 第一行）
# 这些信息会作为 tool schema 发送给模型
# ============================================================

@tool
def read_file(filepath: str) -> str:
    """Read the content of a file. Must be within the workspace directory."""
    resolved = _safe_path(filepath)
    if resolved.startswith("ERROR"):
        return resolved
    if not os.path.isfile(resolved):
        return f"ERROR: File not found: {resolved}"
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()
        return content[:2000] if len(content) > 2000 else content
    except Exception as e:
        return f"ERROR: {e}"


@tool
def write_file(filepath: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed."""
    resolved = _safe_path(filepath)
    if resolved.startswith("ERROR"):
        return resolved
    try:
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return f"OK: Written {len(content)} chars to {resolved}"
    except Exception as e:
        return f"ERROR: {e}"


@tool
def list_dir(dirpath: str) -> str:
    """List files and directories in the given path. Defaults to workspace root."""
    if not dirpath:
        dirpath = "."
    resolved = _safe_path(dirpath)
    if resolved.startswith("ERROR"):
        return resolved
    if not os.path.isdir(resolved):
        return f"ERROR: Not a directory: {resolved}"
    try:
        entries = os.listdir(resolved)
        if not entries:
            return f"(empty directory: {resolved})"
        lines = []
        for e in sorted(entries):
            full = os.path.join(resolved, e)
            prefix = "[DIR]" if os.path.isdir(full) else "[FILE]"
            size = ""
            if os.path.isfile(full):
                sz = os.path.getsize(full)
                size = f" ({sz} bytes)"
            lines.append(f"  {prefix} {e}{size}")
        return f"Directory: {resolved}\n" + "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


@tool
def search_files(keyword: str, dirpath: str = ".") -> str:
    """Search for files containing a keyword in their name or content."""
    resolved = _safe_path(dirpath)
    if resolved.startswith("ERROR"):
        return resolved
    matches = []
    for root, dirs, files in os.walk(resolved):
        for f in files:
            if keyword.lower() in f.lower():
                matches.append(os.path.join(root, f))
            elif f.endswith((".txt", ".md", ".py")):
                try:
                    full = os.path.join(root, f)
                    with open(full, "r", encoding="utf-8") as fh:
                        if keyword.lower() in fh.read().lower():
                            matches.append(full)
                except Exception:
                    pass
    if not matches:
        return f"No matches for '{keyword}' in {resolved}"
    return "Matches:\n" + "\n".join(f"  - {m}" for m in matches[:20])


@tool
def calculator(expression: str) -> str:
    """Evaluate a simple math expression (e.g., '2 + 3 * 4')."""
    import re
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)]+$', expression):
        return f"ERROR: Invalid expression '{expression}'"
    try:
        return str(eval(expression))
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# Demo 模式 — 无需 Ollama，直接调用工具展示流程
# ============================================================

def run_demo():
    """Run tools directly to demonstrate LangChain tool usage."""
    print("=" * 60)
    print("LangChain Agent — Demo Mode (no Ollama needed)")
    print(f"Workspace: {ALLOWED_DIR}")
    print("=" * 60)

    # Setup workspace
    os.makedirs(ALLOWED_DIR, exist_ok=True)

    # 1) Write a file
    print("\n[Tool] write_file('hello.txt', 'Hello from LangChain Agent!')")
    result = write_file.invoke({"filepath": "hello.txt",
                                "content": "Hello from LangChain Agent!\nThis is a test file."})
    print(f"  -> {result}")

    # 2) Read the file
    print("\n[Tool] read_file('hello.txt')")
    result = read_file.invoke({"filepath": "hello.txt"})
    print(f"  -> {result}")

    # 3) Write another file
    print("\n[Tool] write_file('notes/plan.md', '# Plan\\n## Step 1\\nBuild agent\\n## Step 2\\nTest tools')")
    result = write_file.invoke({"filepath": "notes/plan.md",
                                "content": "# Plan\n## Step 1\nBuild agent\n## Step 2\nTest tools\n## Step 3\nDeploy"})
    print(f"  -> {result}")

    # 4) List directory
    print("\n[Tool] list_dir('.')")
    result = list_dir.invoke({"dirpath": "."})
    print(f"  -> {result}")

    # 5) Search
    print("\n[Tool] search_files('agent', '.')")
    result = search_files.invoke({"keyword": "agent", "dirpath": "."})
    print(f"  -> {result}")

    # 6) Calculator
    print("\n[Tool] calculator('2 + 3 * 4')")
    result = calculator.invoke({"expression": "2 + 3 * 4"})
    print(f"  -> {result}")

    # 7) Path traversal test (security)
    print("\n[Tool] read_file('../../../etc/passwd')  [should be blocked]")
    result = read_file.invoke({"filepath": "../../../etc/passwd"})
    print(f"  -> {result}")

    # 8) Show tool schemas (what LangChain sends to the model)
    print(f"\n{'='*60}")
    print("Tool Schemas (what LangChain sends to the LLM):")
    print(f"{'='*60}")
    for t in [read_file, write_file, list_dir, search_files, calculator]:
        schema = t.get_input_schema().model_json_schema()
        print(f"\n  {schema['title']}")
        print(f"    Description: {schema.get('description', 'N/A')}")
        props = schema.get("properties", {})
        for pname, pinfo in props.items():
            print(f"    - {pname}: {pinfo.get('type', '?')} "
                  f"({pinfo.get('description', 'N/A')})")

    print(f"\n{'='*60}")
    print("In LangChain Agent mode, the framework automatically:")
    print("  1. Sends tool schemas to the LLM as part of the API request")
    print("  2. Parses LLM tool_call responses")
    print("  3. Executes the matched tool")
    print("  4. Feeds the result back to the LLM")
    print("  5. Repeats until the LLM gives a final text response")
    print(f"{'='*60}")


# ============================================================
# LangChain Agent 模式
# ============================================================

def run_agent(question: str = None):
    """Create and run a LangChain ReAct agent with file tools."""
    model_name = "qwen3.8:latest"

    print("=" * 60)
    print("LangChain Agent (ReAct)")
    print(f"Model: {model_name}")
    print(f"Workspace: {ALLOWED_DIR}")
    print(f"Tools: read_file, write_file, list_dir, search_files, calculator")
    print("=" * 60)

    os.makedirs(ALLOWED_DIR, exist_ok=True)

    try:
        # qwen3.8 默认开启 thinking——最终回复可能整段耗在 thinking
        # 通道导致 message.content 为空。reasoning=False 让正文直接进 content。
        llm = ChatOllama(model=model_name, reasoning=False)
        agent = create_agent(
            model=llm,
            tools=[read_file, write_file, list_dir, search_files, calculator],
            system_prompt=(
                "You are a file management assistant. "
                "Use the provided tools to read, write, search, and list files. "
                "All file operations are restricted to the workspace directory. "
                "Always confirm what you did."
            ),
        )
    except Exception as e:
        print(f"Error creating agent: {e}")
        print("Note: qwen3.8 may not be compatible with LangChain tool calling.")
        print("Try: python langchain_agent.py --demo")
        return

    if not question:
        question = (
            "Create a file called 'summary.txt' with a summary of the "
            "workspace contents, then read it back to confirm."
        )

    print(f"\nUser: {question}\n")

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
        )
    except Exception as e:
        print(f"Error during agent execution: {e}")
        print("Note: qwen3.8 may have format issues with LangChain tool calling.")
        return

    # Extract final answer from messages
    def _text(msg):
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            # content_blocks format
            return "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
        return content

    messages = result.get("messages", [])
    if messages:
        content = _text(messages[-1])
        if not content:
            # 兜底: 模型最终回复为空时, 回退到最后一条非空 AI 消息, 再退到工具结果
            for m in reversed(messages):
                text = _text(m)
                if text:
                    content = text
                    break
        print(f"Agent: {content}")

    # Print tool call summary
    tool_calls = [m for m in messages
                  if getattr(m, "type", None) == "tool"
                  or (hasattr(m, "tool_calls") and m.tool_calls)]
    print(f"\nTool calls: {len(tool_calls)}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
        run_agent(q)
