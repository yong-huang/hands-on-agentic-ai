"""
面试项目 8 — 长期记忆库（写入 + 检索注入）

覆盖面试题: 请设计一个 Agent 的记忆系统, 包括短期和长期记忆。

核心: SQLite 持久化 + 向量检索 + TopK 注入 system prompt:
  写入路径  显式("记住: ...") + 自动抽取(从对话里抽持久事实) 两种
  读取路径  query 向量化 → 余弦相似 TopK → 拼进 system prompt → 回答
  跨会话    写入后关库重开 (模拟新进程), 记忆仍在
embedding: 真实模式走本地 nomic-embed-text; MOCK 用 hash 词袋退化向量
(检索语义弱但链路完整, 离线可跑)。

运行:
  MOCK=1 python long_memory.py    # 离线: hash 向量 + 模板回答
  python long_memory.py           # 真实: nomic-embed-text + qwen3.8
"""

import json, math, os, re, sqlite3, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_store.sqlite3")
EMBED_MODEL = "nomic-embed-text"
DIM = 256


def http_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    for pat in (r"\[[^\[\]]*\]", r"\{[^{}]*\}"):
        for m in reversed(re.findall(pat, text, re.S)):
            try:
                return json.loads(m)
            except json.JSONDecodeError:
                continue
    return None


# ============================================================
# Embedder: 真实 nomic / MOCK hash 词袋
# ============================================================

def tokenize(text):
    text = re.sub(r"[^\w\u4e00-\u9fff]", " ", str(text).lower())
    toks = []
    for w in text.split():
        if re.fullmatch(r"[\u4e00-\u9fff]+", w):      # 中文: 二元组为主 + 单字弱权重
            bigrams = [w[i:i + 2] for i in range(len(w) - 1)]
            toks += bigrams or [w]
            toks += [c + "*" for c in w]              # unigram 加 * 后缀区分
        else:
            toks.append(w)
    return toks


def hash_vec(text):
    v = [0.0] * DIM
    for t in tokenize(text):
        v[hash(t) % DIM] += 0.5 if t.endswith("*") else 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed(text):
    if MOCK:
        return hash_vec(text)
    data = http_json(f"{BASE_URL}/embeddings", {"model": EMBED_MODEL, "input": text})
    return data["data"][0]["embedding"]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((math.sqrt(sum(x * x for x in a)) or 1.0) *
                  (math.sqrt(sum(x * x for x in b)) or 1.0))


# ============================================================
# MemoryStore: SQLite + 向量检索 (lib 对象可反复重开, 模拟跨进程)
# ============================================================

