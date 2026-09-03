"""
对话记忆与长期记忆 — 滑动窗口 + 向量检索 + MEMORY.md 沉淀

项目 16 的 Memory 是写死的常量。本篇让 Agent 真正拥有两层记忆:
- 短期记忆: messages 滑动窗口——上下文预算内保留最近对话, 超出即淘汰
- 长期记忆: 向量库 + MEMORY.md——值得记的事实被 embedding 入库,
  新对话按相似度检索 top-k 注入 System Prompt, 跨会话可用

两层记忆的分工:
  短期 (窗口内)      长期 (检索注入)
  ───────────        ───────────
  逐字保留           压缩成事实
  自动淘汰           永久沉淀
  无需判断           LLM 判定"值得记"
  本回合就生效       下次对话才生效

向量库为教学实现: JSON 落盘 + 纯 Python 余弦相似度 (数十条记忆足够),
生产环境换 chromadb / 专用向量数据库 (项目 21)。
Embedding 用本地 nomic-embed-text (768 维), 不需要任何 API Key。
"""

import json
import math
import os
import sys
import requests

BASE_URL = "http://localhost:11434/api/chat"
EMBED_URL = "http://localhost:11434/api/embeddings"
MODEL = "qwen3.8:latest"
EMBED_MODEL = "nomic-embed-text"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(SCRIPT_DIR, "memory_store.json")
MEMORY_MD = os.path.join(SCRIPT_DIR, "MEMORY.md")
SYSTEM_PROMPT = "你是用户的个人助理。回答简洁，优先使用【相关记忆】中的信息。"

MAX_WINDOW_TOKENS = 300   # 短期记忆预算: 超出即淘汰最旧对话
TOP_K = 2                 # 每次注入的长期记忆条数
SIM_THRESHOLD = 0.5       # 相似度低于此值的记忆不注入


# ============================================================
# Embedding 与向量库
# ============================================================

def embed(text):
    """文本 -> 768 维向量 (本地 nomic-embed-text)。"""
    resp = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=60)
    resp.raise_for_status()
    return resp.json()["embedding"]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class VectorStore:
    """教学级向量库: JSON 落盘 + 纯 Python 余弦相似度。"""

    def __init__(self, path):
        self.path = path
        self.items = []                      # [{text, vec}]
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.items = json.load(f)

    def add(self, text, vec):
        self.items.append({"text": text, "vec": vec})
        self._save()

    def search(self, query_vec, top_k=2, threshold=0.0):
        scored = [(cosine(query_vec, it["vec"]), it["text"]) for it in self.items]
        scored.sort(key=lambda x: -x[0])
        return [(s, t) for s, t in scored[:top_k] if s >= threshold]

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=2)

    def __len__(self):
        return len(self.items)


# ============================================================
# 短期记忆: messages 滑动窗口
# ============================================================

def estimate_tokens(text):
    """粗估: CJK 1 字 1 token, 其余 4 字符 1 token (教学估算, 生产用 tiktoken)。"""
    cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
    return cjk + (len(text) - cjk) // 4


class ShortTermMemory:
    """保留全部对话, 但 build_window() 只放行预算内的最近对话。"""

    def __init__(self, system_prompt):
        self.system_prompt = system_prompt
        self.messages = []                   # [{"role", "content"}] 不含 system

    def add(self, role, content):
        self.messages.append({"role": role, "content": content})

    def build_window(self, max_tokens=MAX_WINDOW_TOKENS):
        """从最新消息向前收集, 预算用尽即停; system 消息永远保留。"""
        window, budget = [], max_tokens
        for msg in reversed(self.messages):
            cost = estimate_tokens(msg["content"])
            if budget - cost < 0 and window:
                break
            window.insert(0, msg)
            budget -= cost
        dropped = len(self.messages) - len(window)
        return [{"role": "system", "content": self.system_prompt}] + window, dropped


# ============================================================
# 长期记忆: 事实提取与沉淀
# ============================================================

def chat(messages, temperature=0.3):
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": temperature, "num_predict": 300},
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def extract_fact(user_msg, assistant_msg):
    """LLM 判定这轮对话里是否值得存一条长期记忆; 没有则返回 None。"""
    prompt = (
        "从下面的对话中提取值得长期记住的用户事实（偏好、身份、约定等）。\n"
        "只输出事实本身，一句话；如果没有值得记的，只输出 NONE。\n\n"
        f"用户: {user_msg}\n助手: {assistant_msg}"
    )
    fact = chat([{"role": "user", "content": prompt}], temperature=0.0)
    return None if (not fact or "NONE" in fact.upper()) else fact


def settle_memory(fact, store):
    """沉淀: 向量入库 + 追加 MEMORY.md。"""
    store.add(fact, embed(fact))
    with open(MEMORY_MD, "a", encoding="utf-8") as f:
        f.write(f"- {fact}\n")


def recall(user_msg, store):
    """检索: 用户输入 -> 向量 -> top-k 相似记忆。"""
    return store.search(embed(user_msg), top_k=TOP_K, threshold=SIM_THRESHOLD)


