"""mh.permissions — 权限门 (项目 07): allow / ask / deny 三档 + HITL + 审计

"The model decides what to do. The harness decides what's allowed."
规则从 YAML 读取, fnmatch 模式匹配命令, 首条命中生效:
  allow: 直通
  ask:   暂停, 交给人决定(HITL interrupt) —— 非交互场景用可注入的 ask_fn
  deny:  自动拒绝, 拒绝原因回喂模型
每次判定写 audit.log(时间戳·命令·判定·命中规则), 01 的"判分铁证"哲学:
权限也要留痕。

与工具层的接法: wrap_tool(entry, gate) 返回包了权限门的工具表条目 ——
拦截点在意图与副作用之间(02 解剖图的位置)。
"""

import fnmatch
import json
import os
import re
import time
from pathlib import Path

import yaml

_DEFAULT_RULES = [
    {"pattern": "rm*", "decision": "deny", "reason": "删除类命令默认禁止"},
    {"pattern": "pip install*", "decision": "ask", "reason": "安装需人工确认"},
    {"pattern": "ls*", "decision": "allow", "reason": "只读直通"},
]


class PermissionGate:
    def __init__(self, rules=None, rules_file=None, audit_path=None,
                 ask_fn=None, default="deny"):
        if rules_file:
            self.rules = yaml.safe_load(Path(rules_file).read_text())["rules"]
        else:
            self.rules = rules or _DEFAULT_RULES
        self.audit_path = Path(audit_path) if audit_path else None
        self.ask_fn = ask_fn or self._tty_ask
        self.default = default  # 无规则命中时的兜底(安全默认: 拒绝)

    @staticmethod
    def _tty_ask(command, rule) -> tuple:
        """终端 HITL: y 放行 / n 拒绝。"""
        ans = input(f"\n[权限门·ask] 命中规则 {rule['pattern']}({rule.get('reason', '')})\n"
                    f"  命令: {command}\n  允许执行? [y/N] ").strip().lower()
        return ans == "y", "人工批准" if ans == "y" else "人工拒绝"

    @staticmethod
    def _segments(command: str):
        """命令链拆分: && / || / ; / 管道 逐段独立判定。
        17 总装实测: 模型会把 rm 藏进 `echo ... && rm ...`, 整串前缀匹配
        会被 echo* 放行 —— 链感知后任一段命中 deny/ask 即生效(最严者胜)。"""
        return [s.strip() for s in re.split(r"&&|\|\||;|\|", command) if s.strip()]

    def check(self, command: str) -> tuple:
        """返回 (decision, rule) —— 对命令链逐段判定, 最严者胜。"""
        order = {"deny": 0, "ask": 1, "allow": 2}
        default_rule = {"pattern": "(default)",
                        "reason": "无规则命中, 安全默认"}
        decisions = []
        for seg in self._segments(command):
            hit = None
            for rule in self.rules:
                if fnmatch.fnmatch(seg, rule["pattern"]):
                    hit = (rule.get("decision", "deny"), rule)
                    break
            decisions.append(hit or (self.default, default_rule))
        if not decisions:
            return self.default, default_rule
        decisions.sort(key=lambda d: order.get(d[0], 0))
        return decisions[0]

    def audit(self, command: str, decision: str, rule: dict, note: str = ""):
        if not self.audit_path:
            return
        self.audit_path.parent.mkdir(exist_ok=True)
        with self.audit_path.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{decision}\t"
                    f"{rule['pattern']}\t{command[:80]}\t{note}\n")

    def decide(self, command: str) -> tuple:
        """对一条命令做权限判定, 返回 (ok: bool, 回喂文本)。"""
        decision, rule = self.check(command)
        note = ""
        if decision == "ask":
            ok, note = self.ask_fn(command, rule)
            decision = "allow" if ok else "deny"
        elif decision == "allow":
            ok = True
        else:
            ok = False
        text = (f"[权限放行]" if ok else
                f"[权限拒绝] 命中规则 {rule['pattern']}: "
                f"{rule.get('reason', '未说明原因')}。请改用其他方案完成任务。")
        self.audit(command, decision, rule, note)
        return ok, text


def wrap_tool(entry: dict, gate: PermissionGate, name: str = None) -> dict:
    """给工具表条目套上权限门: 拦截在执行之前。

    匹配串优先取 args.command(bash 类工具), 否则用 "工具名 参数"
    (MCP 等结构化工具) —— 规则 pattern 如 "place_order*" 两者通吃。
    """
    tool_name = name or entry["fn"].__name__
    origin = entry["fn"]

    def gated(cwd=None, **args):
        command = args.get("command") or f"{tool_name} {json.dumps(args, ensure_ascii=False)}"
        ok, text = gate.decide(command)
        if not ok:
            return f"[error] {text}"
        return origin(cwd=cwd, **args)

    gated.__name__ = tool_name
    out = dict(entry)
    out["fn"] = gated
    return out
