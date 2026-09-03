# 21 · 向量化存储：从文本块到语义索引

> 项目 20 产出的 chunks 只是文本，检索它只能靠关键词——问"怎么切分"找不到
> 只说"递归降级"的块。本篇把 chunks 逐一 embedding（nomic-embed-text，768 维）
> 写入 **Chroma** 向量数据库：检索升级为语义匹配，按"意思"找块。直接复用
> 项目 20 的加载与切分代码——RAG 管线在这里正式串起来了。

## 1. 为什么需要它

关键词检索的天花板很明显：同义改写、跨语言表达、上下位词全都匹配不上。
向量检索把文本映射到高维空间，语义相近的块距离相近——"怎么切分文档"和
"递归字符切分"在 768 维空间里几乎是邻居。Chroma 是生产中最常用的轻量向量库：
持久化、元数据过滤、多种距离度量，本篇用真实 embedding 走完建索引与检索的
完整闭环（项目 17 的手写余弦版则是理解其内部原理的垫脚石）。

## 2. 总览：核心机制一图看懂

![向量化存储管线](images/vector_index.dataflow.svg)

**怎么看这张图**：项目 20 的 chunks 进入本篇后兵分两路——索引路径逐块
embedding 后 upsert 进持久化的 Chroma 集合；查询路径把用户问题也变成向量，
在库中取 top-3，distance 越小越相关。

心智模型一句话：**embedding 把"语义"变成"几何"——找相关文本变成找最近邻。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/21_vector_store/images/vector_index.dataflow.html)（或本地打开 [`images/vector_index.dataflow.html`](images/vector_index.dataflow.html)）。

## 3. 快速开始

```bash
cd agents/21_vector_store
python vector_store.py --demo   # 离线：伪向量走完 Chroma 全流程
python vector_store.py          # 真实：nomic-embed-text + 持久化 Chroma
```

真实模式先复用项目 20 的加载与切分（9 个 chunks），逐块 embedding 后
`upsert` 入库（幂等，重复跑不会重复），再跑 4 组查询。**实测**：4 组查询的
top-1 全部语义正确——"文档应该怎么切分"命中切分策略段（dist 300）、
"为什么需要评估"命中评估手册开头（dist 205）、"RAG 有哪些步骤"命中速查表。

## 4. 核心概念

### 4.1 upsert 与持久化

`PersistentClient` 把数据落在 `chroma_db/` 目录，重启不丢；`upsert` 按 id
幂等写入，重复建索引不产生重复条目。**坑**：集合的向量维度在第一次写入时
定死——本篇 demo（32 维伪向量）与真实（768 维）必须用不同的持久化目录，
混用会得到 "expecting embedding with dimension of 32, got 768"。

### 4.2 距离的含义

Chroma 默认返回平方 L2 距离（数值几百属正常，因为 nomic 向量未归一化）。
重要的不是绝对值，而是**相对排序**：同一查询下 distance 越小越相关。
若换用 cosine 空间（space="cosine"），距离落在 0-2 之间更直观。

### 4.3 语义检索 vs 关键词检索

| | 关键词 | 向量 |
| :--- | :--- | :--- |
| 匹配依据 | 字面共现 | 语义邻近 |
| 同义改写 | 找不到 | 自然命中 |
| 成本 | 零 | 每条文本一次 embedding |
| 可解释性 | 直观 | 需要距离度量辅助 |

### 4.4 已知边界

- embedding 模型换了（维度/空间都变），整库必须重建索引；
- demo 的伪向量只为验证管线——hash 向量不携带语义，检索结果是随机排序；
- chunk 数量大后应考虑批量 embedding 与 HNSW 索引参数调优。

## 5. 代码关键部分

```python
def build_index(collection, docs_root=DOCS_DIR):
    """加载 -> 切分 -> 逐块 embedding -> upsert 入 Chroma"""
    docs = load_directory(docs_root)            # 复用项目 20
    chunks = split_documents(docs)
    for c in chunks:
        c["id"] = f"{c['source']}#{c['chunk_id']}"
    collection.upsert(
        ids=[c["id"] for c in chunks],
        embeddings=[embed_fn(c["text"]) for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[{"source": c["source"], "chunk_id": c["chunk_id"]} for c in chunks],
    )
```

坑清单：

- `get_or_create_collection` 拿到的是已有集合——维度不匹配在 add 时才爆，
  排查先看库目录是否残留旧数据；
- `ids` 必须稳定（本文用 `文件名#块序号`），否则重复建索引会产生重复条目；
- embedding 请求逐条发太慢，生产用 `/api/embed` 批量接口。

## 6. 文件结构

```
21_vector_store/
├── README.md                          # 本篇教程
├── vector_store.py                    # 主脚本（约 150 行）：建索引 + 语义检索
├── chroma_db/                         # 运行时产物：持久化向量库（gitignore）
└── images/
    ├── vector_index.dataflow.json     # 图源：dataflow 类型（索引/查询双路径）
    ├── vector_index.dataflow.html     # 交互版架构图
    └── vector_index.dataflow.svg      # 双主题矢量图
```

## 7. 面试要点

- **Q: 向量数据库解决什么问题？**
  A: 高维向量的存储与最近邻检索——把"语义相似"变成"几何最近"，支撑
  RAG 的语义检索、推荐与去重。
- **Q: upsert 为什么比 add 更适合建索引？**
  A: 幂等——同一 id 重复写入是更新而非新增，重复跑建索引不会产生重复数据。
- **Q: Chroma 返回的 distance 怎么理解？**
  A: 取决于空间配置：默认平方 L2（无上界），cosine 空间为 0-2。比较相关性
  看同一查询内的相对排序即可。
- **Q: 换 embedding 模型要注意什么？**
  A: 维度与语义空间都会变，旧向量全部作废，必须整库重建；新旧向量不可混存。
- **Q: 手写余弦版（项目 17）和 Chroma（本篇）的差距在哪？**
  A: 持久化、元数据过滤、增量更新、规模化后的近似最近邻索引（HNSW）——
  原理相同，工程能力不同。

## 8. 总结

chunks → 向量 → 语义索引，RAG 的"检索"一侧就此打通：任何问题都能按意思
找到最相关的块。但检索现在是被动调用的函数——下一篇让它变成 Agent 手里的
工具，由模型自主决定"要不要查、查什么"，这就是 Agentic RAG。
