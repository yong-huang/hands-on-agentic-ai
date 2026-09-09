"""
面试项目 28 — RAG 质量量化 (Faithfulness / Relevance)

覆盖面试题: 如何评估 RAG 的检索质量？Faithfulness 和 Relevance 怎么量化？

核心: 30 条文档小语料, 3 种 chunking (整段 / 滑窗 200 字 / 句对) 各建索引:
  Relevance    检索块与问题的 embedding 相似度均值
  Faithfulness 答案逐句回溯: 每句是否能被检索块的字面证据支撑,
               无支撑句占比 -> 忠实度 (幻觉检测的简化版)
对照一种"注入幻觉"的回答, 验证 Faithfulness 指标能把它抓出来。
真机: 3 题 x 3 chunking, 回答由 qwen3.8 生成; 检索用 nomic-embed-text。

运行:
  MOCK=1 python rag_quality.py    # 离线: hash 向量 + 抽取式回答
  python rag_quality.py           # 真实: nomic + qwen3.8
"""

import json, math, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
EMBED_MODEL = "nomic-embed-text"
DIM = 256
TOP_K = 3


def embed(text):
    if MOCK:
        return None
    body = {"model": EMBED_MODEL, "input": text}
    req = urllib.request.Request(
        "{}/embeddings".format(BASE_URL), data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer {}".format(API_KEY)})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())["data"][0]["embedding"]


def http_chat(messages, num_predict=700):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": num_predict}
    req = urllib.request.Request(
        "{}/chat/completions".format(BASE_URL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer {}".format(API_KEY)})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    content = re.sub(r"<think>.*?</think>\s*", "", msg.get("content") or "",
                     flags=re.S).strip()
    return content or (msg.get("reasoning") or "").strip()


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
    return sum(x * y for x, y in zip(a, b)) / (
        (math.sqrt(sum(x * x for x in a)) or 1) *
        (math.sqrt(sum(x * x for x in b)) or 1))


# ============================================================
# 30 条文档 (每条 2 句)
# ============================================================

DOCS = [
    "上下文窗口是模型单次能处理的最大 token 数。超出窗口的历史必须截断或压缩。",
    "滑动窗口保留最近 N 轮对话, 丢弃更早的内容。简单但会丢失早期关键信息。",
    "摘要压缩把旧对话归纳成要点, 保留语义骨架但可能丢失数字细节。",
    "长期记忆用向量库跨会话保存用户事实。检索时按相似度取 TopK 注入。",
    "ReAct 用提示词驱动 思考-行动-观察 循环。任何指令模型都能运行。",
    "function calling 由 API 结构化传输工具参数。要求模型原生支持 tools。",
    "死循环防护包括步数上限、重复动作检测和预算熔断。多层互为补充。",
    "MCP 是模型连接工具与数据源的开放协议。支持 stdio 与 HTTP 传输。",
    "prompt injection 把恶意指令藏进数据。防御要在服务端做白名单与扫描。",
    "多 Agent 系统常见拓扑有路由型、辩论型和管理者-工人型。各有适用场景。",
    "LLM-as-Judge 用模型给回答打分。要注意身份偏差和位置偏差。",
    "Faithfulness 衡量答案是否被检索文档支撑。无支撑句比例高说明幻觉多。",
    "Relevance 衡量检索块与问题的相关程度。常用 embedding 相似度近似。",
    "chunking 切块太碎会丢失上下文。太大则稀释相关度, 需要权衡。",
    "混合检索把关键词路与向量路召回融合。RRF 用排名倒数合并两路结果。",
    "BM25 基于词频与逆文档频率。对精确词匹配强, 对语义改写无能为力。",
    "向量检索把文本编码成 embedding。语义相近的文本距离更近。",
    "rerank 重排模型是交叉编码器。精度高但慢, 只对 top 候选打分。",
    "Hit@k 衡量目标文档是否出现在前 k 个结果里。是检索评测的基础指标。",
    "MRR 是目标文档排名倒数的均值。兼顾了排序位置的信息。",
    "熔断器在连续失败 N 次后暂时摘除故障工具。冷却后半开探测恢复。",
    "优雅降级链依次尝试 主工具、备用工具、缓存。最后诚实拒答并附原因。",
    "HITL 在执行不可逆操作前请求人工审批。超时未响应默认拒绝。",
    "审计日志记录谁在何时调用了什么。是生产 Agent 的合规底线。",
    "Agent Card 描述 Agent 的技能与端点。让其他 Agent 可以动态发现它。",
    "A2A 解决 Agent 之间的协作发现。与 MCP 的 Agent-接-工具互补。",
    "护栏分规则层与模型层。规则先拦明显攻击, 可疑的再交给分类器。",
    "记忆污染指错误信息进入长期记忆。防御有置信度、TTL 和冲突检测。",
    "Reflection 定期把近期记忆归纳成高层洞察。按重要性乘新近性打分。",
    "评测集要覆盖边界用例。单一指标会掩盖长尾问题, 需要多指标互补。",
]

QA = [
    ("RAG 的忠实度指标怎么定义？", 11),
    ("滑动窗口记忆策略有什么缺点？", 1),
    ("BM25 对什么查询弱？", 15),
    ("熔断器是怎么工作的？", 20),
    ("Agent Card 是干什么的？", 24),
]


def chunk_docs(strategy):
    """三种 chunking: whole / window(滑窗50字) / pair(句对)。"""
    chunks = []
    for d in DOCS:
        sents = [s for s in re.split(r"(?<=[。？！])", d) if s]
        if strategy == "whole":
            chunks.append(d)
        elif strategy == "window":
            for i in range(0, max(len(d) - 50, 1), 50):
                chunks.append(d[i:i + 100])
        else:                                    # pair: 每句一块 (句子级)
            chunks.extend(sents)
    return chunks


def retrieve(question, chunks, k=TOP_K):
    qv = embed(question) or hash_vec(question)
    scored = []
    for c in chunks:
        cv = embed(c) or hash_vec(c)
        scored.append((cosine(qv, cv), c))
    scored.sort(key=lambda x: -x[0])
    top = scored[:k]
    return top


def make_answer(question, top_chunks, hallucinate=False):
    """MOCK: 抽取式回答 (取 top1 的第一句); hallucinate=True 注入无支撑句。"""
    if not MOCK:
        ctx = "\n".join("- " + c for c in top_chunks)
        return http_chat([{"role": "user", "content":
                           "只根据以下资料回答, 不要编造。\n资料:\n{}\n\n问题: {}"
                           .format(ctx, question)}], 700)
    base = re.split(r"(?<=[。])", top_chunks[0])[0]
    if hallucinate:
        return base + " 另外, 该指标由 OpenAI 在 2030 年提出, 满分 100 分。"
    return base


def faithfulness(answer, top_chunks):
    """逐句回溯: 答案每句是否被检索块的字符证据支撑 (二元组重合率)。"""
    def bigrams(t):
        t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
        return {t[i:i + 2] for i in range(len(t) - 1)} or set(t)
    evidence = set()
    for c in top_chunks:
        evidence |= bigrams(c)
    sents = [s for s in re.split(r"(?<=[。！？.])", answer) if len(s.strip()) > 2]
    if not sents:
        return 0.0
    supported = 0
    for s in sents:
        bg = bigrams(s)
        if bg and len(bg & evidence) / len(bg) >= 0.35:
            supported += 1
    return supported / len(sents)


def main():
    print("=" * 72)
    print("RAG 质量量化 (Relevance / Faithfulness) -- {}".format(
        "MOCK (hash 向量 + 抽取式回答)" if MOCK else
        "真实 nomic + qwen3.8 (3 题 x 3 chunking)"))
    print("语料 {} 条 | Top{} | Faithfulness = 有证据支撑的句子占比".format(
        len(DOCS), TOP_K))
    print("=" * 72)

    strategies = ["whole", "window", "pair"]
    table = {}
    print("\n==> 幻觉注入对照 (验证 Faithfulness 能抓幻觉)")
    chunks0 = chunk_docs("pair")
    top0 = retrieve(QA[0][0], chunks0)
    ans_clean = make_answer(QA[0][0], [c for _, c in top0])
    ans_hallu = make_answer(QA[0][0], [c for _, c in top0], hallucinate=True)
    f_clean = faithfulness(ans_clean, [c for _, c in top0])
    f_hallu = faithfulness(ans_hallu, [c for _, c in top0])
    print("  干净回答 Faithfulness = {:.2f}".format(f_clean))
    print("  注入幻觉后 Faithfulness = {:.2f} {}"
          .format(f_hallu, "✓ 被抓出" if f_hallu < f_clean - 0.15 else "✗"))

    print("\n==> 3 种 chunking 对比")
    for strat in strategies:
        chunks = chunk_docs(strat)
        rels, faithfuls = [], []
        for q, _ in QA if MOCK else QA[:3]:
            top = retrieve(q, chunks)
            rel = sum(s for s, _ in top) / len(top)
            ans = make_answer(q, [c for _, c in top])
            f = faithfulness(ans, [c for _, c in top])
            rels.append(rel)
            faithfuls.append(f)
        table[strat] = (sum(rels) / len(rels), sum(faithfuls) / len(faithfuls),
                        len(chunks))
        print("  [{:<7}] 块数={:<4} Relevance={:.3f} Faithfulness={:.2f}".format(
            strat, len(chunks), table[strat][0], table[strat][1]))

    best = max(table.items(), key=lambda kv: kv[1][1])
    print("\nFaithfulness 最优 chunking: {} ({:.2f})".format(best[0], best[1][1]))
    print("""
要点: RAG 质量怎么量化
  1) 两个指标分开看: Relevance 管"检索得准不准" (embedding 相似度);
     Faithfulness 管"说得对不对" (答案逐句能否被检索证据支撑)。
  2) Faithfulness 是幻觉的量化: 注入无支撑句后指标显著下降 ——
     生产上用它做线上幻觉监控, 低分样本进人工复核队列。
  3) chunking 没有万能解: 句子级切块 Faithfulness 高 (证据精确),
     整段切块 Relevance 稳 (上下文完整) —— 按任务误差代价选择。
""")


if __name__ == "__main__":
    main()
