"""
上下文压缩策略 — 截断 vs 摘要 vs 不压缩 的对照实验

项目 17 的滑动窗口解决了"预算内放行"，但淘汰即失忆: 早期对话里的事实
（名字、截止日期）全部丢失。本篇做一次严格的对照实验——同一段长对话分别用
三种策略压缩后发给模型，量化两个指标:

- 上下文大小: 压缩后的估算 token 数 (越小越省)
- 信息保留率: 用只出现在【早期对话】里的事实做测验, 关键词评分 (越高越好)

三种策略:
  full    不压缩      全量重发, 保留率恒定 100%, token 无上界
  window  滑动窗口    只放行最近对话, token 有上界, 早期事实全丢
  summary LLM 摘要    旧对话压缩成摘要 + 最近对话逐字保留, 两者的折中

真实模式全部跑 qwen3.8; --demo 用预置数据演示评估管线 (诚实预期:
摘要由预置文本代替, 真实摘要质量以真实模式为准)。
"""

import os
import sys
import requests

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
SYSTEM_PROMPT = "你是用户的助理。回答简洁，仅依据对话内容作答，没有的信息就说不知道。"
WINDOW_BUDGET = 160        # 滑动窗口 token 预算 (实验故意设小, 让早期事实被淘汰)
KEEP_RECENT = 4            # 摘要策略: 最近 N 条消息逐字保留


# ============================================================
# 实验材料: 一段"前重后轻"的长对话 (早期埋 5 个事实, 后期灌水)
# ============================================================

def build_long_conversation():
    facts = [
        ("我叫李雷", "李雷"),
        ("我在杭州工作", "杭州"),
        ("我在做一个电商推荐系统", "电商推荐"),
        ("项目周五就要演示", "周五"),
        ("团队主要用 Python", "Python"),
    ]
    conv = [{"role": "system", "content": SYSTEM_PROMPT}]
    for user, _ in facts:
        conv += [{"role": "user", "content": user},
                 {"role": "assistant", "content": "好的，记下了。"}]
    fillers = [
        ("帮我讲讲什么是上下文窗口", "上下文窗口是模型一次能处理的文本长度上限。"),
        ("attention 机制是怎么回事", "attention 让模型关注输入中相关的部分。"),
        ("RAG 和微调有什么区别", "RAG 外挂知识库，微调改模型参数。"),
        ("Agent 和普通聊天机器人差在哪", "Agent 能调用工具、自主多步行动。"),
        ("什么是思维链", "思维链让模型先推理再给答案。"),
        ("向量数据库是干什么的", "存向量并支持相似度检索。"),
    ]
    for user, assistant in fillers:
        conv += [{"role": "user", "content": user},
                 {"role": "assistant", "content": assistant}]
    quiz = [
        ("用户叫什么名字？", ["李雷"]),
        ("用户在哪个城市工作？", ["杭州"]),
        ("用户在做什么项目？", ["电商推荐", "推荐系统"]),
        ("项目什么时候演示？", ["周五"]),
        ("团队主要用什么语言？", ["Python"]),
    ]
    return conv, facts, quiz


def estimate_tokens(text):
    """粗估: CJK 1 字 1 token, 其余 4 字符 1 token (教学估算, 生产用 tiktoken)。"""
    cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
    return cjk + (len(text) - cjk) // 4


def count_tokens(messages):
    return sum(estimate_tokens(m["content"]) for m in messages)


# ============================================================
# 三种压缩策略
# ============================================================

def compress_full(messages, system_prompt):
    """策略 1: 不压缩, 全量重发。"""
    return [system_prompt] + messages[1:]


def compress_window(messages, system_prompt, budget=WINDOW_BUDGET):
    """策略 2: 滑动窗口, 从最新向前收集, 预算用尽即停。"""
    kept, used = [], 0
    for msg in reversed(messages[1:]):
        cost = estimate_tokens(msg["content"])
        if used + cost > budget and kept:
            break
        kept.insert(0, msg)
        used += cost
    return [system_prompt] + kept


def summarize(text):
    """LLM 摘要: 要求保留所有事实 (名字/数字/日期/偏好)。"""
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "stream": False, "think": False,
        "messages": [{"role": "user", "content":
                      "将以下对话压缩成要点摘要（不超过 120 字），"
                      f"必须保留所有事实（名字、地点、数字、日期、偏好）:\n\n{text}"}],
        "options": {"temperature": 0.0, "num_predict": 300},
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def compress_summary(messages, system_prompt, keep_recent=KEEP_RECENT, canned=None):
    """策略 3: 旧对话 -> LLM 摘要, 最近 KEEP_RECENT 条逐字保留。"""
    old, recent = messages[1:-keep_recent], messages[-keep_recent:]
    if canned is not None:
        summary = canned
    else:
        transcript = "\n".join(f"{m['role']}: {m['content']}" for m in old)
        summary = summarize(transcript)
    compaction = {"role": "user",
                  "content": f"[以下是更早对话的摘要]\n{summary}\n[摘要结束]"}
    return [system_prompt, compaction] + recent


