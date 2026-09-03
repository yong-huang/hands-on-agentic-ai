"""
Manager-Worker 多 Agent 协作 — 任务分解 + 并行执行 + 结果合并

单个 Agent 做复杂任务时上下文容易超载。Manager-Worker 模式把"分工"与
"执行"分离: Manager (LLM) 把任务分解成带角色的子任务, 多个 Worker (各自
带角色提示词的 LLM) **并行**执行, Manager 再把所有结果合并成最终产出。

  Manager                    Workers (并行)                Merge
  ──────                     ────────                      ─────
  分解任务为子任务             各自带角色提示词               合并所有结果
  指定每个 Worker 的角色      只看自己的子任务               产出最终答案
  不执行具体工作              互相不可见                     消除冗余与冲突

并行用 ThreadPoolExecutor (LLM 调用是 IO 密集, 线程即可真并行)。
Demo 模式: 预置分解与产出, 离线演示编排结构。
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

MANAGER_PROMPT = """你是任务调度 Manager。把用户任务分解为 2-3 个可独立执行的子任务，
并为每个子任务指定一个 Worker 角色:
- researcher: 收集事实、概念与资料
- analyst: 分析原理、优劣与适用场景

只输出 JSON（不要其他文字）:
{"subtasks": [{"role": "researcher", "task": "子任务描述"}]}"""

ROLE_PROMPTS = {
    "researcher": "你是资料研究员。只输出事实与概念清单，不要展开议论。",
    "analyst": "你是分析师。输出分析要点，包含优劣对比与适用建议。",
    "writer": "你是撰写员。把材料组织成结构清晰的短文。",
}


def chat(messages, temperature=0.3):
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": temperature, "num_predict": 500},
    }, timeout=180)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def extract_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ============================================================
# Manager: 分解与合并
# ============================================================

def decompose(task):
    raw = chat([{"role": "user", "content": f"用户任务: {task}\n\n{MANAGER_PROMPT}"}],
               temperature=0.0)
    plan = extract_json(raw)
    return (plan or {}).get("subtasks") or [{"role": "researcher", "task": task}]


def merge(task, results):
    lines = "\n\n".join(f"[{r['role']} - {r['task']}]\n{r['output']}" for r in results)
    return chat([{"role": "user", "content":
                  f"原始任务: {task}\n\n各 Worker 的产出:\n{lines}\n\n"
                  "把以上材料合并成一份完整、无重复的最终产出。"}], temperature=0.2)


# ============================================================
# Worker: 并行执行 (IO 密集, 线程池即可真并行)
# ============================================================

def worker_execute(subtask):
    role = subtask.get("role", "researcher")
    prompt = ROLE_PROMPTS.get(role, ROLE_PROMPTS["researcher"])
    start = time.time()
    output = chat([{"role": "user", "content": f"{prompt}\n\n子任务: {subtask['task']}"}])
    return {"role": role, "task": subtask["task"], "output": output,
            "elapsed": round(time.time() - start, 1)}


def run_workers(subtasks):
    with ThreadPoolExecutor(max_workers=len(subtasks)) as pool:
        futures = [pool.submit(worker_execute, st) for st in subtasks]
        return [f.result() for f in futures]


# ============================================================
# 真实模式
# ============================================================

def run_real():
    task = ("调研 Python 异步编程（asyncio），并产出一份包含核心概念、"
            "适用场景与常见坑的入门摘要")
    print("=" * 60)
    print(f"Manager-Worker -- 真实模式 ({MODEL})")
    print(f"任务: {task}")
    print("=" * 60)

    print("\n==> [manager] 分解任务")
    subtasks = decompose(task)
    for st in subtasks:
        print(f"  [{st['role']}] {st['task']}")

    print(f"\n==> [workers] {len(subtasks)} 个 Worker 并行执行...")
    t0 = time.time()
    results = run_workers(subtasks)
    wall = round(time.time() - t0, 1)
    seq = round(sum(r["elapsed"] for r in results), 1)
    for r in results:
        print(f"  [{r['role']}] {r['elapsed']}s, 产出 {len(r['output'])} 字")
    print(f"  墙钟 {wall}s vs 串行合计 {seq}s (并行加速可见)")

    print("\n==> [manager] 合并产出")
    final = merge(task, results)
    print(f"\n{final[:600]}{'…' if len(final) > 600 else ''}")


# ============================================================
# Demo 模式: 预置分解与产出 (离线, 编排结构真实运行)
# ============================================================

CANNED_SUBTASKS = [
    {"role": "researcher", "task": "收集 ReAct 的核心概念"},
    {"role": "analyst", "task": "分析 ReAct 的优劣与适用场景"},
]
CANNED_OUTPUTS = [
    "ReAct = Reason + Act：Thought/Action/Observation 循环，配合工具使用。",
    "优势：用外部行动修正推理、降低幻觉；劣势：多轮 LLM 调用延迟高，解析易碎。"
    "适合需要实时信息的探索型任务。",
]


def fake_worker(subtask, output):
    start = time.time()
    time.sleep(0.3)   # 模拟 LLM 延迟, 展示并行
    return {"role": subtask["role"], "task": subtask["task"], "output": output,
            "elapsed": round(time.time() - start, 1)}


def run_demo():
    print("=" * 60)
    print("Manager-Worker -- Demo 模式（预置产出, 编排结构真实运行）")
    print("=" * 60)
    task = "介绍 ReAct 模式并分析其优劣"
    print(f"任务: {task}")

    print("\n==> [manager] 分解 (预置 JSON)")
    for st in CANNED_SUBTASKS:
        print(f"  [{st['role']}] {st['task']}")

    print("\n==> [workers] 并行执行 (ThreadPoolExecutor + 模拟延迟)")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(CANNED_SUBTASKS)) as pool:
        futures = [pool.submit(fake_worker, st, out)
                   for st, out in zip(CANNED_SUBTASKS, CANNED_OUTPUTS)]
        results = [f.result() for f in futures]
    wall = round(time.time() - t0, 1)
    seq = round(sum(r["elapsed"] for r in results), 1)
    for r in results:
        print(f"  [{r['role']}] {r['elapsed']}s  {r['output'][:36]}…")
    print(f"  墙钟 {wall}s vs 串行合计 {seq}s —— 并行加速 {seq / wall:.1f}x")

    print("\n==> [manager] 合并 (真实模式由 LLM 完成)")
    print("  最终产出 = 概念介绍 + 优劣分析，去重合并。")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        print("Usage: python manager_worker.py [--demo]\n"
              "  --demo   : 离线演示编排结构（无需 Ollama）\n"
              "  (无参数)  : 真实模式, Manager 分解 + Worker 并行 + 合并\n")
        run_real()
