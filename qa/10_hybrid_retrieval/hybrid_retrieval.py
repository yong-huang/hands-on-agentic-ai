"""
面试项目 10 — 混合检索（向量 + 关键词 + RRF）

覆盖面试题: 向量检索、关键词检索、混合检索怎么选择？

核心: 50 条文档小语料, 三种检索器对跑 15 条查询 (三类 × 5 条):
  BM25    简化实现 (k1/b + IDF), 字面匹配强
  Vector  语义匹配 (真实: nomic-embed-text / MOCK: hash 词袋退化)
  RRF     Reciprocal Rank Fusion 融合前两者排名
评测 Hit@3, 按查询类别输出命中率对比表。
预期: 精确词查询 BM25 赢, 语义改写查询向量赢, 混合 overall RRF 最高。

运行:
  MOCK=1 python hybrid_retrieval.py    # 离线: hash 向量 (链路验证)
  python hybrid_retrieval.py           # 真实: nomic-embed-text 语义检索
"""

import json, math, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
EMBED_MODEL = "nomic-embed-text"
DIM = 256
K1, B, RRF_K = 1.5, 0.75, 60


def embed(text):
    if MOCK:
        return None                    # mock 用 hash_vec
    body = {"model": EMBED_MODEL, "input": text}
    req = urllib.request.Request(f"{BASE_URL}/embeddings", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())["data"][0]["embedding"]


def tokenize(text):
    text = re.sub(r"[^\w\u4e00-\u9fff]", " ", str(text).lower())
    toks = []
    for w in text.split():
        if re.fullmatch(r"[\u4e00-\u9fff]+", w):
            toks += [w[i:i + 2] for i in range(len(w) - 1)] or [w]
            toks += [c + "*" for c in w]
        else:
            toks.append(w)
    return toks


def hash_vec(text):
    v = [0.0] * DIM
    for t in tokenize(text):
        v[hash(t) % DIM] += 0.5 if t.endswith("*") else 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / ((math.sqrt(sum(x * x for x in a)) or 1)
                                               * (math.sqrt(sum(x * x for x in b)) or 1))


# ============================================================
# 50 条文档小语料
# ============================================================

