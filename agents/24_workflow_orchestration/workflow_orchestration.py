"""
工作流编排 — Fan-out/Fan-in 评审 + 反思修订循环

项目 25 的 Worker 是"各干各的"; 本篇的编排多两个机制:
- Fan-out/Fan-in: 同一份稿件扇出给 3 个不同视角的评审员 (准确性/结构/风格)
  并行评审, 扇入汇总所有意见
- 反思循环: 综合评分 < 阈值时, 带着全部意见回炉修订, 再评, 直到达标
  或到达最大轮数

流程: 初稿 -> [扇出] 准确性/结构/风格 三评审并行 -> [扇入] 汇总意见与评分
      -> 评分 >= 8 ? -> 是: 定稿 / 否: 修订后重新评审 (最多 MAX_ROUNDS 轮)
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TOPIC = "如何为团队编写高质量的 Agent 开发规范"
PASS_SCORE = 8
MAX_ROUNDS = 2

REVIEWERS = [
    {"id": "accuracy", "name": "准确性评审", "focus": "事实是否正确、建议是否可执行"},
    {"id": "structure", "name": "结构评审", "focus": "逻辑分层是否清晰、条目是否互斥"},
    {"id": "style", "name": "风格评审", "focus": "是否简洁、可读、无空话"},
]

REVIEW_PROMPT = """你是{name}，评审重点: {focus}。

评审以下稿件《{topic}》:
{draft}

只输出 JSON: {{"score": 1-10 整数, "comment": "一句话最关键的评审意见"}}"""


def chat(messages, temperature=0.3):
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": temperature, "num_predict": 500},
    }, timeout=180)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def extract_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    for candidate in ([m.group(1)] if m else []) + [text]:
        try:
            return json.loads(re.search(r"\{.*\}", candidate, re.S).group(0))
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


# ============================================================
# Fan-out: 并行评审 / Fan-in: 汇总意见
# ============================================================

def review_once(reviewers, draft, round_no):
    def one(rv):
        raw = chat([{"role": "user", "content":
                     REVIEW_PROMPT.format(name=rv["name"], focus=rv["focus"],
                                          topic=TOPIC, draft=draft)}], temperature=0.0)
        verdict = extract_json(raw) or {"score": 5, "comment": raw[:60]}
        return {"reviewer": rv["name"], "score": int(verdict.get("score", 5)),
                "comment": str(verdict.get("comment", ""))[:80],
                "elapsed": None}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(reviewers)) as pool:
        reviews = list(pool.map(one, reviewers))
    wall = round(time.time() - t0, 1)
    for r in reviews:
        print(f"    [{r['reviewer']}] {r['score']}/10  {r['comment']}")
    print(f"    (扇出 {len(reviewers)} 路并行, 墙钟 {wall}s)")
    avg = round(sum(r["score"] for r in reviews) / len(reviews), 1)
    feedback = "\n".join(f"- {r['reviewer']}({r['score']}分): {r['comment']}" for r in reviews)
    return avg, feedback


# ============================================================
# 编排主循环: 生成 -> 扇出评审 -> 扇入汇总 -> 反思修订
# ============================================================

def run_real():
    print("=" * 60)
    print(f"工作流编排 -- 真实模式 ({MODEL})")
    print(f"任务: 撰写《{TOPIC}》, 三路评审均分 ≥{PASS_SCORE} 或 {MAX_ROUNDS} 轮后定稿")
    print("=" * 60)

    print("\n==> [round 0] 生成初稿")
    draft = chat([{"role": "user", "content":
                   f"写一篇《{TOPIC}》的规范短文，200 字左右，分点陈述。"}])
    print(f"  初稿 {len(draft)} 字")

    for round_no in range(1, MAX_ROUNDS + 1):
        print(f"\n==> [round {round_no}] Fan-out: 三路并行评审")
        avg, feedback = review_once(REVIEWERS, draft, round_no)
        print(f"    均分: {avg}/10")
        if avg >= PASS_SCORE:
            print(f"\n==> 定稿 (均分 {avg} ≥ {PASS_SCORE})")
            print(f"\n{draft[:400]}{'…' if len(draft) > 400 else ''}")
            return
        print(f"\n==> [round {round_no}] 反思修订 (带全部评审意见回炉)")
        draft = chat([{"role": "user", "content":
                       f"按评审意见修改这篇《{TOPIC}》稿件（保持 200 字左右）:\n\n"
                       f"原稿:\n{draft}\n\n评审意见:\n{feedback}"}])
        print(f"  修订稿 {len(draft)} 字")

    print(f"\n==> 达到最大轮数, 以当前版本定稿 (最后一轮均分 {avg})")
    print(f"\n{draft[:400]}{'…' if len(draft) > 400 else ''}")


# ============================================================
# Demo 模式: 预置评审意见, 真实走编排结构 (离线)
# ============================================================

CANNED_REVIEWS = [
    {"round": 1, "scores": [6, 7, 7],
     "comments": ["缺少可执行的检查清单", "三个部分之间缺少优先级", "有少量空话"]},
    {"round": 2, "scores": [8, 8, 9],
     "comments": ["清单已补充", "已标注优先级", "表述紧凑"]},
]
CANNED_DRAFTS = [
    "初稿: 一、写清楚背景。二、定义术语。三、定期回顾。",
    "修订稿: 一、写清楚背景与目标（可检验）。二、按 P0/P1 标注术语优先级。"
    "三、附检查清单：每周对照回顾。四、示例：禁止把'应该'写成规范——要写成'必须'。",
]


def run_demo():
    print("=" * 60)
    print("工作流编排 -- Demo 模式（预置评审, 编排结构真实运行）")
    print("=" * 60)
    print(f"任务: 撰写《{TOPIC}》\n")

    draft = CANNED_DRAFTS[0]
    for i, canned in enumerate(CANNED_REVIEWS, 1):
        print(f"==> [round {i}] Fan-out: 三路并行评审")
        avg = round(sum(canned["scores"]) / 3, 1)
        for (score, comment) in zip(canned["scores"], canned["comments"]):
            print(f"    [评审] {score}/10  {comment}")
        print(f"    均分: {avg}/10")
        if avg >= PASS_SCORE:
            print(f"\n==> 定稿 (均分 {avg} ≥ {PASS_SCORE})\n")
            print(f"  {CANNED_DRAFTS[1]}")
            return
        print(f"\n==> [round {i}] 反思修订 (带全部意见回炉)\n")
        draft = CANNED_DRAFTS[min(i, len(CANNED_DRAFTS) - 1)]

    print(f"最终稿: {draft}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        print("Usage: python workflow_orchestration.py [--demo]\n"
              "  --demo   : 离线演示编排结构（无需 Ollama）\n"
              "  (无参数)  : 真实模式, 扇出评审 + 反思修订\n")
        run_real()
