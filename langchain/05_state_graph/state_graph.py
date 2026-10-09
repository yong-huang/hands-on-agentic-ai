"""
05 · StateGraph 三件套：State、Reducer 与条件边

纯离线实验（不调用任何模型），五组确定性验证：
  A. 无 reducer 的并行写入 → InvalidUpdateError（先复现失败）
  B. 加 reducer → 并行分支的写入正确合并
  C. add_messages reducer → 消息只追加不覆盖
  D. 条件边循环 → 达标退出（带实际轮数断言）
  E. 轮次上限守卫 → 不达标时强制收束

用法:
  python langchain/05_state_graph/state_graph.py
"""

import operator
import sys
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


# ============================================================
# A/B. Reducer：并行写同一 key 的合并
# ============================================================

class PlainState(TypedDict):
    logs: list[str]
    total: int


class ReducerState(TypedDict):
    logs: Annotated[list[str], operator.add]
    total: Annotated[int, operator.add]


def make_branch_graph(state_schema):
    """两个并行分支各自写 logs/total，再汇聚。"""
    def branch_a(_):
        return {"logs": ["a"], "total": 1}

    def branch_b(_):
        return {"logs": ["b"], "total": 1}

    def merge(state):
        return {"logs": [f"merged:{sorted(state['logs'])}"]}

    g = StateGraph(state_schema)
    g.add_node("a", branch_a)
    g.add_node("b", branch_b)
    g.add_node("merge", merge)
    g.add_edge(START, "a")
    g.add_edge(START, "b")
    g.add_edge("a", "merge")
    g.add_edge("b", "merge")
    g.add_edge("merge", END)
    return g.compile()


def part_ab_reducer():
    section("[A] 复现：无 reducer 的并行写入报 InvalidUpdateError")
    try:
        make_branch_graph(PlainState).invoke({"logs": [], "total": 0})
        check("无 reducer 并行写报 InvalidUpdateError", False, "未抛出异常")
    except InvalidUpdateError as e:
        print(f"  报错原文: {str(e)[:100]}")
        check("无 reducer 并行写报 InvalidUpdateError",
              "one value per step" in str(e))

    section("[B] 修复：加 Annotated reducer 后正确合并")
    result = make_branch_graph(ReducerState).invoke({"logs": [], "total": 0})
    print(f"  合并结果: total={result['total']}, logs={result['logs']}")
    check("并行分支写入被 reducer 合并",
          result["total"] == 2 and sorted(result["logs"][:2]) == ["a", "b"])


# ============================================================
# C. add_messages：消息只追加不覆盖
# ============================================================

class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def part_c_messages():
    section("[C] add_messages reducer：消息只追加不覆盖")

    def ask(_):
        return {"messages": [HumanMessage("你好")]}

    def reply(state):
        return {"messages": [AIMessage(f"收到 {len(state['messages'])} 条消息")]}

    g = StateGraph(ChatState)
    g.add_node("ask", ask)
    g.add_node("reply", reply)
    g.add_edge(START, "ask")
    g.add_edge("ask", "reply")
    g.add_edge("reply", END)
    result = g.compile().invoke({"messages": []})
    print(f"  消息序列: {[(type(m).__name__, m.content) for m in result['messages']]}")
    check("两次节点写入被合并为两条消息",
          len(result["messages"]) == 2
          and isinstance(result["messages"][0], HumanMessage)
          and isinstance(result["messages"][1], AIMessage))


# ============================================================
# D/E. 条件边循环 + 轮次上限守卫
# ============================================================

class DraftState(TypedDict):
    draft: str
    score: int
    rounds: int
    max_rounds: int
    path: Annotated[list[str], operator.add]


TARGET_SCORE = 10
SUFFIX = "（补充说明）"


def build_loop_graph():
    def write(state):
        return {"draft": "草稿", "rounds": 0, "path": ["write"]}

    def critic(state):
        return {"score": len(state["draft"]), "path": ["critic"]}

    def revise(state):
        return {
            "draft": state["draft"] + SUFFIX,
            "rounds": state["rounds"] + 1,
            "path": [f"revise#{state['rounds'] + 1}"],
        }

    def route(state):
        if state["score"] >= TARGET_SCORE:
            return "done"
        if state["rounds"] >= state["max_rounds"]:
            return "give_up"
        return "revise"

    def done(state):
        return {"path": ["done"]}

    def give_up(state):
        return {"path": ["give_up"]}

    g = StateGraph(DraftState)
    for name, fn in [("write", write), ("critic", critic), ("revise", revise),
                     ("done", done), ("give_up", give_up)]:
        g.add_node(name, fn)
    g.add_edge(START, "write")
    g.add_edge("write", "critic")
    g.add_conditional_edges("critic", route,
                            {"revise": "revise", "done": "done", "give_up": "give_up"})
    g.add_edge("revise", "critic")
    g.add_edge("done", END)
    g.add_edge("give_up", END)
    return g.compile()


def part_de_loop():
    section("[D] 条件边循环：达标退出")
    g = build_loop_graph()
    result = g.invoke({"draft": "", "score": 0, "rounds": 0,
                       "max_rounds": 5, "path": []})
    print(f"  路径: {' → '.join(result['path'])}")
    print(f"  最终: score={result['score']} rounds={result['rounds']}")
    check("循环在 score≥10 时经 done 退出",
          result["path"][-1] == "done" and result["score"] >= TARGET_SCORE
          and result["rounds"] == 2,
          f"实际轮数={result['rounds']}")

    section("[E] 轮次上限守卫：不达标时强制收束")
    result2 = g.invoke({"draft": "", "score": 0, "rounds": 0,
                        "max_rounds": 1, "path": []})
    print(f"  路径: {' → '.join(result2['path'])}")
    check("达到 max_rounds 后经 give_up 收束",
          result2["path"][-1] == "give_up" and result2["rounds"] == 1,
          f"实际轮数={result2['rounds']}")


def main():
    print("=" * 64)
    print("[05] StateGraph 三件套：State、Reducer 与条件边（纯离线）")
    print("=" * 64)

    part_ab_reducer()
    part_c_messages()
    part_de_loop()

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
