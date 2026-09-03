"""
工具授权与 HITL 审批 — Human-in-the-Loop 工具审批机制

项目 12-14 的工具调用对模型完全放权：模型选什么工具就执行什么。
生产环境中某些工具是危险的（删除文件、发送邮件、执行命令），
需要人工审批才能执行。

本项目实现:
  - ApprovalPolicy: 工具分级（auto / confirm / deny）
  - ApprovalGate: 执行前拦截检查，confirm 级工具暂停等待用户确认
  - ApprovalLog: 审批记录（谁批的、什么时候、什么结果）
  - 白名单机制: 非白名单工具直接拒绝

核心概念:
- HITL (Human-in-the-Loop): 关键决策需要人类参与
- 分级授权: 安全工具自动执行，危险工具需确认，禁止工具直接拒绝
- 审计日志: 每次审批决策留痕
"""

import json
import os
import re
import sys
import tempfile
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
HEADERS = {"Content-Type": "application/json"}


# ============================================================
# 审批策略
# ============================================================

class ApprovalPolicy:
    """Tool approval levels: auto (safe), confirm (dangerous), deny (forbidden)."""

    def __init__(self):
        self._rules: dict[str, str] = {}
        # Default: all tools require confirmation
        self._default = "confirm"

    def set(self, tool_name: str, level: str):
        if level not in ("auto", "confirm", "deny"):
            raise ValueError(f"Invalid level: {level}")
        self._rules[tool_name] = level

    def get(self, tool_name: str) -> str:
        return self._rules.get(tool_name, self._default)

    def setup_defaults(self):
        """Pre-configure common tools."""
        safe_tools = ["calculator", "get_weather", "search",
                      "lookup_population", "read_file", "list_dir"]
        dangerous_tools = ["delete_file", "send_email", "execute_command",
                           "write_file", "write_db"]
        forbidden_tools = ["format_disk", "rm_rf", "drop_database"]

        for name in safe_tools:
            self.set(name, "auto")
        for name in dangerous_tools:
            self.set(name, "confirm")
        for name in forbidden_tools:
            self.set(name, "deny")


# ============================================================
# 审批日志
# ============================================================

class ApprovalLog:
    """Record all approval decisions."""

    def __init__(self):
        self._entries: list[dict] = []

    def record(self, tool_name: str, args: dict, policy_level: str,
               decision: str, detail: str = ""):
        self._entries.append({
            "time": datetime.now().isoformat(),
            "tool": tool_name,
            "args": args,
            "policy": policy_level,
            "decision": decision,  # approved / denied / auto / forbidden
            "detail": detail,
        })

    @property
    def entries(self) -> list[dict]:
        return list(self._entries)

    def summary(self) -> str:
        auto = sum(1 for e in self._entries if e["decision"] == "auto")
        approved = sum(1 for e in self._entries if e["decision"] == "approved")
        denied = sum(1 for e in self._entries if e["decision"] == "denied")
        forbidden = sum(1 for e in self._entries if e["decision"] == "forbidden")
        return (f"Approval Log: {auto} auto, {approved} approved, "
                f"{denied} denied, {forbidden} forbidden, {len(self._entries)} total")


# ============================================================
# ApprovalGate — 执行拦截器
# ============================================================

class ApprovalGate:
    """Intercept tool calls, enforce approval policy."""

    def __init__(self, policy: ApprovalPolicy, log: ApprovalLog,
                 auto_approve: bool = False):
        self.policy = policy
        self.log = log
        self.auto_approve = auto_approve  # For non-interactive mode

    def check(self, tool_name: str, args: dict) -> dict:
        """Check if tool call is allowed. Returns decision dict."""
        level = self.policy.get(tool_name)

        if level == "deny":
            self.log.record(tool_name, args, level, "forbidden",
                            "Tool is forbidden by policy")
            return {"allowed": False, "reason": f"Tool '{tool_name}' is forbidden"}

        if level == "auto":
            self.log.record(tool_name, args, level, "auto")
            return {"allowed": True, "reason": "Auto-approved (safe tool)"}

        # level == "confirm": need human approval
        if self.auto_approve:
            self.log.record(tool_name, args, level, "approved",
                            "Auto-approved (non-interactive mode)")
            return {"allowed": True, "reason": "Auto-approved (non-interactive)"}

        # Interactive: ask user
        decision = self._ask_user(tool_name, args)
        if decision:
            self.log.record(tool_name, args, level, "approved",
                            "User approved")
            return {"allowed": True, "reason": "User approved"}
        else:
            self.log.record(tool_name, args, level, "denied",
                            "User denied")
            return {"allowed": False, "reason": "User denied"}

    def _ask_user(self, tool_name: str, args: dict) -> bool:
        """Prompt user for approval. Returns True if approved."""
        args_str = json.dumps(args, ensure_ascii=False)
        print(f"\n  [APPROVAL REQUIRED] {tool_name}({args_str})")
        print(f"  This tool requires human confirmation.")
        while True:
            try:
                choice = input("  Approve? [y/n]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                return False
            if choice in ("y", "yes"):
                return True
            elif choice in ("n", "no"):
                return False
            print("  Please enter 'y' or 'n'.")


# ============================================================
# 模拟工具
# ============================================================

def tool_calculator(expression: str) -> str:
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)\^]+$', expression):
        return f"Error: invalid '{expression}'"
    return str(eval(expression.replace('^', '**')))


def tool_delete_file(filepath: str) -> str:
    if not os.path.isabs(filepath):
        filepath = os.path.join(SCRIPT_DIR, "workspace", filepath)
    if os.path.isfile(filepath):
        os.remove(filepath)
        return f"Deleted: {filepath}"
    return f"Not found: {filepath}"


