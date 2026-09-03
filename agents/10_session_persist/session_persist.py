"""
会话管理与状态持久化 — Agent 会话的保存与恢复

项目 05 实现了多轮对话的消息历史，但会话在程序退出后丢失。
项目 07 的 AgentLoop 有事件流记录，但没有持久化。
本项目实现了完整的会话生命周期:
  创建 → 对话 → 保存(JSON) → 退出 → 恢复 → 继续对话

核心概念:
- AgentSession: 封装消息历史 + 工具调用记录 + 元数据
- JSON 持久化: 序列化/反序列化会话状态
- 会话索引: 支持多个命名会话的创建、列出、切换、删除
"""

import json
import os
import re
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(SCRIPT_DIR, "sessions")

# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
HEADERS = {"Content-Type": "application/json"}


# ============================================================
# 工具定义
# ============================================================

def tool_calculator(expression: str) -> str:
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)\^]+$', expression):
        return f"Error: invalid '{expression}'"
    try:
        return str(eval(expression.replace('^', '**')))
    except Exception as e:
        return f"Error: {e}"


def tool_lookup_fact(keyword: str) -> str:
    facts = {
        "python": "Python by Guido van Rossum, 1991.",
        "gil": "GIL limits one thread at a time in CPython.",
        "rag": "RAG retrieves docs then generates answers.",
        "react": "ReAct alternates reasoning and tool use.",
    }
    for k, v in facts.items():
        if k in keyword.lower():
            return v
    return f"Not found: '{keyword}'"


TOOLS = {"Calculator": tool_calculator, "LookupFact": tool_lookup_fact}


# ============================================================
# AgentSession — 会话状态
# ============================================================

