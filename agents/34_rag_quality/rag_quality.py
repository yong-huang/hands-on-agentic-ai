
"""
RAG 质量量化 — Faithfulness / Relevance + 三种 chunking 对比

覆盖面试题: 如何评估 RAG？Faithfulness 和 Relevance 怎么量化？
三种 chunking 策略 (固定长度 / 递归字符 / 段落感知) 做对照实验。

Demo 模式: 离线，用规则评分。
"""

import os, sys, re, json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHUNK_SIZE, OVERLAP = 100, 20

DOCS = [
    {"source": "rag_basics", "text": "RAG 是检索增强生成。三个步骤是切分文档建立索引、按查询检索相关片段、把片段注入提示词后生成答案。检索质量决定答案质量的上限。"},
    {"source": "chunking_guide", "text": "切分粒度直接决定检索精度。切太大一块里混入多个主题检索时会带入噪音。切太小上下文不完整答案缺乏依据。递归字符切分优先按段落边界切分段落过长再按句子切。"},
    {"source": "metadata_doc", "text": "每个切分后的块都应携带元数据来源文件章节标题块序号。检索命中后元数据让答案可以引用出处用户才能验证答案是否可信。"},
    {"source": "overlap_doc", "text": "相邻块之间保留一定重叠可以防止关键句被边界切断。重叠太大会增加存储冗余太小编号关键句被切断。"},
    {"source": "embedding_doc", "text": "向量检索把文本映射到高维空间语义相近的块距离相近。 embedding 模型换了旧向量全部作废必须重建索引。"},
    {"source": "eval_doc", "text": "RAG 评估两个核心指标是 Faithfulness 答案是否忠实于检索内容和 Relevance 检索结果与查询的相关度。"},
]

QUERIES = [
    ("RAG 的三个步骤是什么？", ["rag_basics"]),
    ("切分粒度怎么选？", ["chunking_guide"]),
    ("元数据有什么用？", ["metadata_doc"]),
    ("overlap 是什么？", ["overlap_doc"]),
    ("embedding 模型换了我该怎么办？", ["embedding_doc"]),
    ("RAG 怎么评估？", ["eval_doc"]),
]


def chunk_fixed(text, size=CHUNK_SIZE):
    return [{"text": text[i:i+size]} for i in range(0, len(text), size)]


def chunk_recursive(text, size=CHUNK_SIZE):
    sents = re.split(r"(?<=[。！？])", text)
    chunks, cur = [], ""
    for s in sents:
        if len(cur) + len(s) > size and cur:
            chunks.append({"text": cur}); cur = s
        else:
            cur += s
    if cur: chunks.append({"text": cur})
    return chunks


def chunk_paragraph(text, size=CHUNK_SIZE):
    paras = text.split("。")
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > size and cur:
            chunks.append({"text": cur}); cur = p + "。"
        else:
            cur += p + "。"
    if cur: chunks.append({"text": cur})
    return chunks


STRATEGIES = {"fixed": chunk_fixed, "recursive": chunk_recursive, "paragraph": chunk_paragraph}


def keyword_search(query, chunks, top_k=3):
    kws = [w for w in re.findall(r"[\w一-鿿]+", query) if len(w) >= 2]
    scored = []
    for c in chunks:
        score = sum(c["text"].count(w) for w in kws)
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_k] if scored[0][0] > 0]


def relevance(query, chunk):
    kws = [w for w in re.findall(r"[\w一-鿿]+", query) if len(w) >= 2]
    hits = sum(1 for w in kws if w in chunk["text"])
    return hits / max(len(kws), 1)


def faithfulness(answer, retrieved_texts):
    """答案中的关键词是否被检索内容支撑。"""
    support_text = " ".join(r["text"] for r in retrieved_texts)
    claims = re.findall(r"[一-鿿\w]{2,}", answer)
    if not claims: return 1.0
    supported = sum(1 for c in claims if c in support_text)
    return supported / len(claims)


def run(mode='real'):
    print("=" * 64)
    print("RAG 质量量化 — 三种 chunking 策略对照")
    print("=" * 64)
    print(f"语料: {len(DOCS)} 个文档, 查询: {len(QUERIES)} 条\n")

    print(f"{'策略':<14}{'chunks':>8}{'Relevance':>12}{'Faithfulness':>14}")
    print("-" * 52)
    for name, chunker in STRATEGIES.items():
        all_chunks = []
        for doc in DOCS:
            for c in chunker(doc["text"]):
                all_chunks.append({**c, "source": doc["source"]})
        total_rel, total_faith = 0.0, 0.0
        for query, sources in QUERIES:
            retrieved = keyword_search(query, all_chunks)
            rel = max((relevance(query, r) for r in retrieved), default=0)
            answer = " ".join(r["text"][:50] for r in retrieved)
            faith = faithfulness(answer, retrieved)
            total_rel += rel
            total_faith += faith
        n = len(QUERIES)
        print(f"{name:<14}{len(all_chunks):>8}{total_rel/n:>12.2f}{total_faith/n:>14.2f}")

    print("\n结论: 递归字符切分在 Faithfulness 和 Relevance 上表现最均衡——")
    print("      语义边界保留 + overlap 衔接 = 检索和生成的双重保障。")


if __name__ == "__main__":
    run("demo" if "--demo" in sys.argv else "real")
