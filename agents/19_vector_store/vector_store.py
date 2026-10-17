"""
向量化存储 — 把项目 20 的 chunks 变成可检索的语义索引

项目 20 产出的 chunks 只是文本。本篇把它们逐一 embedding (nomic-embed-text,
768 维) 后写入 Chroma 向量数据库——检索从"字面匹配"升级为"语义匹配":
问"怎么切分"能命中只说"递归字符切分"的块。

真实模式: 复用项目 20 的加载与切分, 真实 embedding 写入持久化 Chroma,
再跑多组查询观察语义召回与距离。
Demo 模式: 确定性伪向量走完 Chroma 全流程 (离线, 无需 Ollama)。

Chroma 是生产里最常用的轻量向量库; 教学实现的手写余弦版见项目 17。
"""

import hashlib
import math
import os
import sys

import chromadb

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "20_doc_splitting", "docs")
CHROMA_DIR = os.path.join(SCRIPT_DIR, "chroma_db_demo" if "--demo" in sys.argv
                             else "chroma_db")   # 两个模式的向量维度不同, 不能共用
COLLECTION = "rag_chunks"

# 复用项目 20 的加载与切分 (跨实验复用: 21 直接消费 20 的产物)
sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "20_doc_splitting"))
from doc_splitting import load_directory, split_documents, estimate_len  # noqa: E402


def embed(text):
    """nomic-embed-text: 768 维向量 (Ollama 本地, 无 API Key)。"""
    import requests
    resp = requests.post("http://localhost:11434/api/embeddings",
                         json={"model": "nomic-embed-text", "prompt": text}, timeout=60)
    resp.raise_for_status()
    return resp.json()["embedding"]


def fake_embed(text, dim=32):
    """确定性伪向量 (demo 用): 相似文本不会真的更近, 仅验证管线。"""
    v = [0.0] * dim
    for i, ch in enumerate(text):
        v[(i * 7 + ord(ch)) % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def embed_fn(text):
    return fake_embed(text) if "--demo" in sys.argv else embed(text)


# ============================================================
# 建索引与检索
# ============================================================

def build_index(collection, docs_root=DOCS_DIR):
    """加载 -> 切分 -> 逐块 embedding -> upsert 入 Chroma。"""
    docs = load_directory(docs_root)
    chunks = split_documents(docs)
    for c in chunks:
        c["id"] = f"{c['source']}#{c['chunk_id']}"
    collection.upsert(
        ids=[c["id"] for c in chunks],
        embeddings=[embed_fn(c["text"]) for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[{"source": c["source"], "chunk_id": c["chunk_id"]} for c in chunks],
    )
    print(f"  已索引 {len(chunks)} 个 chunks ({collection.count()} 条在库)")
    return chunks


def search(collection, query, top_k=3):
    result = collection.query(query_embeddings=[embed_fn(query)], n_results=top_k)
    hits = []
    for i in range(len(result["ids"][0])):
        hits.append({"id": result["ids"][0][i],
                     "distance": result["distances"][0][i],
                     "text": result["documents"][0][i]})
    return hits


QUERIES = [
    "文档应该怎么切分？",
    "为什么需要评估 Agent？",
    "元数据的作用是什么？",
    "RAG 有哪些步骤？",
]


# ============================================================
# 入口
# ============================================================

def run(mode):
    print("=" * 60)
    tag = "Demo 模式（伪向量, 离线）" if mode == "demo" else "真实模式（nomic-embed-text, 768 维）"
    print(f"向量化存储 -- {tag}")
    print("=" * 60)

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(COLLECTION)

    print("\n==> [index] 建索引 (加载/切分复用项目 20)")
    chunks = build_index(collection)

    print("\n==> [query] 语义检索 (top-3, distance 越小越相关)")
    for q in QUERIES:
        print(f"\n  Q: {q}")
        for h in search(collection, q):
            preview = h["text"].replace("\n", " ")[:52]
            print(f"    [{h['id']}] dist={h['distance']:.3f}  {preview}…")

    print("\n要点: 语义检索按'意思'找块——问'怎么切分'能命中只讲'递归降级'的块;")
    print("      distance 是向量距离 (越小越相关), 项目 22 将把检索变成 Agent 工具。")


if __name__ == "__main__":
    run("demo" if "--demo" in sys.argv else "real")