DOCS = [
    "RRF 即 Reciprocal Rank Fusion, 融合公式为各排名倒数求和, 常数 k 取 60",
    "P99 延迟指第 99 百分位的请求耗时, 是观察长尾延迟的核心指标",
    "BM25 是基于词频与逆文档频率的概率检索算法, k1 控制词频饱和, b 控制长度归一",
    "JSON Schema 可以声明嵌套对象与数组结构, 配合 jsonschema 库做参数校验",
    "SSE 是服务器向浏览器单向推送事件流的协议, 断线后浏览器自动重连",
    "上下文窗口超限时, 把旧对话压缩成摘要, 保留近期原文",
    "检索后加一层 rerank 重排模型, 能显著提升文档相关度",
    "长期记忆库用向量数据库跨会话保存用户事实, 按需检索注入",
    "工具描述要写清使用时机与反例, 能提升模型选对工具的准确率",
    "JSON 解析失败时把错误信息回喂给模型, 让它自行纠正输出格式",
    "故障时把执行现场快照持久化到磁盘, 重启后从断点恢复",
    "下游服务变慢时用降级与熔断保护主链路, 避免雪崩",
    "意图识别置信度低时把会话转给人工坐席, 兜底体验",
    "索引膨胀与慢查询堆积会让数据库性能逐渐劣化",
    "检验生成内容是否有引用支撑, 可以量化幻觉比例",
    "Agent 死循环防护: 步数上限、重复动作检测、预算熔断三管齐下",
    "function calling 把工具参数结构化传输, 依赖模型原生能力",
    "ReAct 用提示词驱动 思考-行动-观察 循环, 任何模型都能跑",
    "prompt injection 把恶意指令藏在网页或工具返回里, 诱导模型执行",
    "评估 LLM 输出可以用 LLM-as-Judge, 但要小心位置与身份偏见",
    "多路召回后用 RRF 融合排名, 兼顾字面与语义两路信号",
    "向量检索把文本编码成 embedding, 用余弦相似度找近邻",
    "倒排索引把词映射到文档列表, 是关键词检索的底座",
    "chunking 切块策略影响召回粒度, 太碎丢上下文, 太大稀释相关度",
    "top_k 采样从概率最高的 k 个候选里抽样, 温度控制分布尖锐度",
    "系统提示词里标注指令层级, 能缓解注入攻击",
    "MCP 是模型连接工具与数据源的开放协议, 有 stdio 与 HTTP 传输",
    "A2A 让 Agent 之间互相发现与协作, 与 MCP 互补",
    "会话历史按轮存储, 窗口策略只保留最近 N 轮",
    "embedding 模型把语义相近的文本映射到相近的向量位置",
    "缓存热门查询结果, 可以显著降低检索延迟",
    "灰度发布先放少量流量验证, 再逐步放量",
    "幂等设计让同一操作重复执行结果不变, 是重试安全的前提",
    "限流算法有令牌桶与漏桶, 保护服务不被突发流量打垮",
    "分布式锁用 Redis SETNX 加过期时间实现, 注意续期问题",
    "消息队列削峰填谷, 异步解耦生产者与消费者",
    "向量数据库支持 ANN 近似最近邻检索, 牺牲少量精度换速度",
    "微调需要构造指令数据集, LoRA 只训练低秩增量矩阵",
    "量化把权重压到低位宽, 换取更小内存与更快推理",
    "KV cache 复用已计算的注意力键值, 加速自回归生成",
    "流式输出边生成边返回, 降低首字延迟",
    "护栏分规则层与模型层, 规则先拦可疑再过分类器",
    "工具调用失败要把异常信息作为观察回喂, 让 Agent 换路径",
    "多 Agent 协作常见拓扑有 路由型 辩论型 与 管理者-工人型",
    "评测集要覆盖边界用例, 单一指标会掩盖长尾问题",
    "embedding 相似度高不代表事实正确, 只代表语义相近",
    "混合检索通常 字面一路 语义一路, 再用融合排序合并",
    "重排模型是交叉编码器, 精度高但慢, 只对 top 候选打分",
    "检索评测用 MRR 与 Hit@k, 看目标文档排在第几位",
    "上下文工程比提示词工程更系统: 组织、压缩、隔离上下文",
]

# 15 条查询: (查询, 类别, 目标文档下标)
QUERIES = [
    ("RRF 的融合公式里常数 k 取多少", "精确词", 0),
    ("P99 延迟是什么指标", "精确词", 1),
    ("BM25 的 k1 和 b 参数分别控制什么", "精确词", 2),
    ("JSON Schema 怎么校验嵌套结构", "精确词", 3),
    ("SSE 断线之后会怎么样", "精确词", 4),
    ("怎么防止程序挂掉之前做的事白做", "语义改写", 10),
    ("线上接口偶发超时应该怎么保护自己", "语义改写", 11),
    ("机器人答不上来用户的怪问题时咋办", "语义改写", 12),
    ("数据库为什么越跑越卡", "语义改写", 13),
    ("怎么判断模型是不是在瞎编", "语义改写", 14),
    ("对话太长装不下了如何处理", "混合", 5),
    ("搜回来的东西不相关该怎么改进", "混合", 6),
    ("怎么让机器人记住上个月聊过的偏好", "混合", 7),
    ("模型输出不是合法 JSON 怎么补救", "混合", 9),
    ("怎样让模型少选错工具", "混合", 8),
]


# ============================================================
# 三种检索器
# ============================================================

