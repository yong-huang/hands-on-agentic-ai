#!/usr/bin/env python3
"""15 · MCP 动态工具 — 外部工具先过权限门 (docs/harness.md 项目 15)

interview/19-20 的进阶: MCP 工具不是"直接信"。
流程: 启动书店 MCP server(interview/19 夹具) → list_tools 动态注册 →
每个 MCP 工具包上 07 权限门 → 真机 agent 查库存+下单。

规则: query_stock/sales_stats allow, place_order ask(脚本注入批准)。
验收:
  ① 动态发现 ≥3 个工具且模型能调用
  ② place_order 命中 ask 拦截, 脚本批准后调用成功
  ③ audit.log 有 MCP 工具判定记录

用法:
  python3 demo.py            # 真机
  MOCK=1 python3 demo.py     # 离线(不启动 MCP, 只验管道)
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh import loop  # noqa: E402
from mh.mcp_client import MCPBridge, mcp_tools  # noqa: E402
from mh.permissions import PermissionGate, wrap_tool  # noqa: E402

RULES_YAML = """\
rules:
  - {pattern: "place_order*", decision: ask,   reason: "下单涉及真实交易, 需人工确认"}
  - {pattern: "query_stock*", decision: allow, reason: "只读查询"}
  - {pattern: "sales_stats*", decision: allow, reason: "只读统计"}
"""

TASK = ("帮我在书店完成一笔交易: 先查询 sku=A1 的库存, 然后下单购买 2 本, "
        "最后汇报订单号与金额。")


def scripted_ask(answers):
    seq = iter(answers)

    def _ask(command, rule):
        ans = next(seq, "n")
        print(f"  [ask] {command[:40]} → {ans}")
        return ans == "y", "人工批准" if ans == "y" else "人工拒绝"
    return _ask


def main():
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    if os.environ.get("MOCK") == "1":
        print("MOCK: MCP 管道无离线模式(依赖真实 server), 跳过")
        return

    server = Path("..") / ".." / "interview" / "19_mcp_server" / "mcp_server.py"
    bridge = MCPBridge(server)
    bridge.start()
    discovered = bridge.list_tools()
    print(f"① MCP 发现 {len(discovered)} 个工具: {[t[0] for t in discovered]}")

    lab = Path(tempfile.mkdtemp(prefix="mh15_"))
    rules = lab / "permissions.yaml"
    rules.write_text(RULES_YAML)
    gate = PermissionGate(rules_file=rules, audit_path=lab / "audit.log",
                          ask_fn=scripted_ask(["y"]))

    tools = {}
    for name, entry in mcp_tools(bridge).items():
        tools[name] = wrap_tool(entry, gate, name=name)

    result = loop.run_agent(TASK, tools, max_turns=8)
    print("\n===== 工具轨迹 =====")
    for tr in result["tool_trace"]:
        print(f"  {tr['tool']}({json.dumps(tr['args'], ensure_ascii=False)[:50]}) "
              f"→ {tr['result'][:70]}")
    print(f"最终回答: {result['final'][:100]}")

    audit = (lab / "audit.log").read_text().strip().splitlines()
    placed = any("place_order" in tr["tool"] for tr in result["tool_trace"]) \
        and any("allow" in l and "place_order" in l for l in audit)
    mcp_audits = [l for l in audit if "place_order" in l or "query_stock" in l]
    print("\n===== 验收 =====")
    print(f"① 动态发现 ≥3 工具: {'✅' if len(discovered) >= 3 else '❌'}")
    print(f"② place_order 被 ask 拦截→批准→成功: {'✅' if placed else '❌'}")
    print(f"③ audit.log MCP 记录: {'✅' if mcp_audits else '❌'} ({len(mcp_audits)} 条)")
    bridge.close()
    sys.exit(0 if (len(discovered) >= 3 and placed and mcp_audits) else 1)


if __name__ == "__main__":
    main()
