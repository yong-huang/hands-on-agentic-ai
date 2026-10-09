"""
10 · Agentic RAG：检索 + 评分回炉循环

真机实验（需要本机 Ollama：qwen3.8 对话 + nomic-embed-text 嵌入）。
  - 用本仓库 docs/ 下的 5 份 md 建向量知识库（切分 → 嵌入 → Chroma）
  - 图结构：retrieve → grade（相关性评分）→ 合格则 generate（带来源标注）；
    不合格先 rewrite（查询改写）回炉重试，重试仍不合格则 refuse（拒答）
  - 三个可答问题断言来源正确；一个库外问题断言"改写 ≥1 次后拒答"

用法:
  python langchain/10_agentic_rag/agentic_rag.py
"""

import operator
import os
import sys
import tempfile
from pathlib import Path
from typing import TypedDict
from urllib.request import urlopen

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

MODEL = os.environ.get("LLM_MODEL", "qwen3.8:latest")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
OLLAMA = "http://localhost:11434"
MAX_REWRITES = 1
TOP_K = 4

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
# 知识库构建
# ============================================================

def build_index(docs_dir: Path):
    from langchain_chroma import Chroma
    from langchain_ollama import OllamaEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=60)
    chunks = []
    files = sorted(docs_dir.glob("*.md"))
    for f in files:
        for c in splitter.split_text(f.read_text(encoding="utf-8")):
            chunks.append(Document(page_content=c, metadata={"source": f.name}))

    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    store = Chroma(collection_name="repo_docs",
                   embedding_function=embeddings,
                   persist_directory=tempfile.mkdtemp(prefix="rag_index_"))
    store.add_documents(chunks)
    return store, chunks, [f.name for f in files]


# ============================================================
# RAG 图
# ============================================================

class RagState(TypedDict):
    question: str
    query: str
    docs: list[str]
    doc_sources: list[str]
    sources: list[str]
    relevant: bool
    rewrites: int
    answer: str


class Relevance(BaseModel):
    relevant: bool = Field(description="资料与问题是否相关")
    reason: str = Field(description="一句话理由")


GRADE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "判断下面的资料能否回答用户问题。只依据资料内容，不要用你自己的知识。"),
    ("human", "问题：{question}\n\n资料：\n{context}"),
])

REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "把用户问题改写成更适合检索的表述：保留原意，补上关键实体词，只输出改写后的问句。"),
    ("human", "{question}"),
])

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "依据资料回答用户问题，答案末尾必须以 [来源: 文件名] 标注引用的文件；"
               "资料不足时只回答\"无法回答\"。"),
    ("human", "问题：{question}\n\n资料：\n{context}"),
])


def build_graph(store, llm):
    grader = llm.with_structured_output(Relevance)

    def retrieve(state):
        hits = store.similarity_search(state["query"], k=TOP_K)
        docs = [h.page_content for h in hits]
        doc_sources = [h.metadata.get("source", "?") for h in hits]
        sources = sorted(set(doc_sources))
        return {"docs": docs, "doc_sources": doc_sources, "sources": sources}

    def grade(state):
        context = "\n\n".join(f"[{i + 1}] {d[:400]}" for i, d in enumerate(state["docs"]))
        verdict = grader.invoke(GRADE_PROMPT.format_messages(
            question=state["question"], context=context))
        return {"relevant": verdict.relevant}

    def rewrite(state):
        new_q = _text(llm.invoke(REWRITE_PROMPT.format_messages(
            question=state["question"]))).strip()
        return {"query": new_q or state["question"],
                "rewrites": state["rewrites"] + 1}

    def generate(state):
        context = "\n\n".join(f"[{i + 1}] ({src})\n{d}"
                              for i, (d, src) in enumerate(
                                  zip(state["docs"], state["doc_sources"])))
        answer = _text(llm.invoke(ANSWER_PROMPT.format_messages(
            question=state["question"], context=context))).strip()
        return {"answer": answer}

    def refuse(_state):
        return {"answer": "知识库中没有与问题相关的资料，无法回答该问题。"}

    def route(state):
        if state["relevant"]:
            return "generate"
        if state["rewrites"] < MAX_REWRITES:
            return "rewrite"
        return "refuse"

    g = StateGraph(RagState)
    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade)
    g.add_node("rewrite", rewrite)
    g.add_node("generate", generate)
    g.add_node("refuse", refuse)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route,
                            {"generate": "generate",
                             "rewrite": "rewrite",
                             "refuse": "refuse"})
    g.add_edge("rewrite", "retrieve")
    g.add_edge("generate", END)
    g.add_edge("refuse", END)
    return g.compile()


def ask(app, question, thread):
    init = {"question": question, "query": question, "docs": [], "doc_sources": [],
            "sources": [], "relevant": False, "rewrites": 0, "answer": ""}
    return app.invoke(init, {"configurable": {"thread_id": thread}})


def main():
    print("=" * 64)
    print("[10] Agentic RAG：检索 + 评分回炉循环（真机）")
    print(f"模型: {MODEL} | 嵌入: {EMBED_MODEL}")
    print("=" * 64)

    if not ollama_alive():
        print("\n⏭️ Ollama 未启动，本实验需要嵌入与对话模型：先 `ollama serve`")
        return 2

    from langchain_ollama import ChatOllama

    docs_dir = Path(__file__).resolve().parents[2] / "docs"
    section("[索引] 用仓库 docs/ 建知识库")
    store, chunks, files = build_index(docs_dir)
    print(f"  文件 {len(files)} 个: {files}")
    print(f"  切分 {len(chunks)} 个 chunk，写入 Chroma")
    check("知识库覆盖 ≥4 个来源、≥100 个 chunk",
          len(files) >= 4 and len(chunks) >= 100)

    llm = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_predict=512)
    app = build_graph(store, llm)

    section("[问答] 三个可答问题：来源与内容断言")
    cases = [
        ("langgraph dev 本地起服务需要云 key 吗？", "langchain.md", ["不需要"]),
        ("aitest 测试台项目 21 要做什么？", "aitest.md", ["体检", "四维"]),
        ("Harness 与 Agentic AI 的核心区别是什么？", "harness.md", ["运行时", "工程"]),
    ]
    for i, (q, src, keywords) in enumerate(cases, 1):
        r = ask(app, q, f"q{i}")
        hit_kw = [k for k in keywords if k in r["answer"]]
        print(f"  Q{i}: {q}")
        print(f"      回答: {r['answer'][:80].replace(chr(10), ' ')}")
        print(f"      来源: {r['sources']} | 改写次数: {r['rewrites']}")
        check(f"Q{i} 答案引用正确来源且含关键信息",
              src in r["answer"] and len(hit_kw) >= 1,
              f"source={src} 命中关键词={hit_kw}")

    section("[拒答] 库外问题：改写回炉后仍无据 → 拒答")
    r = ask(app, "火星上有什么矿产资源？", "refuse")
    print(f"  改写后查询: {r['query']}")
    print(f"  改写次数: {r['rewrites']} | 回答: {r['answer']}")
    check("库外问题被拒答", "无法回答" in r["answer"])
    check("拒答前评分循环触发 ≥1 次查询改写",
          r["rewrites"] >= 1 and r["query"] != "火星上有什么矿产资源？")

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
