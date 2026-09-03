"""
记忆更新策略 — 重要性判定 + 查重 + 融合

项目 17 的长期记忆是"只进不出": 同一句"喜欢吃火锅"被沉淀了两次, 琐碎事实
和关键事实混在一起。本篇给长期记忆装上管理器, 每条新事实经过三重决策:

  1. 重要性判定  LLM 打分 0-10, 低于阈值直接丢弃 (琐碎不入库)
  2. 查重        向量检索最相似旧记忆, 高度相似 (>=0.85) 判为重复, 跳过
  3. 融合        中度相似 (0.70-0.85) 交给 LLM 合并——偏好变化时更新旧事实
                 低相似 (<0.70) 作为新记忆入库

对照实验: 同一组用户陈述, 分别跑 17 式"裸入库"和本篇"托管入库",
对比最终记忆库的质量——裸入库堆满重复与琐碎, 托管入库干净且自我更新。

Decision: LLM 判定 + 向量查重 + LLM 融合; Embedding 用本地 nomic-embed-text。
"""

import json
import math
import os
import sys
import difflib
import requests

BASE_URL = "http://localhost:11434/api/chat"
EMBED_URL = "http://localhost:11434/api/embeddings"
MODEL = "qwen3.8:latest"
EMBED_MODEL = "nomic-embed-text"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

IMPORTANCE_FLOOR = 4      # 重要性 0-10, 低于 4 不入库
DUP_THRESHOLD = 0.85      # 相似度 >= 0.85 判为重复
MERGE_THRESHOLD = 0.70    # 0.70-0.85 触发 LLM 融合


# ============================================================
# 基础设施: embedding / 向量 / LLM (与项目 17 同款, 独立成函数)
# ============================================================

def embed(text):
    resp = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=60)
    resp.raise_for_status()
    return resp.json()["embedding"]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def chat(messages, temperature=0.0):
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": temperature, "num_predict": 200},
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


# ============================================================
# 三重决策
# ============================================================

def judge_importance(statement):
    """LLM 给陈述的重要性打分 0-10 (10 = 核心用户画像, 0 = 完全琐碎)。"""
    prompt = ("给下面这条用户陈述的长期记忆价值打分（0-10 的整数）。\n"
              "10 = 身份/偏好/重要约定；0 = 寒暄、天气等完全琐碎的内容。\n"
              "只输出整数。\n\n"
              f"陈述: {statement}")
    try:
        return int("".join(c for c in chat([{"role": "user", "content": prompt}]) if c.isdigit())[:2] or 0)
    except (ValueError, requests.RequestException):
        return 5   # 判定失败时保守放行, 不静默丢弃


def llm_merge(old_fact, new_info):
    """融合: 新信息更新旧事实, 输出一条合并后的记忆。"""
    prompt = ("以下是一条旧记忆和关于用户的新信息。把新信息合并进旧记忆，"
              "输出一条更新后的记忆（一句话，保留仍然有效的内容，覆盖过时内容）。\n\n"
              f"旧记忆: {old_fact}\n新信息: {new_info}\n\n只输出合并后的记忆。")
    return chat([{"role": "user", "content": prompt}])


class ManagedMemory:
    """带三重决策的长期记忆库。"""

    def __init__(self):
        self.items = []      # [{"text", "vec", "importance"}]
        self.log = []        # 决策审计: (statement, decision, detail)

    def remember(self, statement):
        """返回 (decision, detail): added / skip_trivial / skip_duplicate / merged"""
        imp = judge_importance(statement)
        if imp < IMPORTANCE_FLOOR:
            self.log.append((statement, "skip_trivial", f"重要性 {imp} < {IMPORTANCE_FLOOR}"))
            return "skip_trivial", f"重要性 {imp}"

        vec = embed(statement)
        best_sim, best = max(
            ((cosine(vec, it["vec"]), it) for it in self.items),
            default=(0.0, None))

        if best_sim >= DUP_THRESHOLD:
            self.log.append((statement, "skip_duplicate", f"与「{best['text']}」相似度 {best_sim:.2f}"))
            return "skip_duplicate", best["text"]

        if best_sim >= MERGE_THRESHOLD:
            merged = llm_merge(best["text"], statement)
            best["text"] = merged
            best["vec"] = embed(merged)
            best["importance"] = max(best["importance"], imp)
            self.log.append((statement, "merged", f"与「{best['text'][:24]}…」融合 (相似度 {best_sim:.2f})"))
            return "merged", merged

        self.items.append({"text": statement, "vec": vec, "importance": imp})
        self.log.append((statement, "added", f"新记忆 (重要性 {imp})"))
        return "added", statement


