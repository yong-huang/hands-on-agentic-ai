"""
07 · interrupt 与 Human-in-the-loop

两块内容：
  A. 节点级中断（离线）— 自定义审批闸门节点：interrupt() 暂停整个人工
     决策点，Command(resume=...) 分别回放 approve / edit / reject 三种决策
  B. 工具级中断（真机）— HumanInTheLoopMiddleware 在危险工具执行前暂停，
     三种决策的真实差异：approve 原样执行、edit 用修改后的参数执行、
     reject 不执行并给模型拒绝理由

用法:
  python langchain/07_interrupt_hitl/interrupt_hitl.py
  python langchain/07_interrupt_hitl/interrupt_hitl.py --demo   # 只跑离线 A
"""

import operator
import os
import sys
from typing import Annotated, TypedDict
from urllib.request import urlopen

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

MODEL = os.environ.get("LLM_MODEL", "qwen3.8:latest")
OLLAMA = "http://localhost:11434"

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def ollama_alive():
    try:
        with urlopen(f"{OLLAMA}/v1/models", timeout=3):
            return True
    except Exception:
        return False


def _text(msg):
    content = getattr(msg, "content", msg)
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)


# ============================================================
# A. 节点级中断：自定义审批闸门（离线）
# ============================================================

class ApprovalState(TypedDict):
    action: str
    payload: dict
    decision: dict
    executed: Annotated[list[str], operator.add]
    notes: Annotated[list[str], operator.add]


def propose(_state):
    return {"action": "delete_file", "payload": {"path": "old.txt"}}


def review(state):
    # interrupt() 抛出暂停信号：把审批问题交给调用方，整个人工决策点挂起
    decision = interrupt({
        "question": f"是否执行 {state['action']}?",
        "args": state["payload"],
        "options": ["approve", "edit", "reject"],
    })
    return {"decision": dict(decision)}


def act(state):
    d = state["decision"]
    if d["type"] == "approve":
        return {"executed": [f"{state['action']}({state['payload']['path']})"]}
    if d["type"] == "edit":
        return {"executed": [f"{state['action']}({d['args']['path']})"]}
    return {"notes": [f"rejected: {d.get('message', '(无理由)')}"]}


def build_approval_graph():
    g = StateGraph(ApprovalState)
    g.add_node("propose", propose)
    g.add_node("review", review)
    g.add_node("act", act)
    g.add_edge(START, "propose")
    g.add_edge("propose", "review")
    g.add_edge("review", "act")
    g.add_edge("act", END)
    return g.compile(checkpointer=InMemorySaver())


def part_a_node_level():
    section("[A] 节点级中断：interrupt 暂停 + Command(resume) 三种决策（离线）")
    graph = build_approval_graph()
    init = {"action": "", "payload": {}, "decision": {},
            "executed": [], "notes": []}

    cfg = {"configurable": {"thread_id": "a1"}}
    paused = graph.invoke(dict(init), cfg)
    gate = paused["__interrupt__"][0].value
    print(f"  暂停时的问题: {gate['question']} args={gate['args']}")
    check("审批闸门在动作执行前暂停", "delete_file" in gate["question"]
          and gate["options"] == ["approve", "edit", "reject"])

    approved = graph.invoke(Command(resume={"type": "approve"}), cfg)
    print(f"  approve -> executed={approved['executed']}")
    check("approve：原参数执行", approved["executed"] == ["delete_file(old.txt)"])

    cfg2 = {"configurable": {"thread_id": "a2"}}
    graph.invoke(dict(init), cfg2)
    edited = graph.invoke(Command(resume={
        "type": "edit", "args": {"path": "old-v2.txt"},
    }), cfg2)
    print(f"  edit    -> executed={edited['executed']}")
    check("edit：用修改后的参数执行",
          edited["executed"] == ["delete_file(old-v2.txt)"])

    cfg3 = {"configurable": {"thread_id": "a3"}}
    graph.invoke(dict(init), cfg3)
    rejected = graph.invoke(Command(resume={
        "type": "reject", "message": "先不删了",
    }), cfg3)
    print(f"  reject  -> executed={rejected['executed']} notes={rejected['notes']}")
    check("reject：不执行且记录理由",
          rejected["executed"] == [] and "先不删了" in rejected["notes"][0])


