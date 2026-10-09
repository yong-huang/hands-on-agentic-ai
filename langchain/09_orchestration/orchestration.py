"""
09 · 编排原语：Send 动态扇出与 Command 监督者路由

纯离线实验（不调用任何模型），两块编排：
  A. Send map-reduce — 输入 N 篇文档，条件边扇出 N 个并行分支，每个分支
     跑独立编译的子图，reducer 聚合结果（N=3 与 N=7 两次验证）
  B. Command 监督者 — 节点返回 Command(goto=..., update=...) 决定下一跳，
     实现按问题类型路由 + worker 间 handoff，路由轨迹写进 audit 可审计

用法:
  python langchain/09_orchestration/orchestration.py
"""

import operator
import sys
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


# ============================================================
# A. Send map-reduce：动态扇出 + 子图作节点
# ============================================================

class SubState(TypedDict):
    doc: str
    results: Annotated[list[str], operator.add]
    total: Annotated[int, operator.add]


def summarize(state):
    """子图里的处理节点：给单篇文档生成摘要标记。"""
    return {"results": [f"摘要({state['doc']})"], "total": 1}


def build_subgraph():
    g = StateGraph(SubState)
    g.add_node("summarize", summarize)
    g.add_edge(START, "summarize")
    g.add_edge("summarize", END)
    return g.compile()


class MapState(TypedDict):
    docs: list[str]
    results: Annotated[list[str], operator.add]
    total: Annotated[int, operator.add]


def build_map_reduce(subgraph):
    def fanout(state):
        # Send 只在路由函数里返回：按输入列表长度动态生成 N 个分支
        return [Send("process", {"doc": d}) for d in state["docs"]]

    g = StateGraph(MapState)
    g.add_node("process", subgraph)      # 编译好的子图直接当节点用
    g.add_conditional_edges(START, fanout)
    g.add_edge("process", END)
    return g.compile()


def part_a_map_reduce():
    section("[A] Send 动态扇出 + 子图 map-reduce（离线）")
    subgraph = build_subgraph()
    app = build_map_reduce(subgraph)

    for n in (3, 7):
        docs = [f"doc-{i}" for i in range(1, n + 1)]
        updates = list(app.stream(
            {"docs": docs, "results": [], "total": 0}, stream_mode="updates"))
        process_events = sum(1 for u in updates if "process" in u)
        final = app.invoke({"docs": docs, "results": [], "total": 0})
        print(f"  N={n}: process 事件 {process_events} 个, "
              f"total={final['total']}, 聚合 {len(final['results'])} 条")
        check(f"N={n} 时并行分支数 = {n}（按事件计数）",
              process_events == n and final["total"] == n)
        check(f"N={n} 时聚合结果完整",
              sorted(final["results"]) == sorted(f"摘要(doc-{i})"
                                                 for i in range(1, n + 1)))

    solo = subgraph.invoke({"doc": "solo", "results": [], "total": 0})
    print(f"  子图独立运行: {solo}")
    check("子图独立编译、可单独运行；父图最终只含自身 key",
          solo["results"] == ["摘要(solo)"]
          and set(app.invoke({"docs": ["x"], "results": [], "total": 0}).keys())
          == {"docs", "results", "total"})


# ============================================================
# B. Command 监督者：路由 + 交接
# ============================================================

class SupState(TypedDict):
    question: str
    draft: str
    audit: Annotated[list[str], operator.add]


def supervisor(state):
    q = state["question"]
    if "换算" in q:  # 换算类先给 researcher，由它决定是否交接
        return Command(goto="researcher",
                       update={"audit": ["supervisor → researcher"]})
    if any(w in q for w in ("算", "数", "统计")):
        return Command(goto="statistician",
                       update={"audit": ["supervisor → statistician"]})
    return Command(goto="researcher",
                   update={"audit": ["supervisor → researcher"]})


def researcher(state):
    # 研究者遇到换算类问题，把任务交接（handoff）给统计员
    if "换算" in state["question"]:
        return Command(goto="statistician",
                       update={"audit": ["researcher ⇢ statistician（交接）"]})
    return Command(
        goto="aggregate",
        update={"draft": f"资料整理：关于「{state['question']}」的要点",
                "audit": ["researcher 完成"]},
    )


def statistician(state):
    # handoff 后仍能读到原始问题：上下文不丢
    return Command(
        goto="aggregate",
        update={"draft": f"统计结果（基于问题「{state['question']}」）：42",
                "audit": ["statistician 完成"]},
    )


def aggregate(state):
    return {"draft": state["draft"] + " ｜ 已汇总",
            "audit": ["aggregate 汇总"]}


def build_supervisor_graph():
    g = StateGraph(SupState)
    for name, fn in [("supervisor", supervisor), ("researcher", researcher),
                     ("statistician", statistician), ("aggregate", aggregate)]:
        g.add_node(name, fn)
    g.add_edge(START, "supervisor")
    g.add_edge("aggregate", END)
    return g.compile()


def part_b_supervisor():
    section("[B] Command 监督者：路由、交接与审计（离线）")
    app = build_supervisor_graph()

    r_text = app.invoke({"question": "介绍杭州", "draft": "", "audit": []})
    print(f"  文本问题 audit: {r_text['audit']}")
    check("文本问题路由到 researcher",
          "supervisor → researcher" in r_text["audit"]
          and r_text["draft"].startswith("资料整理"))

    r_math = app.invoke({"question": "统计一下销售额", "draft": "", "audit": []})
    print(f"  数学问题 audit: {r_math['audit']}")
    check("数学问题路由到 statistician",
          "supervisor → statistician" in r_math["audit"]
          and r_math["draft"].startswith("统计结果"))

    r_handoff = app.invoke({"question": "把 12 公里换算成英里",
                            "draft": "", "audit": []})
    print(f"  交接场景 audit: {r_handoff['audit']}")
    print(f"  交接场景 draft: {r_handoff['draft']}")
    check("worker 间 handoff 且上下文不丢",
          "researcher ⇢ statistician（交接）" in r_handoff["audit"]
          and "把 12 公里换算成英里" in r_handoff["draft"])
    check("每次 goto 目标可从 audit 逐条列举",
          r_handoff["audit"][-1] == "aggregate 汇总"
          and len(r_handoff["audit"]) == 4)


def main():
    print("=" * 64)
    print("[09] 编排原语：Send 动态扇出与 Command 监督者路由（纯离线）")
    print("=" * 64)

    part_a_map_reduce()
    part_b_supervisor()

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
