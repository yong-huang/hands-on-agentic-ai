"""
01 · LCEL 与 Runnable 协议

LCEL（LangChain Expression Language）用 | 把组件拼成链；拼出来的对象都实现
同一套 Runnable 协议——invoke / batch / stream 三种调用方式在任何链上通用。

本实验两条链：
  A. 纯计算报告链（无 LLM）：验证三种调用方式结果一致
  B. 分诊链（RunnableBranch + 真 LLM）：按关键词路由到不同提示词

用法:
  python langchain/01_lcel/lcel.py          # 真机（需本机 Ollama）
  python langchain/01_lcel/lcel.py --demo   # 离线演示（FakeListChatModel）
"""

import os
import sys
import time
from urllib.request import urlopen

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    RunnableBranch,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)

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


# ============================================================
# A. 纯计算链 — 验证 Runnable 协议的三种调用方式
# ============================================================

def build_report_chain():
    """RunnableParallel 同时算三个指标，RunnableLambda 合并渲染。"""
    stats = RunnableParallel(
        raw=RunnablePassthrough(),
        chars=RunnableLambda(len),
        words=RunnableLambda(lambda t: len(t.split())),
    )

    def render(d):
        return f"{d['raw']!r} -> {d['chars']} 字符 / {d['words']} 词"

    return stats | RunnableLambda(render)


def part_a_report():
    section("[A] 纯计算链：invoke / batch / stream 结果一致")
    chain = build_report_chain()
    inputs = ["hello lcel world", "Runnable 协议"]
    print(f"  输入: {inputs}")

    one_by_one = [chain.invoke(x) for x in inputs]
    batched = chain.batch(inputs)
    print(f"  逐条 invoke : {one_by_one}")
    print(f"  batch       : {batched}")
    check("batch 结果 == 逐条 invoke（顺序一致）", one_by_one == batched)

    streamed = "".join(chain.stream(inputs[0]))
    direct = chain.invoke(inputs[0])
    print(f"  stream 拼接 : {streamed!r}")
    check("stream 拼接 == invoke", streamed == direct)


# ============================================================
# B. 分诊链 — RunnableBranch 路由 + 真机流式
# ============================================================

ROUTE_LOG = []


def tagged(label, chain):
    """在分支开头打一个路由标记（旁路副作用，数据原样透传）。"""

    def _tag(x):
        ROUTE_LOG.append(label)
        return x

    return RunnableLambda(_tag) | chain


def build_triage_chain(llm):
    prompts = {
        "code": ChatPromptTemplate.from_messages([
            ("system", "你是代码审查员。用一句话指出下面描述里的代码问题。"),
            ("human", "{question}"),
        ]),
        "math": ChatPromptTemplate.from_messages([
            ("system", "你是数学助教。逐步计算，最后一行给出结果。"),
            ("human", "{question}"),
        ]),
        "general": ChatPromptTemplate.from_messages([
            ("system", "你是通用助手。用一句话回答。"),
            ("human", "{question}"),
        ]),
    }
    chains = {k: tagged(k, p | llm | StrOutputParser()) for k, p in prompts.items()}

    def is_code(x):
        q = x["question"].lower()
        return "代码" in q or "code" in q

    def is_math(x):
        q = x["question"]
        return any(w in q for w in ("计算", "数学", "+", "加"))

    branch = RunnableBranch(
        (is_code, chains["code"]),
        (is_math, chains["math"]),
        chains["general"],
    )
    return {"question": RunnablePassthrough()} | branch


def part_b_triage(llm, demo=False):
    section("[B] 分诊链：RunnableBranch 按关键词路由")
    chain = build_triage_chain(llm)
    questions = [
        "这段代码在 for 循环里反复查询数据库，有什么问题？",
        "计算 21 + 21 等于多少？",
        "用一句话介绍巴黎。",
    ]

    results = chain.batch(questions, config={"max_concurrency": 1} if demo else None)
    for q, r in zip(questions, results):
        print(f"  Q: {q}\n  A: {r.strip()[:90]}")

    hit = sorted(set(ROUTE_LOG))
    check("三个问题命中三条分支", hit == ["code", "general", "math"], f"命中={hit}")
    check("batch 返回三条非空答案", all(r.strip() for r in results))

    one_by_one = [chain.invoke(q) for q in questions]
    check("LLM 链 batch == 逐条 invoke", one_by_one == results)

    q = "计算 21 + 21 等于多少？"
    # demo 的 FakeListChatModel 每次调用按序消耗响应，会让两次调用错位；
    # 流式对比换一个单响应假模型（每次调用都返回同一句）
    if demo:
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        chain = build_triage_chain(FakeListChatModel(responses=["（演示）21 + 21 = 42。"]))
    t0 = time.time()
    gen = chain.stream(q)
    first = next(gen)
    ttft = time.time() - t0
    streamed = first + "".join(gen)
    direct = chain.invoke(q)
    print(f"  首 token 延迟 {ttft:.2f}s，流式 {len(streamed)} 字符：{streamed.strip()[:60]}")
    check("LLM 链 stream 拼接 == invoke", streamed == direct)


def main():
    demo = "--demo" in sys.argv
    print("=" * 64)
    print("[01] LCEL 与 Runnable 协议")
    print(f"模式: {'离线演示（FakeListChatModel）' if demo else f'真机（{MODEL}）'}")
    print("=" * 64)

    part_a_report()

    if demo:
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        llm = FakeListChatModel(responses=[
            "（演示）循环内查询数据库会产生 N+1 查询，应改为一次批量查询。",
            "（演示）21 + 21 = 42。",
            "（演示）巴黎是法国的首都。",
        ])
        part_b_triage(llm, demo=True)
    else:
        from langchain_ollama import ChatOllama

        if not ollama_alive():
            print("\n⏭️ Ollama 未启动，真机部分无法运行：先 `ollama serve`，"
                  "或加 `--demo` 看离线行为")
            return 2
        llm = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_predict=256)
        part_b_triage(llm)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
