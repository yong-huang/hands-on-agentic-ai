"""
Agentic RAG — 检索变成 Agent 的工具, 由模型自主决定查不查、查什么

普通 RAG (20-21) 是固定管线: 每个问题都无脑检索。Agentic RAG 把检索变成
Agent 手里的**工具**: 模型先看问题, 自主决定——
  {"action": "search", "query": "..."}   需要外部知识, 发起检索
  {"action": "answer", "answer": "..."}  已有足够信息, 直接回答
知识库没有的内容必须明确拒答 ("知识库中没有相关信息"), 不编造。

复用项目 21 的向量索引 (nomic-embed-text + Chroma)。
Demo 模式: 预置 LLM 决策脚本 + 伪向量, 离线走完整循环。
"""

import json
import os
import sys

import chromadb

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "21_vector_store"))
sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "20_doc_splitting"))

from vector_store import build_index, search, embed_fn          # noqa: E402
from doc_splitting import estimate_len                          # noqa: E402

MODEL = "qwen3.8:latest"
DEMO = "--demo" in sys.argv

SYSTEM_PROMPT = """你是基于知识库的问答助手。知识库主题: RAG 与 Agent 评估。

你可以使用一个工具:
- search(query): 在知识库中做语义检索, 返回最相关的文本块

每轮只输出一个 JSON 决策:
{"action": "search", "query": "要检索的问题"}
{"action": "answer", "answer": "给用户的最终回答"}

规则: 回答前先用 search 核实; 知识库中没有的信息, 必须明确说
"知识库中没有相关信息"，绝对不要编造。"""


# ============================================================
# 工具与决策解析
# ============================================================

def make_search(collection):
    def search_tool(query):
        hits = search(collection, query, top_k=3)
        if not hits:
            return "（知识库中未找到相关内容）"
        return "\n\n".join(f"[{h['id']}]\n{h['text']}" for h in hits)
    return search_tool


def extract_json(text):
    """两级回退 (代码围栏 -> 全文花括号), 与项目 08 同款。"""
    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ============================================================
# Agentic 循环
# ============================================================

def agentic_answer(collection, question, llm, max_rounds=3):
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}]
    for round_no in range(1, max_rounds + 1):
        raw = llm(messages)
        decision = extract_json(raw)
        if decision is None or "action" not in decision:
            print(f"  [round {round_no}] 决策解析失败: {raw[:60]}…")
            return "（决策解析失败）"
        if decision["action"] == "answer":
            print(f"  [round {round_no}] answer")
            return decision["answer"]
        print(f"  [round {round_no}] search: {decision['query']}")
        messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
        messages.append({"role": "user", "content": f"[search 结果]\n{make_search(collection)(decision['query'])}"})
    return "（达到最大轮数仍未给出答案）"


# ============================================================
# 真实 LLM / Demo 脚本
# ============================================================

def real_llm(messages):
    import requests
    resp = requests.post("http://localhost:11434/api/chat", json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": 0.0, "num_predict": 400},
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


class DemoLLM:
    """预置决策脚本: 模拟 LLM 的两轮决策 (真实模式由 qwen3.8 决定)。"""

    def __init__(self):
        self.script = iter([
            '{"action": "search", "query": "RAG 的三个步骤"}',
            '{"action": "answer", "answer": "RAG 的三个步骤是：切分文档并建立索引、'
            '按查询检索相关片段、把片段注入提示词后生成答案。"}',
        ])

    def __call__(self, messages):
        return next(self.script, '{"action": "answer", "answer": "（演示脚本结束）"}')


QUESTIONS = [
    "切分文档有什么讲究？",
    "量子力学的波函数坍缩应该怎么理解？",   # 知识库外 -> 应拒答
]


def run(mode):
    print("=" * 60)
    tag = "Demo 模式（预置决策脚本, 伪向量）" if mode == "demo" else "真实模式（qwen3.8 自主决策）"
    print(f"Agentic RAG -- {tag}")
    print("=" * 60)

    client = chromadb.PersistentClient(path=os.path.join(
        SCRIPT_DIR, "chroma_db_demo" if mode == "demo" else "chroma_db"))
    collection = client.get_or_create_collection("rag_chunks")
    build_index(collection)

    llm = DemoLLM() if mode == "demo" else real_llm
    questions = (["RAG 的三个步骤是什么？"] if mode == "demo" else QUESTIONS)
    for q in questions:
        print(f"\nQ: {q}")
        print(f"A: {agentic_answer(collection, q, llm)}")

    print("\n要点: 检索由模型自主发起——知识库内的问题先查后答,")
    print("      知识库外的问题明确拒答, 不编造。")


if __name__ == "__main__":
    run("demo" if "--demo" in sys.argv else "real")