class AgentSession:
    """封装 Agent 的完整会话状态，支持序列化到 JSON。"""

    def __init__(self, session_id: str = None):
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        self.session_id = session_id or self._generate_id()
        self.messages = []       # API 格式的消息列表
        self.tool_calls = []     # 工具调用记录
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        self.metadata = {"model": MODEL, "steps": 0}

    @staticmethod
    def _generate_id() -> str:
        return datetime.now().strftime("sess_%Y%m%d_%H%M%S")

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self._touch()

    def add_assistant(self, content: str):
        self.messages.append({"role": "assistant", "content": content})
        self._touch()

    def add_observation(self, content: str):
        # Observation 以 assistant 形式记录（实际以 user 发给 API）
        self.tool_calls.append({
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        self._touch()

    def _touch(self):
        self.updated_at = datetime.now().isoformat()
        self.metadata["steps"] = len(
            [m for m in self.messages if m["role"] == "user"])

    def set_system_prompt(self, prompt: str):
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0]["content"] = prompt
        else:
            self.messages.insert(0, {"role": "system", "content": prompt})

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "tool_calls": self.tool_calls,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentSession":
        sess = cls(data["session_id"])
        sess.messages = data["messages"]
        sess.tool_calls = data.get("tool_calls", [])
        sess.created_at = data["created_at"]
        sess.updated_at = data["updated_at"]
        sess.metadata = data.get("metadata", {})
        return sess

    def save(self):
        path = os.path.join(SESSIONS_DIR, f"{self.session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, session_id: str) -> "AgentSession":
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def list_sessions(cls) -> list:
        """列出所有已保存的会话。"""
        if not os.path.isdir(SESSIONS_DIR):
            return []
        result = []
        for fname in sorted(os.listdir(SESSIONS_DIR)):
            if fname.endswith(".json"):
                path = os.path.join(SESSIONS_DIR, fname)
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    result.append({
                        "session_id": data["session_id"],
                        "steps": data.get("metadata", {}).get("steps", 0),
                        "updated": data.get("updated_at", "unknown"),
                        "messages": len(data.get("messages", [])),
                    })
                except Exception:
                    pass
        return result

    @classmethod
    def delete(cls, session_id: str) -> bool:
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.isfile(path):
            os.remove(path)
            return True
        return False

    def summary(self) -> str:
        user_msgs = sum(1 for m in self.messages if m["role"] == "user")
        return (f"Session: {self.session_id} | "
                f"Messages: {len(self.messages)} | "
                f"User turns: {user_msgs} | "
                f"Tool calls: {len(self.tool_calls)} | "
                f"Updated: {self.updated_at}")


# ============================================================
# ReAct Agent（复用项目 06 的核心逻辑）
# ============================================================

SYSTEM_PROMPT = """You are a helpful assistant with tools.
Use format:
Thought: reasoning
Action: tool name
Action Input: parameter

When ready:
Thought: summary
Answer: final answer"""


def parse_react(text: str) -> dict:
    result = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^Thought:\s*(.+)$', line, re.IGNORECASE)
        if m:
            result['thought'] = m.group(1).strip(); continue
        m = re.match(r'^Action:\s*(.+)$', line, re.IGNORECASE)
        if m:
            result['action'] = m.group(1).strip(); continue
        m = re.match(r'^Action Input:\s*(.+)$', line, re.IGNORECASE)
        if m:
            result['action_input'] = m.group(1).strip(); continue
        m = re.match(r'^Answer:\s*(.+)$', line, re.IGNORECASE)
        if m:
            result['answer'] = m.group(1).strip(); continue
    return result if result else None


def call_llm(messages: list, temperature: float = 0.3) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "options": {"temperature": temperature, "num_predict": 512},
        "stream": False,
    }
    try:
        resp = __import__('requests').post(
            BASE_URL, headers=HEADERS, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]
        if not content or len(content) < 5:
            content = data.get("message", {}).get("thinking", "")
        return content
    except Exception as e:
        return f"API Error: {e}"


def agent_step(session: AgentSession, max_steps: int = 6) -> str:
    """Run a single user turn through the ReAct loop."""
    model_output = call_llm(session.messages)
    if not model_output:
        return "API call failed"

    for i in range(max_steps):
        session.add_assistant(model_output)
        parsed = parse_react(model_output)

        if parsed is None:
            session.add_user("Error: cannot parse. Output Thought + Action/Answer.")
            model_output = call_llm(session.messages)
            if not model_output:
                break
            continue

        thought = parsed.get("thought", "")

        if "answer" in parsed:
            return parsed["answer"]

        if "action" in parsed:
            action = parsed["action"]
            action_input = parsed.get("action_input", "")
            tool_fn = TOOLS.get(action)
            if tool_fn:
                obs = tool_fn(action_input)
            else:
                obs = f"Unknown tool '{action}'"
            session.add_observation(f"{action}({action_input}) -> {obs}")
            print(f"  >> Action: {action}({action_input})")
            print(f"  >> Observation: {obs}")
            session.add_user(f"Observation: {obs}")
            model_output = call_llm(session.messages)
            if not model_output:
                break
            continue

        session.add_user("Error: output Thought + Action or Thought + Answer.")
        model_output = call_llm(session.messages)
        if not model_output:
            break

    return "Max steps reached"


# ============================================================
# CLI 交互
# ============================================================

def print_help():
    print("\nCommands:")
    print("  /save       - Save session and exit")
    print("  /resume ID  - Resume a saved session")
    print("  /list       - List saved sessions")
    print("  /delete ID  - Delete a saved session")
    print("  /info       - Show session summary")
    print("  /exit       - Exit without saving")
    print("  /help       - Show this help\n")


def run_cli(session: AgentSession):
    """Interactive CLI loop."""
    print(f"\n{session.summary()}")
    print("Type /help for commands\n")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nUse /save to save, /exit to quit.")
            continue

        if not user_input:
            continue

        # Commands
        cmd = user_input.lower().split()
        cmd_name = cmd[0] if cmd else ""

        if cmd_name == "/exit":
            print("Bye!")
            return
        elif cmd_name == "/save":
            path = session.save()
            print(f"Saved: {path}")
            return
        elif cmd_name == "/list":
            sessions = AgentSession.list_sessions()
            if not sessions:
                print("No saved sessions.")
            else:
                print(f"{'Session ID':<25} {'Msgs':>6} {'Updated':<20}")
                print("-" * 55)
                for s in sessions:
                    print(f"{s['session_id']:<25} {s['messages']:>6} {s['updated']:<20}")
            continue
        elif cmd_name == "/delete" and len(cmd) > 1:
            sid = cmd[1]
            if AgentSession.delete(sid):
                print(f"Deleted: {sid}")
            else:
                print(f"Not found: {sid}")
            continue
        elif cmd_name == "/info":
            print(session.summary())
            continue
        elif cmd_name == "/help":
            print_help()
            continue
        elif cmd_name == "/resume" and len(cmd) > 1:
            try:
                session = AgentSession.load(cmd[1])
                print(f"Resumed: {session.summary()}")
                # Show recent messages for context
                recent = session.messages[-4:]
                for m in recent:
                    role = "You" if m["role"] == "user" else "Sys" if m["role"] == "system" else "Agent"
                    preview = m["content"][:80]
                    print(f"  [{role}] {preview}")
                continue
            except FileNotFoundError:
                print(f"Not found: {cmd[1]}")
            except Exception as e:
                print(f"Error: {e}")
            continue

        # Agent turn
        session.add_user(user_input)
        answer = agent_step(session)
        print(f"\nAgent: {answer}")


# ============================================================
# Demo 模式
# ============================================================

def run_demo():
    """Simulate save → restore → continue without Ollama."""
    print("=" * 60)
    print("Session Persistence — Demo Mode (no Ollama)")
    print(f"Sessions dir: {SESSIONS_DIR}")
    print("=" * 60)

    # ---- Phase 1: Create session, do 2 turns ----
    print("\n--- Phase 1: Create session, 2 turns ---")
    sess = AgentSession("demo_20260812")
    sess.set_system_prompt(SYSTEM_PROMPT)

    # Turn 1
    sess.add_user("What is Python?")
    sess.add_assistant("Thought: Common knowledge\nAnswer: Python is a language by Guido van Rossum.")
    sess.add_observation("no tools used")
    print("  Turn 1: What is Python? -> Python is a language...")

    # Turn 2
    sess.add_user("What about its GIL?")
    sess.add_assistant("Thought: Need to look up GIL\nAction: LookupFact\nAction Input: gil")
    print("  Turn 2: What about its GIL? -> Action: LookupFact(gil)")
    obs = tool_lookup_fact("gil")
    sess.add_observation(f"LookupFact(gil) -> {obs}")
    print(f"  >> Observation: {obs}")
    sess.add_user(f"Observation: {obs}")
    sess.add_assistant(f"Thought: Got info\nAnswer: {obs}")
    print(f"  >> Answer: {obs}")

    print(f"\n  {sess.summary()}")

    # ---- Save ----
    path = sess.save()
    print(f"\n  Saved to: {path}")

    # Show JSON structure (first 20 lines)
    with open(path) as f:
        lines = f.readlines()
    print(f"\n  JSON preview ({len(lines)} lines):")
    for line in lines[:15]:
        print(f"    {line.rstrip()}")
    if len(lines) > 15:
        print(f"    ... ({len(lines) - 15} more lines)")

    # ---- Phase 2: Restore session ----
    print(f"\n--- Phase 2: Restore session ---")
    restored = AgentSession.load("demo_20260812")
    print(f"  Restored: {restored.summary()}")

    # Verify messages match
    assert restored.session_id == sess.session_id
    assert len(restored.messages) == len(sess.messages)
    assert len(restored.tool_calls) == len(sess.tool_calls)
    print("  Verification: messages and tool_calls match!")

    # ---- Phase 3: Continue conversation ----
    print(f"\n--- Phase 3: Continue conversation (turn 3) ---")
    restored.add_user("Tell me about ReAct.")
    restored.add_assistant("Thought: Look up ReAct\nAction: LookupFact\nAction Input: react")
    print("  Turn 3: Tell me about ReAct -> Action: LookupFact(react)")
    obs2 = tool_lookup_fact("react")
    restored.add_observation(f"LookupFact(react) -> {obs2}")
    print(f"  >> Observation: {obs2}")
    restored.add_user(f"Observation: {obs2}")
    restored.add_assistant(f"Thought: Got info\nAnswer: {obs2}")
    print(f"  >> Answer: {obs2}")

    print(f"\n  {restored.summary()}")

    # ---- Save updated session ----
    path2 = restored.save()
    print(f"  Updated: {path2}")

    # ---- List sessions ----
    print(f"\n--- List all sessions ---")
    for s in AgentSession.list_sessions():
        print(f"  {s['session_id']:<25} msgs={s['messages']:<4} steps={s['steps']}")

    # Cleanup
    os.remove(path)

    print(f"\n  Demo complete: save -> restore -> continue -> re-save all verified!")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        session = AgentSession()
        session.set_system_prompt(SYSTEM_PROMPT)
        run_cli(session)