class MemoryStore:
    def __init__(self, db_path=DB_PATH):
        self.db = sqlite3.connect(db_path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS memories ("
            "id INTEGER PRIMARY KEY, text TEXT, kind TEXT, source TEXT, vec TEXT)")
        self.db.commit()

    def add(self, text, kind="fact", source="auto"):
        vec = json.dumps(embed(text))
        self.db.execute("INSERT INTO memories(text, kind, source, vec) VALUES (?,?,?,?)",
                        (text, kind, source, vec))
        self.db.commit()

    def search(self, query, k=3):
        qv = embed(query)
        rows = self.db.execute("SELECT text, kind, source, vec FROM memories").fetchall()
        scored = [(cosine(qv, json.loads(v)), t, kind, src) for t, kind, src, v in rows]
        scored.sort(reverse=True)
        return scored[:k]

    def close(self):
        self.db.close()


def extract_facts_auto(dialogue):
    """自动抽取: 真实用 LLM 出 JSON; MOCK 用规则正则。"""
    if MOCK:
        # 规范化事实句 (写入前先归一, 是记忆库的标准实践)
        facts, d = [], dialogue
        for pat, tpl in ((r"我(?:叫|的名字是)([\u4e00-\u9fff]{2,3})", "用户的名字是{}"),
                         (r"常(?:驻|在|居住于)([\u4e00-\u9fff]{2,4})", "用户的城市是{}"),
                         (r"咖啡只喝([\u4e00-\u9fff]+)", "用户的咖啡偏好是{}"),
                         (r"截止日?[是](\d+ ?月 ?\d+ ?日?)", "用户的项目截止日是{}")):
            m = re.search(pat, d)
            if m:
                facts.append(tpl.format(m.group(1)))
        return facts
    r = http_json(f"{BASE_URL}/chat/completions", {
        "model": MODEL, "temperature": 0.0, "max_tokens": 800,
        "messages": [{"role": "user", "content":
                      "从下面的对话里抽取值得长期记住的用户持久事实(姓名/城市/偏好/日期), "
                      '每条一句话。只输出 JSON: {"facts": ["...", ...]}\n\n' + dialogue}]})
    msg = r["choices"][0]["message"]
    data = extract_json(msg.get("content") or "") or \
        extract_json(msg.get("reasoning") or "") or {}
    if isinstance(data, list):
        items = data
    else:
        items = data.get("facts", [])
    return [str(f) for f in items][:5]


def answer_with_memory(store, question):
    """读取路径: 检索 TopK → 注入 system prompt → 回答。"""
    hits = store.search(question, k=3)
    mem_text = "\n".join(f"- {t}" for s, t, _, _ in hits if s > 0.05)
    system = f"你是助理。以下是关于该用户的长期记忆, 回答时优先使用:\n{mem_text}"
    print(f"    检索注入 TopK: " + " | ".join(f"{t}(score={s:.2f})" for s, t, _, _ in hits))
    if MOCK:
        good = [t for s, t, _, _ in hits if s > 0.05]
        return "[基于记忆] " + "；".join(good[:2] if good else ["(没有相关记忆)"])
    r = http_json(f"{BASE_URL}/chat/completions", {
        "model": MODEL, "temperature": 0.0, "max_tokens": 1500,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": question}]})
    msg = r["choices"][0]["message"]
    content = re.sub(r"<think>.*?</think>\s*", "", msg.get("content") or "", flags=re.S).strip()
    return content or (msg.get("reasoning") or "").strip()[-200:]


# ============================================================
# 跨会话演示: 会话 1 写入 → 关库 → "新进程" 开库读取
# ============================================================

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)          # 每次实验从空库开始
    print("=" * 72)
    print(f"长期记忆库 (写入 + 检索注入) -- {'MOCK (hash 向量)' if MOCK else '真实 nomic-embed-text'}")
    print("=" * 72)

    # ---- 会话 1: 显式写入 + 自动抽取 ----
    store = MemoryStore()
    print("\n==> 会话 1: 写入记忆")
    store.add("用户的项目代号叫夜莺", kind="fact", source="explicit")
    print("  [显式] 记住: 用户的项目代号叫夜莺")
    dialogue = ("你好, 我叫林晓, 常驻杭州。我们项目截止日是 10 月 18 日。"
                "对了, 我咖啡只喝燕麦拿铁。")
    for f in extract_facts_auto(dialogue):
        store.add(f, kind="fact", source="auto")
        print(f"  [自动抽取] {f}")
    n = store.db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    store.close()
    print(f"  库中共 {n} 条记忆, 关闭连接 (模拟会话结束)")

    # ---- 会话 2: 全新进程开库 ----
    print("\n==> 会话 2: 新进程重开数据库 (跨会话)")
    store2 = MemoryStore()
    checks = {"项目代号": ("夜莺", "我的项目代号是什么？"),
              "姓名": ("林晓", "我叫什么名字？"),
              "城市": ("杭州", "我在哪个城市？"),
              "咖啡": ("燕麦拿铁", "我咖啡喝什么？")}
    ok_all = 0
    for name, (expect, q) in checks.items():
        ans = answer_with_memory(store2, q)
        ok = expect in ans
        ok_all += ok
        print(f"  Q: {q}\n  A: {ans[:70]}  {'✓' if ok else '✗'}")
    print(f"\n跨会话记忆测试: {ok_all}/4 正确")

    # ---- 与项目 7 组合: 完整记忆系统 ----
    print("""
==> 记忆系统全貌 (短期=项目7, 长期=本项目)
  用户输入 ──► 短期记忆 (窗口/摘要, 本会话上下文) ──► LLM
                  │ 会话结束/关键事实
                  ▼
              写入路径: 显式"记住" + 自动抽取
                  ▼
              长期记忆库 (SQLite+向量, 跨会话)
                  │ 检索 TopK 注入
                  ▼
              下一次会话的 system prompt ◄── 读取路径
""")
    print("要点: 记忆系统 = 短期(管理上下文预算) + 长期(跨会话持久化)。")
    print("      写入要过滤(不是什么都存), 读取要检索(不是全量塞入)——")
    print("      这一对读写路径就是'设计一个记忆系统'大题的骨架。")
    store2.close()
    os.remove(DB_PATH)              # 清理实验产物


if __name__ == "__main__":
    main()
