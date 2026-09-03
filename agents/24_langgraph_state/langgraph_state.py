"""
LangGraph 状态管理 — 用 StateGraph 编排带条件边与循环的多步工作流

项目 08 的 Plan-and-Execute 是手写的三段架构。本篇把"写作-评审-修订"这种
需要循环与条件跳转的流程交给 LangGraph: 状态 (TypedDict) 在节点间流动,
每个节点读写状态的一部分; 条件边决定"评审不通过就回炉修订", 循环次数
用状态里的计数器控制。

两种模式:
  真实模式: 每个节点调 qwen3.8 (大纲/初稿/评审/修订都是 LLM 任务)
  --demo : 节点函数换成确定性文本变换, 图结构照常运行 (离线)

核心概念:
- State (TypedDict): 全局共享状态, 节点返回 partial update
- Node: 读状态 -> 干活 -> 返回增量
- Conditional Edge: 按状态决定下一个节点 (评审通过否?)
"""

import os
import sys
import requests
from typing import TypedDict

from langgraph.graph import StateGraph, END

MODEL = "qwen3.8:latest"
MAX_ITERATIONS = 2
PASS_SCORE = 8
TOPIC = "上下文工程对 Agent 的重要性"


class ArticleState(TypedDict):
    topic: str          # 输入: 文章主题
    outline: str        # 大纲
    draft: str          # 当前稿
    critique: str       # 评审意见
    score: int          # 评审分 1-10
    iterations: int     # 已修订次数
    final: str          # 定稿


# ============================================================
# LLM 调用
# ============================================================

def llm(prompt, temperature=0.4):
    resp = requests.post("http://localhost:11434/api/chat", json={
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "stream": False, "think": False,
        "options": {"temperature": temperature, "num_predict": 400},
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


# ============================================================
# 真实节点: 每个节点读状态、调 LLM、返回增量
# ============================================================

def node_outline(state):
    outline = llm(f"为短文《{state['topic']}》列一个 3 点大纲，每点一行。")
    print("  [outline] 大纲就绪")
    return {"outline": outline}


def node_draft(state):
    draft = llm(f"按以下大纲写一篇 150 字左右的短文《{state['topic']}》:\n{state['outline']}")
    print(f"  [draft] 初稿 {len(draft)} 字")
    return {"draft": draft}


def node_critique(state):
    raw = llm(f"评审这篇短文，严格打分（1-10）并给一条最关键的修改意见。\n"
              f"输出格式:\n分数: N\n意见: ...\n\n{state['draft']}")
    score, _, opinion = raw.partition("\n")
    digits = "".join(c for c in score if c.isdigit())
    score = int(digits[:2] or 5)
    critique = opinion.strip() or raw
    print(f"  [critique] 评分 {score}/10, 意见: {critique[:40]}…")
    return {"critique": critique, "score": score}


def node_revise(state):
    revised = llm(f"按评审意见修改短文（保持 150 字左右）。\n\n"
                  f"原文:\n{state['draft']}\n\n评审意见:\n{state['critique']}")
    print(f"  [revise] 第 {state['iterations'] + 1} 次修订完成, {len(revised)} 字")
    return {"draft": revised, "iterations": state["iterations"] + 1}


def node_finalize(state):
    print(f"  [finalize] 定稿 (评分 {state['score']}, 修订 {state['iterations']} 次)")
    return {"final": state["draft"]}


# ============================================================
# Demo 节点: 确定性文本变换 (离线), 图结构照常运行
# ============================================================

def demo_outline(state):
    print("  [outline] 1. 是什么  2. 为什么重要  3. 怎么做")
    return {"outline": "1. 是什么\n2. 为什么重要\n3. 怎么做"}


def demo_draft(state):
    text = f"《{state['topic']}》初稿: 上下文工程决定 Agent 的上限……（demo 初稿）"
    print(f"  [draft] 初稿 {len(text)} 字")
    return {"draft": text}


def demo_critique(state):
    score = 7 if state["iterations"] == 0 else 9   # 第一次不过, 修订后通过
    print(f"  [critique] 评分 {score}/10 (demo 规则)")
    return {"critique": "补充一个实际案例", "score": score}


def demo_revise(state):
    text = state["draft"] + " 补充案例: 项目 16 的对照实验证明了注入的价值。"
    print(f"  [revise] 第 {state['iterations'] + 1} 次修订完成")
    return {"draft": text, "iterations": state["iterations"] + 1}


def demo_finalize(state):
    print(f"  [finalize] 定稿 (评分 {state['score']}, 修订 {state['iterations']} 次)")
    return {"final": state["draft"]}


# ============================================================
# 建图: 条件边控制"评审不通过 -> 回炉修订"的循环
# ============================================================

def should_continue(state):
    """条件边: 评分达标或修订次数用尽 -> 定稿; 否则回炉。"""
    if state["score"] >= PASS_SCORE or state["iterations"] >= MAX_ITERATIONS:
        return "finalize"
    return "revise"


def build_graph(nodes):
    g = StateGraph(ArticleState)
    g.add_node("outline", nodes["outline"])
    g.add_node("draft", nodes["draft"])
    g.add_node("critique", nodes["critique"])
    g.add_node("revise", nodes["revise"])
    g.add_node("finalize", nodes["finalize"])
    g.set_entry_point("outline")
    g.add_edge("outline", "draft")
    g.add_edge("draft", "critique")
    g.add_conditional_edges("critique", should_continue,
                            {"revise": "revise", "finalize": "finalize"})
    g.add_edge("revise", "critique")       # 修订后重新评审 (循环)
    g.add_edge("finalize", END)
    return g.compile()


# ============================================================
# 入口
# ============================================================

def run(mode):
    print("=" * 60)
    tag = "Demo 模式（确定性节点, 离线）" if mode == "demo" else "真实模式（节点 = qwen3.8）"
    print(f"LangGraph 状态管理 -- {tag}")
    print(f"任务: 写短文《{TOPIC}》, 评审 ≥{PASS_SCORE} 分或修订 {MAX_ITERATIONS} 次后定稿")
    print("=" * 60)

    if mode == "demo":
        nodes = {"outline": demo_outline, "draft": demo_draft,
                 "critique": demo_critique, "revise": demo_revise,
                 "finalize": demo_finalize}
    else:
        nodes = {"outline": node_outline, "draft": node_draft,
                 "critique": node_critique, "revise": node_revise,
                 "finalize": node_finalize}

    graph = build_graph(nodes)
    print("\n==> 图开始执行 (观察状态逐节点演化)")
    final = graph.invoke({"topic": TOPIC, "iterations": 0})

    print("\n--- 最终状态 ---")
    for key in ("score", "iterations", "outline", "draft", "critique", "final"):
        value = str(final.get(key, ""))[:60]
        print(f"  {key:12s} {value}")


if __name__ == "__main__":
    run("demo" if "--demo" in sys.argv else "real")