class BM25:
    def __init__(self, docs):
        self.docs, self.tl = docs, [tokenize(d) for d in docs]
        self.N, self.avgdl = len(docs), sum(len(t) for t in self.tl) / len(docs)
        self.df = {}
        for t in self.tl:
            for w in set(t):
                self.df[w] = self.df.get(w, 0) + 1

    def idf(self, w):
        return math.log((self.N - self.df.get(w, 0) + 0.5) / (self.df.get(w, 0) + 0.5) + 1)

    def search(self, query, k=3):
        qt = tokenize(query)
        scores = []
        for i, tl in enumerate(self.tl):
            s, tf = 0.0, {}
            for w in tl:
                tf[w] = tf.get(w, 0) + 1
            for w in qt:
                if tf.get(w):
                    s += self.idf(w) * tf[w] * (K1 + 1) / (
                        tf[w] + K1 * (1 - B + B * len(tl) / self.avgdl))
            scores.append((s, i))
        scores.sort(reverse=True)
        return [i for _, i in scores[:k]]


class VectorSearch:
    def __init__(self, docs):
        self.vecs = [(embed(d) if not MOCK else hash_vec(d)) for d in docs]

    def search(self, query, k=3):
        qv = embed(query) if not MOCK else hash_vec(query)
        scored = sorted(((cosine(qv, v), i) for i, v in enumerate(self.vecs)),
                        reverse=True)
        return [i for _, i in scored[:k]]


def rrf_fuse(rank_lists, k=3):
    """Reciprocal Rank Fusion: score(d) = Σ 1/(RRF_K + rank_i(d))"""
    fused = {}
    for ranks in rank_lists:
        for r, d in enumerate(ranks):
            fused[d] = fused.get(d, 0) + 1 / (RRF_K + r + 1)
    return [d for d, _ in sorted(fused.items(), key=lambda x: -x[1])[:k]]


def main():
    print("=" * 72)
    print(f"混合检索 (BM25 + Vector + RRF) -- "
          f"{'MOCK (hash 向量, 仅验证链路)' if MOCK else '真实 nomic-embed-text'}")
    print(f"语料 {len(DOCS)} 条 | 查询 15 条 (精确词/语义改写/混合 各 5) | 评测 Hit@3")
    print("=" * 72)

    bm25, vec = BM25(DOCS), VectorSearch(DOCS)
    stats = {m: {c: [0, 0] for c in ("精确词", "语义改写", "混合")} for m in
             ("BM25", "Vector", "RRF")}
    for q, cat, target in QUERIES:
        r_bm = bm25.search(q)
        r_vec = vec.search(q)
        r_rrf = rrf_fuse([r_bm, r_vec])
        for name, ranks in (("BM25", r_bm), ("Vector", r_vec), ("RRF", r_rrf)):
            hit = target in ranks
            stats[name][cat][0] += hit
            stats[name][cat][1] += 1
        mark = "✓" if target in r_rrf else "✗"
        print(f"  [{cat}] {q[:24]:<26} → 目标#{target:<2} RRF{mark} "
              f"(BM25 目标排名 {r_bm.index(target)+1 if target in r_bm else '-'} / "
              f"Vec {r_vec.index(target)+1 if target in r_vec else '-'})")

    print("\n" + "=" * 72)
    print(f"{'检索器':<10}{'精确词':>12}{'语义改写':>12}{'混合':>10}{'overall':>12}")
    print("-" * 60)
    for name in ("BM25", "Vector", "RRF"):
        cells, tot = [], [0, 0]
        for c in ("精确词", "语义改写", "混合"):
            h, n = stats[name][c]
            cells.append(f"{h}/{n}")
            tot[0] += h
            tot[1] += n
        print(f"{name:<10}" + "".join(f"{c:>12}" for c in cells)
              + f"{tot[0]}/{tot[1]}".rjust(12))
    print("""
要点: 三种检索怎么选
  1) 字面必须命中的场景 (型号/报错码/专名) 靠 BM25——向量对精确 token 不敏感。
  2) 换了一种说法的问题靠向量——字面零重叠时 BM25 直接失明。
  3) 生产默认上混合: 两路召回 + RRF 融合, 用一条公式合并排名,
     不用调两路分数的量纲, overall 最稳。
""")


if __name__ == "__main__":
    main()
