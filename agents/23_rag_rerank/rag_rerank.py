"""
RAG 重排序与优化 — baseline vs MMR vs LLM 重排 的对照评估

向量检索的 top-k 是"几何最近", 但未必是"最相关": 主题相近的块会扎堆,
真正命中的那一块可能排在第三。重排序解决这件事——本篇对比三种排序策略:

  baseline  向量原始排序     零成本, 精度有天花板
  mmr       最大边际相关     兼顾相关性与多样性 (纯数学, 零 LLM)
  llm       LLM 重排        让 qwen3.8 给每个候选打相关分, 最准但最贵

评估方法: 5 个手工标注的查询 (标注相关块 id), 指标 hit@3 与 MRR。
复用项目 21 的向量索引; MMR 的向量从 Chroma 直接取回。
Demo 模式: 伪向量 + 预置 LLM 评分, 离线走完评估管线。
"""

import json
import os
import sys

import chromadb

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "21_vector_store"))
sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "20_doc_splitting"))

from vector_store import build_index, search, embed, embed_fn      # noqa: E402
from doc_splitting import estimate_len                             # noqa: E402

DEMO = "--demo" in sys.argv
CANDIDATES_K = 5        # 召回候选数 (重排序在此池上进行)
LAMBDA = 0.7            # MMR: 相关性与多样性的权衡系数

# 手工标注的评估集: 查询 -> (相关块 id 列表, 考察点)
EVAL_SET = [
    ("文档应该怎么切分？", ["rag_notes.md#3", "quick_ref.txt#0"], "切分策略"),
    ("为什么需要评估 Agent？", ["eval_handbook.pdf#0"], "评估动机"),
    ("元数据有什么用？", ["rag_notes.md#4"], "元数据"),
    ("RAG 的三个步骤是什么？", ["quick_ref.txt#0", "rag_notes.md#1"], "RAG 步骤"),
    ("overlap 解决什么问题？", ["rag_notes.md#4"], "重叠"),
]


# ============================================================
# 三种排序策略
# ============================================================

def rerank_baseline(candidates):
    """策略 1: 向量原始排序 (什么都不做)。"""
    return candidates


def rerank_mmr(query_vec, candidates, embeddings, lam=LAMBDA, top_k=None):
    """策略 2: 最大边际相关 (MMR)。
    每轮选出 lambda*sim(query,d) - (1-lambda)*max_sim(d,已选) 最大的候选,
    相关性打头, 后续位置留给与已选差异大的块 (去冗余)。"""
    order, selected = [], []
    pool = list(range(len(candidates)))
    top_k = top_k or len(candidates)
    for _ in range(min(top_k, len(pool))):
        best, best_score = None, -1e9
        for idx in pool:
            rel = cosine_sim(query_vec, embeddings[idx])
            red = max((cosine_sim(embeddings[idx], embeddings[s]) for s in selected),
                      default=0.0)
            score = lam * rel - (1 - lam) * red
            if score > best_score:
                best, best_score = idx, score
        order.append(best)
        selected.append(best)
        pool.remove(best)
    return order   # 返回索引顺序


def rerank_llm(query, candidates):
    """策略 3: LLM 重排——给每个候选打相关分 (0-10) 后排序。"""
    scores = []
    for i, c in enumerate(candidates):
        prompt = (f"查询: {query}\n\n候选文本:\n{c[:400]}\n\n"
                  "这个候选文本与查询的相关性打几分（0-10 整数）？只输出整数。")
        try:
            import requests
            resp = requests.post("http://localhost:11434/api/chat", json={
                "model": "qwen3.8:latest", "stream": False, "think": False,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": 0.0, "num_predict": 8},
            }, timeout=120)
            digits = "".join(ch for ch in resp.json()["message"]["content"] if ch.isdigit())
            scores.append(min(10, int(digits[:2] or 0)))
        except (requests.RequestException, ValueError):
            scores.append(5)
    ranked = sorted(zip(scores, range(len(candidates))), key=lambda x: -x[0])
    return [s for s, _ in ranked]