def tool_send_email(to: str, subject: str, body: str) -> str:
    return f"Email sent to {to}: {subject}"


def tool_format_disk() -> str:
    return "FORMAT DISK -- BLOCKED"


def tool_execute_command(cmd: str) -> str:
    return f"Executed: {cmd} (simulated)"


TOOLS = {
    "calculator": tool_calculator,
    "delete_file": tool_delete_file,
    "send_email": tool_send_email,
    "format_disk": tool_format_disk,
    "execute_command": tool_execute_command,
}


# ============================================================
# Demo 模式
# ============================================================

def run_demo():
    print("=" * 60)
    print("HITL Approval -- Demo Mode (no Ollama)")
    print("=" * 60)

    policy = ApprovalPolicy()
    policy.setup_defaults()
    log = ApprovalLog()

    # Interactive gate for demo (auto_approve=False for some, True for others)
    interactive_gate = ApprovalGate(policy, log, auto_approve=False)
    auto_gate = ApprovalGate(policy, log, auto_approve=True)

    # Show policy
    print("\n--- Approval Policy ---")
    for name in ["calculator", "delete_file", "send_email",
                  "format_disk", "execute_command", "unknown_tool"]:
        level = policy.get(name)
        marker = {"auto": "[SAFE]", "confirm": "[RISKY]", "deny": "[BLOCKED]"}
        print(f"  {name:<20} -> {level:<10} {marker.get(level, '')}")

    # Simulate calls with auto_approve gate
    print("\n--- Auto-approve mode (simulating user decisions) ---")
    scenarios = [
        ("calculator", {"expression": "2+3"}, "auto"),
        ("delete_file", {"filepath": "test.txt"}, "approved"),
        ("send_email", {"to": "a@b.com", "subject": "hi", "body": "hello"}, "approved"),
        ("format_disk", {}, "forbidden"),
        ("execute_command", {"cmd": "rm -rf /"}, "approved"),
        ("delete_file", {"filepath": "important.db"}, "denied"),
    ]

    # Override _ask_user to simulate user responses
    decisions = iter(["y", "y", "n"])  # first 3 confirm calls: y, y, n

    def mock_ask(tool_name, args):
        return next(decisions, False)

    interactive_gate._ask_user = mock_ask

    for name, args, expected in scenarios:
        result = interactive_gate.check(name, args)
        status = "ALLOWED" if result["allowed"] else "BLOCKED"
        icon = "OK" if result["allowed"] else "X"
        print(f"  [{icon}] {name}({args}) -> {status}: {result['reason']}")

    # Show approval log
    print(f"\n--- {log.summary()} ---")
    for entry in log.entries:
        icon = {"auto": ".", "approved": "+", "denied": "-",
                "forbidden": "!"}[entry["decision"]]
        detail = entry["detail"][:40]
        print(f"  [{icon}] {entry['tool']:<20} {entry['decision']:<12} {detail}")

    print("\nTip: run `python hitl_approval.py --interactive` to answer")
    print("     the confirmation prompts yourself in the terminal.")

    # Decision flow
    print(f"\n{'='*60}")
    print("Approval Gate Decision Flow:")
    print("  tool_call -> policy.get(name)")
    print("    -> 'auto':    log + execute immediately")
    print("    -> 'confirm': pause -> ask user")
    print("                  -> yes: log + execute")
    print("                  -> no:  log + skip (error to model)")
    print("    -> 'deny':    log + reject immediately")
    print(f"{'='*60}")
    print("\nModel receives approval decisions:")
    print("  Approved:  normal tool result")
    print("  Denied:    'Tool execution denied by user'")
    print("  Forbidden: 'Tool is forbidden by policy'")
    print("  Model can then adjust strategy (e.g., explain to user)")


# ============================================================
# Interactive 模式 — 真实在终端等待人工确认（无需 Ollama）
# ============================================================

def run_interactive():
    print("=" * 60)
    print("HITL Approval -- Interactive Mode (real y/n prompts)")
    print("=" * 60)

    policy = ApprovalPolicy()
    policy.setup_defaults()
    log = ApprovalLog()
    gate = ApprovalGate(policy, log, auto_approve=False)

    # 与 run_demo 相同的调用序列，但 confirm 类工具会真正暂停等输入
    scenarios = [
        ("calculator", {"expression": "2+3"}),
        ("delete_file", {"filepath": "test.txt"}),
        ("send_email", {"to": "a@b.com", "subject": "hi", "body": "hello"}),
        ("format_disk", {}),
        ("execute_command", {"cmd": "rm -rf /"}),
        ("delete_file", {"filepath": "important.db"}),
    ]

    for name, args in scenarios:
        print(f"\n🤖 Agent 请求调用: {name}({args})")
        result = gate.check(name, args)
        if result["allowed"]:
            # 只有审批通过才真正执行；拒绝时模型收到的是拒绝原因
            output = TOOLS[name](**args)
            print(f"  ✅ 已执行 -> {output}")
        else:
            print(f"  ❌ 已拦截 -> 模型将收到: {result['reason']}")

    print(f"\n--- {log.summary()} ---")
    for entry in log.entries:
        icon = {"auto": ".", "approved": "+", "denied": "-",
                "forbidden": "!"}[entry["decision"]]
        print(f"  [{icon}] {entry['tool']:<20} {entry['decision']:<12}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    elif "--interactive" in sys.argv or len(sys.argv) == 1:
        if len(sys.argv) == 1:
            print("Usage: python hitl_approval.py [--demo | --interactive]\n")
        run_interactive()
