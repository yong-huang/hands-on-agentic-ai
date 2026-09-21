"""mh.cli — mini-harness 终极总装 (项目 17 🏁): 类 Claude Code 终端 REPL

接线清单(12 模块全部上场):
  llm(loop) · tools(契约) · sandbox(执行) · permissions(权限门)
  hooks(.env 保护) · budget(止损) · compaction(压缩) · session(恢复)
  memory(长期记忆) · skills(按需知识) · [subagent/mcp 按需挂载]

斜杠命令: /help /context /budget /resume /memory /quit
每个会话的证据线写 harness_session.log —— 17 的验收不看嘴, 看日志。

用法:
  python -m mh.cli --sandbox DIR            # 交互式 REPL
  python -m mh.cli --scripted FILE --sandbox DIR   # 脚本化驱动(验收用)
"""

import argparse
import sys
import tempfile
import time
from pathlib import Path

from . import llm as mh_llm
from . import loop
from .budget import Budget, budget_chat_fn
from .compaction import compact_chat_fn, est_tokens
from .hooks import HookManager, protect_file
from .memory import Memory, system_with_memory
from .permissions import PermissionGate, wrap_tool
from .sandbox import run as sandbox_run
from .session import SessionStore, record_chat_fn, skip_redo_tools, snapshotting_tools
from .skills import SkillBook, skill_tools, system_with_skills
from .tools import Registry, tool

BASE_SYSTEM = ("你是 mini-harness 的运维助手, 在任务目录内通过工具完成任务, "
               "完成后简要汇报。/no_think")

RULES_YAML = """\
rules:
  - {pattern: "rm*",     decision: deny,  reason: "删除类命令默认禁止"}
  - {pattern: "ls*",     decision: allow, reason: "只读直通"}
  - {pattern: "cat*",    decision: allow, reason: "只读直通"}
  - {pattern: "wc*",     decision: allow, reason: "只读直通"}
  - {pattern: "echo*",   decision: allow, reason: "良性写"}
  - {pattern: "printf*", decision: allow, reason: "良性写"}
  - {pattern: "touch*",  decision: allow, reason: "建文件"}
  - {pattern: "cp*",     decision: allow, reason: "复制"}
  - {pattern: "mkdir*",  decision: allow, reason: "建目录"}
  - {pattern: "grep*",   decision: allow, reason: "只读"}
  - {pattern: "sed -n*", decision: allow, reason: "只读"}
  - {pattern: "python3*", decision: allow, reason: "脚本自测允许(演示 profile)"}
  - {pattern: "bash *",  decision: allow, reason: "脚本自测允许(演示 profile)"}
"""