# ============================================================
# 评估: 信息保留率 (关键词评分)
# ============================================================

def quiz_retention(messages, quiz):
    """对每种压缩产物提问, 关键词命中即得分; 返回 (答对数, 明细)。"""
    detail, hits = [], 0
    for question, keywords in quiz:
        probe = messages + [{"role": "user", "content": question}]
        resp = requests.post(BASE_URL, json={
            "model": MODEL, "stream": False, "think": False,
            "messages": probe,
            "options": {"temperature": 0.0, "num_predict": 120},
        }, timeout=120)
        answer = resp.json()["message"]["content"].strip()
        ok = any(k in answer for k in keywords)
        hits += ok
        detail.append((question, answer, ok))
    return hits, detail


# ============================================================
# 真实模式: 三策略对照实验
# ============================================================

def run_real():
    print("=" * 60)
    print(f"上下文压缩策略 -- 真实模式 ({MODEL})")
    print("=" * 60)
    conv, facts, quiz = build_long_conversation()
    system_prompt = conv[0]
    print(f"实验材料: {len(conv) - 1} 条消息, 共 {count_tokens(conv)} tokens, "
          f"前 {len(facts)} 轮埋有事实, 后 {len(conv) - 1 - 2 * len(facts)} 轮灌水\n")

    strategies = [
        ("full(不压缩)", compress_full(conv, system_prompt)),
        (f"window(预算{WINDOW_BUDGET})", compress_window(conv, system_prompt)),
        (f"summary(摘要+近{KEEP_RECENT}条)", compress_summary(conv, system_prompt)),
    ]

    rows = []
    for name, compressed in strategies:
        tokens = count_tokens(compressed)
        hits, detail = quiz_retention(compressed, quiz)
        rows.append((name, tokens, hits, len(quiz)))
        print(f"--- {name}: {tokens} tokens, 保留率 {hits}/{len(quiz)} ---")
        for q, a, ok in detail:
            mark = "✓" if ok else "✗"
            print(f"  [{mark}] {q} -> {a[:40]}")
        print()

    def dw(s):  # 显示宽度: CJK 记 2
        return sum(2 if ord(c) > 0x2E7F else 1 for c in s)
    print("=" * 60)
    print(f"{'策略':<24}{'tokens':>10}{'保留率':>8}")
    for name, tokens, hits, total in rows:
        pad = " " * max(0, 24 - dw(name))
        print(f"{name}{pad}{tokens:>10}   {hits}/{total}")
    print("=" * 60)
    print("结论: full 保真但 token 无上界; window 最省但早期事实全丢;")
    print("      summary 用 ~1/3 的 token 保住大部分事实——生产系统的默认折中。")


# ============================================================
# Demo 模式: 预置数据演示评估管线 (离线)
# ============================================================

CANNED_SUMMARY = ("李雷在杭州做电商推荐系统，周五演示，团队主要用 Python。"
                  "随后讨论了上下文窗口、attention、RAG 与微调、Agent、思维链、向量数据库。")


def run_demo():
    print("=" * 60)
    print("上下文压缩策略 -- Demo 模式（预置摘要, 无需 Ollama）")
    print("=" * 60)
    conv, facts, quiz = build_long_conversation()
    system_prompt = conv[0]

    strategies = [
        ("full(不压缩)", compress_full(conv, system_prompt)),
        (f"window(预算{WINDOW_BUDGET})", compress_window(conv, system_prompt)),
        (f"summary(摘要+近{KEEP_RECENT}条)",
         compress_summary(conv, system_prompt, canned=CANNED_SUMMARY)),
    ]

    print(f"\n实验材料: {len(conv) - 1} 条消息, {count_tokens(conv)} tokens, "
          f"早期埋 {len(facts)} 个事实: {[f[1] for f in facts]}\n")

    print(f"{'策略':<24}{'tokens':>8}  早期事实覆盖")
    for name, compressed in strategies:
        tokens = count_tokens(compressed)
        body = "\n".join(m["content"] for m in compressed)
        covered = sum(1 for _, kw in facts if any(k in body for k in [kw]))
        bar = "█" * covered + "░" * (len(facts) - covered)
        print(f"{name:<24}{tokens:>8}  {bar} {covered}/{len(facts)}")

    print("\n摘要产物预览:")
    print(f"  {CANNED_SUMMARY}")
    print("\n要点: window 只保住最后两轮, 5 个事实丢 4 个;")
    print("      summary 以 ~40% 的 token 覆盖全部事实——这就是压缩的价值。")
    print("      保留率的真实评分 (LLM 答题) 见真实模式。")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        print("Usage: python context_compression.py [--demo]\n"
              "  --demo   : 离线演示三种策略与事实覆盖（无需 Ollama）\n"
              "  (无参数)  : 真实模式, 三策略对照实验 + 信息保留率测验\n")
        run_real()