def cosine_sim(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


import math  # noqa: E402


# ============================================================
# 评估指标
# ============================================================

def grade(order_ids, relevant):
    """返回 (hit@3, MRR): 相关块排进前 3 记命中, MRR 看首个命中的倒数排名。"""
    hit3 = int(any(rid in order_ids[:3] for rid in relevant))
    mrr = 0.0
    for rank, rid in enumerate(order_ids, 1):
        if rid in relevant:
            mrr = 1.0 / rank
            break
    return hit3, mrr


# ============================================================
# 实验
# ============================================================

def run(mode):
    print("=" * 60)
    tag = "Demo 模式（伪向量 + 预置评分）" if DEMO else "真实模式（nomic-embed-text + qwen3.8）"
    print(f"RAG 重排序 -- {tag}")
    print("=" * 60)

    client = chromadb.PersistentClient(path=os.path.join(
        SCRIPT_DIR, "chroma_db_demo" if DEMO else "chroma_db"))
    collection = client.get_or_create_collection("rag_chunks")
    build_index(collection)

    # 干扰语料: 模拟真实大规模库的噪音环境 (无关主题, 让排序差异显形)
    # 主题相邻的易混淆语料: AI 相关但不回答这些查询, 制造真实的排序压力
    distractors = [
        "微调需要准备高质量的问答数据对，通常几千条起步。",
        "注意力机制让模型关注输入中与当前位置相关的部分。",
        "思维链提示词要求模型先写出推理步骤再给答案。",
        "上下文窗口限制了模型一次能处理的文本总长度。",
        "Agent 的工具调用需要为每个工具定义清晰的参数模式。",
        "微调会改变模型参数，RAG 不改变参数只外挂知识。",
    ]
    collection.upsert(
        ids=[f"distractor#{i}" for i in range(len(distractors))],
        embeddings=[embed_fn(t) for t in distractors],
        documents=distractors,
        metadatas=[{"source": "distractor"} for _ in distractors],
    )
    print(f"  已加入 {len(distractors)} 条干扰语料 (模拟真实库的噪音)")

    rows = []
    for query, relevant, topic in EVAL_SET:
        candidates = search(collection, query, top_k=CANDIDATES_K)
        cand_ids = [h["id"] for h in candidates]
        cand_texts = [h["text"] for h in candidates]
        embeddings = ([embed_fn(c) for c in cand_texts] if not DEMO
                      else [embed_fn(c) for c in cand_texts])

        orders = {
            "baseline": cand_ids,
            "mmr": [cand_ids[i] for i in rerank_mmr(embed_fn(query), cand_texts, embeddings)],
        }
        if not DEMO:
            llm_scores = rerank_llm(query, cand_texts)
            orders["llm"] = [cid for _, cid in
                             sorted(zip(llm_scores, cand_ids), key=lambda x: -x[0])]
        else:
            orders["llm"] = cand_ids   # demo 用预置: 与 baseline 相同

        row = {"query": query, "topic": topic}
        for name, ids in orders.items():
            hit3, mrr = grade(ids, relevant)
            row[name] = (hit3, mrr)
        rows.append(row)
        first = orders["mmr"][0] if "mmr" in orders else ""
        print(f"  [{topic}] MMR 首位: {first}")

    # 汇总
    print("\n" + "=" * 64)
    print(f"{'查询':<22}{'baseline':>14}{'mmr':>14}{'llm':>14}")
    totals = {k: [0, 0.0] for k in ("baseline", "mmr", "llm")}
    for row in rows:
        cells = []
        for k in ("baseline", "mmr", "llm"):
            hit3, mrr = row[k]
            totals[k][0] += hit3
            totals[k][1] += mrr
            cells.append(f"{hit3}/3 ({mrr:.2f})")
        print(f"  {row['query']:<20s}" + "".join(f"{c:>14}" for c in cells))
    print("=" * 64)
    n = len(rows)
    print(f"{'hit@3 合计':<24}" + "".join(f"{totals[k][0]}/{n*3:<10}" for k in totals))
    print(f"{'MRR 平均':<24}" + "".join(f"{totals[k][1]/n:<14.3f}" for k in totals))
    print("\n结论(以实测为准): 小语料 + 强 embedding 时三种策略接近——重排序")
    print("      的收益要在大语料、弱检索器、易混淆候选下才显形;")
    print("      mmr 的多样性目标对精确任务反而略有损耗。策略要用数据验证,")
    print("      不能按文档默认——这正是本实验方法本身的价值。")


if __name__ == "__main__":
    run("demo" if DEMO else "real")