# ============================================================
# B. 工具级中断：HumanInTheLoopMiddleware（真机）
# ============================================================

DELETED = []


def part_b_middleware(llm):
    from langchain.agents import create_agent
    from langchain.agents.middleware import HumanInTheLoopMiddleware
    from langchain_core.tools import tool

    section("[B] 工具级中断：中间件在危险工具前暂停（真机）")

    @tool
    def delete_file(path: Annotated[str, "要删除的文件路径"]) -> str:
        """删除指定文件（记录到审计列表）。"""
        DELETED.append(path)
        return f"已删除 {path}"

    agent = create_agent(
        model=llm, tools=[delete_file],
        middleware=[HumanInTheLoopMiddleware(
            interrupt_on={"delete_file": {
                "allowed_decisions": ["approve", "edit", "reject"],
            }},
        )],
        checkpointer=InMemorySaver(),
        system_prompt="用户要求删除文件时必须调用 delete_file 工具。",
    )
    init_msg = {"messages": [HumanMessage("请删除 old.txt 文件。")]}

    # ---- approve ----
    DELETED.clear()
    cfg = {"configurable": {"thread_id": "b1"}}
    r = agent.invoke(dict(init_msg), cfg)
    iv = r.get("__interrupt__")
    print(f"  approve 场景暂停: {'delete_file' in str(iv[0].value) if iv else False}")
    check("危险工具执行前中断", bool(iv) and "delete_file" in str(iv[0].value))
    r = agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg)
    print(f"  approve -> 审计列表: {DELETED}")
    check("approve：工具按原参数执行", DELETED == ["old.txt"])

    # ---- edit ----
    DELETED.clear()
    cfg2 = {"configurable": {"thread_id": "b2"}}
    agent.invoke(dict(init_msg), cfg2)
    r2 = agent.invoke(Command(resume={"decisions": [{
        "type": "edit",
        "edited_action": {"name": "delete_file",
                          "args": {"path": "archive/old.txt"}},
    }]}), cfg2)
    print(f"  edit    -> 审计列表: {DELETED}")
    check("edit：工具收到修改后的参数",
          DELETED == ["archive/old.txt"])

    # ---- reject ----
    DELETED.clear()
    cfg3 = {"configurable": {"thread_id": "b3"}}
    agent.invoke(dict(init_msg), cfg3)
    r3 = agent.invoke(Command(resume={"decisions": [{
        "type": "reject", "message": "不要删，先保留。",
    }]}), cfg3)
    rejection_msgs = [m for m in r3["messages"]
                      if type(m).__name__ == "ToolMessage"
                      and "rejected" in _text(m)]
    print(f"  reject  -> 审计列表: {DELETED}，"
          f"拒绝消息 {len(rejection_msgs)} 条")
    check("reject：工具未执行且模型收到拒绝理由",
          DELETED == [] and bool(rejection_msgs))


def main():
    demo = "--demo" in sys.argv
    print("=" * 64)
    print("[07] interrupt 与 Human-in-the-loop")
    print(f"模式: {'离线演示（只跑 A 段）' if demo else f'真机（{MODEL}）'}")
    print("=" * 64)

    part_a_node_level()

    if demo:
        print("\n  （--demo 只运行节点级中断；B 段需要 Ollama 与真机模型）")
    else:
        from langchain_ollama import ChatOllama

        if not ollama_alive():
            print("\n⏭️ Ollama 未启动，真机部分无法运行：先 `ollama serve`，"
                  "或加 `--demo` 看离线行为")
            return 2
        llm = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_predict=256)
        part_b_middleware(llm)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