class NaiveMemory:
    """17 式裸入库: 有statement就存, 用于对照。"""

    def __init__(self):
        self.items = []

    def remember(self, statement):
        self.items.append(statement)


# ============================================================
# 对照实验: 同一组陈述, 裸入库 vs 托管入库
# ============================================================

STATEMENTS = [
    "我叫张三，最喜欢吃火锅",
    "我正在学习 AI Agent 开发",
    "其实我现在更爱吃日料了，火锅吃得少",
    "我叫张三，喜欢吃火锅",
    "今天天气真不错",
]


def run_real():
    print("=" * 60)
    print(f"记忆更新策略 -- 真实模式 ({MODEL} + {EMBED_MODEL})")
    print("=" * 60)
    naive, managed = NaiveMemory(), ManagedMemory()

    for i, stmt in enumerate(STATEMENTS, 1):
        naive.remember(stmt)
        decision, detail = managed.remember(stmt)
        print(f"\n[{i}] 「{stmt}」")
        print(f"    裸入库: 直接存 -> 库共 {len(naive.items)} 条")
        print(f"    托管:   {decision} ({detail}) -> 库共 {len(managed.items)} 条")

    print("\n" + "=" * 60)
    print("裸入库最终记忆库 (含重复与琐碎):")
    for it in naive.items:
        print(f"  - {it}")
    print("托管入库最终记忆库:")
    for it in managed.items:
        print(f"  - {it['text']}  (重要性 {it['importance']})")
    print("=" * 60)
    print(f"对比: 裸 {len(naive.items)} 条 vs 托管 {len(managed.items)} 条——"
          "重复被跳过, 偏好变化被融合, 琐碎被丢弃。")
    print("决策审计:")
    for stmt, decision, detail in managed.log:
        print(f"  [{decision:14s}] {stmt} -> {detail}")


# ============================================================
# Demo 模式: 离线模拟三重决策 (difflib 相似度 + 规则判定)
# ============================================================

def fake_importance(stmt):
    trivial = ("天气", "今天不错", "哈哈")
    return 2 if any(t in stmt for t in trivial) else 7


def fake_similar(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def fake_merge(old, new):
    return f"{old}（已更新: {new}）"


class FakeManagedMemory:
    """离线托管库: difflib 查重 + 规则判定, 决策逻辑与真实版一致。"""

    def __init__(self):
        self.items, self.log = [], []

    def remember(self, stmt):
        imp = fake_importance(stmt)
        if imp < IMPORTANCE_FLOOR:
            self.log.append((stmt, "skip_trivial", f"重要性 {imp}")); return
        best_sim, best = max(((fake_similar(stmt, it), it) for it in self.items),
                             default=(0.0, None))
        if best_sim >= DUP_THRESHOLD:
            self.log.append((stmt, "skip_duplicate", f"与「{best}」相似 {best_sim:.2f}")); return
        if best_sim >= MERGE_THRESHOLD:
            merged = fake_merge(best, stmt)
            self.items[self.items.index(best)] = merged
            self.log.append((stmt, "merged", f"与「{best}」相似 {best_sim:.2f}")); return
        self.items.append(stmt)
        self.log.append((stmt, "added", f"新记忆 (重要性 {imp})"))


def run_demo():
    print("=" * 60)
    print("记忆更新策略 -- Demo 模式（difflib 查重 + 规则判定, 无需 Ollama）")
    print("=" * 60)
    naive, managed = NaiveMemory(), FakeManagedMemory()
    for stmt in STATEMENTS:
        naive.remember(stmt)
        before = len(managed.items)
        managed.remember(stmt)
        decision, detail = managed.log[-1][1], managed.log[-1][2]
        mark = {"added": "+", "merged": "~", "skip_duplicate": "·", "skip_trivial": "×"}[decision]
        print(f"  [{mark}] 「{stmt}」-> {decision} ({detail})  库 {before}->{len(managed.items)}")

    print("\n裸入库:", naive.items)
    print("托管入库:")
    for it in managed.items:
        print(f"  - {it}")
    print("\n要点: 三重决策 = 重要性过滤 + 查重 + 融合; 真实模式用 LLM 打分、")
    print("      embedding 查重与 LLM 融合, 决策逻辑完全一致。")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        print("Usage: python memory_update.py [--demo]\n"
              "  --demo   : 离线模拟三重决策（无需 Ollama）\n"
              "  (无参数)  : 真实模式, 裸入库 vs 托管入库对照实验\n")
        run_real()