def build_messages(user_msg, hits):
    """短期窗口 + 长期检索结果 -> 完整请求。"""
    stm = ShortTermMemory(SYSTEM_PROMPT)
    stm.add("user", user_msg)
    if hits:
        lines = "\n".join(f"- {t} (相似度 {s:.2f})" for s, t in hits)
        stm.system_prompt += f"\n\n【相关记忆】\n{lines}"
    window, dropped = stm.build_window()
    return window, dropped


# ============================================================
# Demo 模式: 离线模拟两层记忆 (伪向量验证管线)
# ============================================================

def fake_embed(text):
    """确定性伪向量: 真实模式才用 nomic-embed-text。"""
    v = [0.0] * 32
    for i, ch in enumerate(text):
        v[(i * 7 + ord(ch)) % 32] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def run_demo():
    print("=" * 60)
    print("对话记忆与长期记忆 -- Demo 模式（伪向量, 无需 Ollama）")
    print("=" * 60)
    store = VectorStore(os.path.join(SCRIPT_DIR, "_demo_store.json"))

    print("\n[1] 写入两条长期记忆")
    for fact in ["用户叫张三，喜欢吃火锅", "用户正在学习 AI Agent 开发"]:
        store.add(fact, fake_embed(fact))
        print(f"  + {fact}")

    print("\n[2] 检索: '用户饮食偏好是什么?'")
    for s, t in store.search(fake_embed("用户饮食偏好是什么?"), top_k=2):
        print(f"  {s:.3f}  {t}")

    print("\n[3] 短期记忆滑动窗口 (预算 60 token)")
    stm = ShortTermMemory(SYSTEM_PROMPT)
    for i in range(1, 5):
        stm.add("user", f"这是第 {i} 轮对话，内容比较长一些用来消耗预算。")
        stm.add("assistant", f"好的，这是第 {i} 轮的回复。")
    window, dropped = stm.build_window(max_tokens=60)
    print(f"  全部 {len(stm.messages)} 条 -> 窗口放行 {len(window) - 1} 条 (淘汰 {dropped} 条)")
    for m in window[1:]:
        print(f"  [{m['role']}] {m['content'][:24]}...")

    print("\n[4] 沉淀 MEMORY.md (模拟)")
    print(f"  会写入: {MEMORY_MD}")
    print("\n要点: 短期保真但会淘汰, 长期压缩但跨会话——两层各司其职。")
    print("      真实模式: 真 embedding + 真 LLM 提取, 验证跨会话召回。")
    os.remove(store.path)   # demo 临时库用完即弃


# ============================================================
# 真实模式: 两段会话验证跨会话记忆
# ============================================================

def run_real():
    print("=" * 60)
    print(f"对话记忆与长期记忆 -- 真实模式 ({MODEL} + {EMBED_MODEL})")
    print("=" * 60)
    store = VectorStore(STORE_PATH)
    print(f"\n向量库现有 {len(store)} 条长期记忆: {STORE_PATH}")

    def turn(stm, user_msg):
        """一轮对话: 检索 -> 生成 -> 提取 -> 沉淀。"""
        hits = recall(user_msg, store)
        if hits:
            print(f"  🔎 检索到 {len(hits)} 条相关记忆: " +
                  "; ".join(f"{t}({s:.2f})" for s, t in hits))
        else:
            print("  🔎 无相关记忆")
        messages, dropped = build_messages(user_msg, hits)
        reply = chat(messages)
        stm.add("user", user_msg)
        stm.add("assistant", reply)
        print(f"  🤖 {reply}\n")
        fact = extract_fact(user_msg, reply)
        if fact:
            settle_memory(fact, store)
            print(f"  💾 沉淀长期记忆: {fact} (库共 {len(store)} 条)\n")

    # ---- 会话 1: 告诉 Agent 两件事 ----
    print("\n----- 会话 1 -----")
    stm1 = ShortTermMemory(SYSTEM_PROMPT)
    turn(stm1, "我叫张三，最喜欢吃火锅，但不能吃辣。")
    turn(stm1, "我正在学习 AI Agent 开发，最近在学记忆系统。")

    # ---- 会话 2: 新会话, 只靠长期记忆回答 ----
    print("\n----- 会话 2 (全新的 ShortTermMemory, 模拟重启) -----")
    stm2 = ShortTermMemory(SYSTEM_PROMPT)
    turn(stm2, "我叫什么名字？我喜欢吃什么？")
    turn(stm2, "我学到哪里了？")

    print("会话 2 没有任何短期历史——答对说明长期记忆跨会话生效。")
    print(f"MEMORY.md 位置: {MEMORY_MD}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        print("Usage: python memory.py [--demo]\n"
              "  --demo   : 离线演示两层记忆机制（无需 Ollama）\n"
              "  (无参数)  : 真实模式, 两段会话验证跨会话记忆召回\n")
        run_real()
