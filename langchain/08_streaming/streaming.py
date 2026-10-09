"""
08 · 流式输出：四种 stream_mode 与事件流

两块内容：
  A. 四种流模式的离线结构验证（FakeListChatModel 逐字流）——values 快照 /
     updates 增量 / messages token / custom 自定义事件；流式拼出的最终状态
     与 invoke 结果一致
  B. 真机流式——messages 模式拿 token 级增量并与 invoke 对拍；
     astream_events 过滤模型 token 事件

用法:
  python langchain/08_streaming/streaming.py
  python langchain/08_streaming/streaming.py --demo   # 只跑离线 A
"""

import asyncio
import operator
import os
import sys
from typing import Annotated, TypedDict
from urllib.request import urlopen

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

MODEL = os.environ.get("LLM_MODEL", "qwen3.8:latest")
OLLAMA = "http://localhost:11434"
QUESTION = "请用一句话介绍杭州。"

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


class StreamState(TypedDict):
    q: str
    answer: str
    steps: Annotated[list[str], operator.add]


def build_graph(llm):
    def prepare(_state):
        return {"steps": ["prepare"]}

    def generate(state):
        writer = get_stream_writer()
        writer({"stage": "generate", "progress": 0.5})
        resp = llm.invoke(state["q"])
        writer({"stage": "generate", "progress": 1.0})
        content = resp.content
        if isinstance(content, list):
            content = "".join(b.get("text", "") for b in content
                              if isinstance(b, dict))
        return {"answer": str(content), "steps": ["generate"]}

    g = StateGraph(StreamState)
    g.add_node("prepare", prepare)
    g.add_node("generate", generate)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "generate")
    g.add_edge("generate", END)
    return g.compile()


def initial():
    return {"q": QUESTION, "answer": "", "steps": []}


# ============================================================
# A. 四种 stream_mode（离线，假模型逐字流）
# ============================================================

def part_a_modes():
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    section("[A] 四种 stream_mode 的结构（离线）")
    fake_text = "杭州是浙江省会，以西湖闻名。"
    app = build_graph(FakeListChatModel(responses=[fake_text]))

    snapshots = list(app.stream(initial(), stream_mode="values"))
    final_stream = snapshots[-1]
    final_invoke = app.invoke(initial())
    print(f"  values 快照 {len(snapshots)} 个，最终: {final_stream['answer']}")
    check("values：快照逐层生长，最终状态与 invoke 一致",
          len(snapshots) >= 3 and final_stream == final_invoke)

    updates = list(app.stream(initial(), stream_mode="updates"))
    node_keys = [k for u in updates for k in u]
    print(f"  updates 增量节点: {node_keys}")
    check("updates：按节点给出增量", "prepare" in node_keys and "generate" in node_keys)

    chunks = list(app.stream(initial(), stream_mode="messages"))
    texts = [c[0].content for c in chunks]
    nodes = {c[1].get("langgraph_node") for c in chunks}
    print(f"  messages 分片 {len(chunks)} 个，来源节点: {nodes}")
    check("messages：token 级分片且带节点元数据",
          len(chunks) >= 3 and nodes == {"generate"}
          and "".join(texts) == fake_text)

    custom = list(app.stream(initial(), stream_mode="custom"))
    print(f"  custom 事件: {custom}")
    check("custom：图内自定义进度事件按序到达",
          [c["progress"] for c in custom] == [0.5, 1.0])


# ============================================================
# B. 真机流式与事件流
# ============================================================

async def collect_events(app):
    token_texts = []
    event_names = set()
    async for ev in app.astream_events(initial(), version="v2"):
        event_names.add(ev["event"])
        if ev["event"] == "on_chat_model_stream":
            token_texts.append(ev["data"]["chunk"].content)
    return token_texts, event_names


def part_b_real(llm):
    section("[B] 真机：messages token 流与 astream_events（真机）")
    app = build_graph(llm)

    chunks = list(app.stream(initial(), stream_mode="messages"))
    streamed = "".join(c[0].content for c in chunks).strip()
    print(f"  messages: {len(chunks)} 个 token 分片，拼接: {streamed[:46]}")
    check("真机 token 级流式分片数 ≥ 5", len(chunks) >= 5)

    invoked = app.invoke(initial())["answer"].strip()
    print(f"  invoke 对照: {invoked[:46]}")
    check("流式拼接结果与 invoke 一致", streamed == invoked)

    tokens, names = asyncio.run(collect_events(app))
    joined = "".join(tokens)
    print(f"  astream_events: {len(tokens)} 个模型 token 事件；"
          f"事件种类 {sorted(names)}")
    check("astream_events 捕获模型 token 事件",
          len(tokens) >= 5 and "on_chat_model_start" in names
          and "on_chat_model_end" in names
          and joined.strip() == invoked)


def main():
    demo = "--demo" in sys.argv
    print("=" * 64)
    print("[08] 流式输出：四种 stream_mode 与事件流")
    print(f"模式: {'离线演示（只跑 A 段）' if demo else f'真机（{MODEL}）'}")
    print("=" * 64)

    part_a_modes()

    if demo:
        print("\n  （--demo 只运行四种流模式的结构验证；B 段需要 Ollama 与真机模型）")
    else:
        from langchain_ollama import ChatOllama

        if not ollama_alive():
            print("\n⏭️ Ollama 未启动，真机部分无法运行：先 `ollama serve`，"
                  "或加 `--demo` 看离线行为")
            return 2
        llm = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_predict=128)
        part_b_real(llm)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