class MiniHarness:
    def __init__(self, sandbox: str, log_path=None, compaction_threshold=1200,
                 memory=None, skills_dir=None, checkpoint=None):
        self.sandbox = sandbox
        self.log_path = Path(log_path) if log_path else None
        self.memory = memory or Memory(Path(sandbox) / "MEMORY.md")
        self.store = SessionStore(checkpoint) if checkpoint else None
        self.messages = []
        self.events = []  # 验收证据: (kind, detail)
        self._build_messages()

    def log(self, kind, detail=""):
        self.events.append((kind, detail))
        if self.log_path:
            with self.log_path.open("a") as f:
                f.write(f"{time.strftime('%H:%M:%S')}\t{kind}\t{detail[:150]}\n")

    def _build_messages(self):
        sysmsg = system_with_skills(system_with_memory(BASE_SYSTEM, self.memory),
                                    self._book())
        if self.store and self.store.data.get("messages"):
            self.messages = self.store.resume_messages()
            self.log("resume", f"恢复 {len(self.messages)} 条历史")
        else:
            self.messages = [{"role": "system", "content": sysmsg}]
        self.log("memory_injected", self.memory.recall()[:120])
        self.log("skills_menu", str(len(sysmsg)) + " 字符 system")

    def _book(self):
        sd = Path(__file__).resolve().parents[1] / "14_skills" / "skills_demo"
        return SkillBook(sd) if sd.exists() else SkillBook(_empty_skills_dir())

    def _build_chat(self, budget: Budget):
        base = self.store and record_chat_fn(mh_llm.chat_with_retry, self.store) \
            or mh_llm.chat_with_retry
        chat = compact_chat_fn(base, threshold=2000, keep_recent=6)
        chat.events_prefix = None
        original = chat

        def wrapped(messages, tools=None, **kw):
            before = len(original.events)
            out = original(messages, tools=tools, **kw)
            if len(original.events) > before:
                e = original.events[-1]
                self.log("compaction", f"{e['before']}→{e['after']} tok")
            return out
        return budget_chat_fn(wrapped, budget)

    def turn(self, user_input: str) -> str:
        """一个用户输入 → 一个完整 agent 回合。"""
        budget = Budget(max_turns=10, max_tokens=8000)
        chat = self._build_chat(budget)
        tools = self._tools()
        self.messages.append({"role": "user", "content": user_input})
        result = loop.run_agent(user_input, tools, max_turns=10, chat_fn=chat,
                                cwd=self.sandbox, messages=self.messages)
        if not result["final"] and result["turns"] > 0:
            # 空回复兜底: 视为模型失语, 注入催办再来一轮(03: 空回复是配额问题)
            self.log("empty_reply_retry", user_input[:40])
            retry_msgs = self.messages + [
                {"role": "user", "content": "请继续完成任务并汇报结果。"}]
            result = loop.run_agent(user_input, tools, max_turns=10,
                                    chat_fn=chat, cwd=self.sandbox,
                                    messages=retry_msgs)
            self.messages = result["messages"]
        else:
            self.messages = result["messages"]
        for e in budget.events:
            self.log("budget_" + e[0], f"turn {e[1]}")
        if self.store:
            self.store.save(self.messages)
        return result["final"]

    def _tools(self):
        reg = Registry()

        @tool
        def run_bash(command: str, cwd: str = None) -> str:
            """在任务目录执行一条 bash 命令(经权限门+沙箱)。"""
            ok, out = sandbox_run(command, cwd=cwd or ".")
            return out if ok else f"[sandbox] {out}"

        reg.add(run_bash)
        entries = reg.to_loop_tools()
        hooks = HookManager()
        hooks.add_pre(protect_file(".env", "禁止修改 .env(受保护配置)。"))
        gate = PermissionGate(rules_file=_rules_file(), audit_path=_audit_path())
        gate_ref, log_ref = gate, self.log
        _orig_decide = gate.decide

        def decide(command):
            ok, text = _orig_decide(command)
            log_ref("permission_" + ("allow" if ok else "deny"), command)
            return ok, text
        gate.decide = decide
        entries = {n: wrap_tool(e, gate, name=n) for n, e in entries.items()}
        entries = {n: hooks.wrap_tool(e) for n, e in entries.items()}
        if self.store:
            entries = skip_redo_tools(entries, self.store)
        else:
            entries = snapshotting_tools(entries, SessionStore(_tmp_store()))
        return entries

    # ---- 斜杠命令 ----
    def cmd_context(self):
        return (f"消息 {len(self.messages)} 条, "
                f"估算 ~{est_tokens(self.messages)} token")

    def cmd_budget(self):
        return "预算按回合计: 每回合 max_turns=10 / max_tokens=8000"

    def cmd_resume(self):
        if not self.store:
            return "本会话未启用 checkpoint"
        self._build_messages()
        return f"已恢复: {len(self.messages)} 条历史"

    def cmd_memory(self):
        return self.memory.recall() or "(记忆为空)"


_CACHE = {}


def _rules_file():
    if "rules" not in _CACHE:
        import tempfile
        p = Path(tempfile.mkdtemp(prefix="mh17_")) / "permissions.yaml"
        p.write_text(RULES_YAML)
        _CACHE["rules"] = p
    return _CACHE["rules"]


def _audit_path():
    if "audit" not in _CACHE:
        _CACHE["audit"] = Path(tempfile.mkdtemp(prefix="mh17_")) / "audit.log"
    return _CACHE["audit"]


def _tmp_store():
    import tempfile
    return Path(tempfile.mkdtemp(prefix="mh17_")) / "checkpoint.json"


def _empty_skills_dir():
    import tempfile
    p = Path(tempfile.mkdtemp(prefix="mh17_")) / "skills"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sandbox", default=".")
    ap.add_argument("--scripted", help="脚本化输入文件(每行一条), 验收用")
    ap.add_argument("--checkpoint")
    args = ap.parse_args()
    mh = MiniHarness(sandbox=args.sandbox, checkpoint=args.checkpoint)
    print("mini-harness v1.0 · /help 查看命令")
    if args.scripted:
        for line in Path(args.scripted).read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            print(f"\n>>> {line}")
            if line.startswith("/"):
                print(getattr(mh, "cmd_" + line[1:])())
            else:
                print(mh.turn(line))
    else:
        import readline  # noqa: F401 —— 方向键/历史
        while True:
            try:
                line = input("\n>>> ")
            except (EOFError, KeyboardInterrupt):
                break
            if not line.strip():
                continue
            if line == "/quit":
                break
            if line.startswith("/"):
                cmd = line[1:].split()[0]
                fn = getattr(mh, "cmd_" + cmd, None)
                print(fn() if fn else f"未知命令 /{cmd}")
            else:
                print(mh.turn(line))


if __name__ == "__main__":
    main()
