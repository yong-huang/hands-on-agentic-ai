"""
可观测性与评估框架 — Trace + 评估集 + 优化迭代对比 (系列收官)

"改了提示词到底变好还是变坏?" 没有评估框架, 这个问题只能靠感觉。本篇给
Agent 装上两样东西:

1. 可观测性: 轻量 Tracer (trace/span 模型)——每次 Agent 运行记录
   llm_call / tool_call 等 span 的耗时与属性, 导出 JSON 供回放分析
   (生产对应 OpenTelemetry SDK, 模型一致)
2. 评估框架: 6 条带预期关键词的测试用例, 对 Agent 的两个版本
   (v1 无工具说明 / v2 有 calculator 工具) 各跑一遍, 对比
   通过率 / token / 延迟——用数据决定哪个版本上线

Demo 模式: 用 MockLLM 离线跑通 Tracer 与评估管线。
"""

import json
import os
import re
import sys
import time
import uuid

import requests

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRACE_DIR = os.path.join(SCRIPT_DIR, "traces")
DEMO = "--demo" in sys.argv


# ============================================================
# 可观测性: 轻量 Tracer (生产对应 OpenTelemetry)
# ============================================================

class Tracer:
    """trace -> spans 的最小实现: 记录 span 名称/耗时/属性, 导出 JSON。"""

    def __init__(self, name):
        self.trace = {"trace_id": uuid.uuid4().hex[:12], "name": name,
                      "start": time.time(), "spans": []}
        self._stack = []

    def start_span(self, name, **attrs):
        span = {"name": name, "start": time.time(), "attrs": attrs}
        self._stack.append(span)
        return span

    def end_span(self, span, **results):
        span["end"] = time.time()
        span["elapsed"] = round(span["end"] - span["start"], 2)
        span["results"] = {k: str(v)[:80] for k, v in results.items()}
        self.trace["spans"].append(span)
        self._stack.pop()

    def export(self):
        self.trace["total"] = round(time.time() - self.trace["start"], 2)
        os.makedirs(TRACE_DIR, exist_ok=True)
        path = os.path.join(TRACE_DIR, f"trace_{self.trace['trace_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.trace, f, ensure_ascii=False, indent=2)
        return path

    def print_tree(self):
        print(f"  trace {self.trace['trace_id']} (total {self.trace['total']}s)")
        for s in self.trace["spans"]:
            print(f"    └ {s['name']:<12} {s['elapsed']:>5}s  "
                  f"{json.dumps(s.get('results', {}), ensure_ascii=False)[:60]}")


# ============================================================
# Agent: v1 (无工具) / v2 (calculator 工具)
# ============================================================

PROMPTS = {
    "v1": "你是精确问答助手。直接回答用户的计算与事实问题。",
    "v2": ("你是精确问答助手。涉及任何数学计算时，必须先输出一行 JSON "
           '{"tool": "calculator", "expression": "算式"}，系统会返回计算结果，'
           "然后基于结果作答。不要心算。"),
}


def llm(messages):
    if DEMO:
        return mock_llm(messages)
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": 0.0, "num_predict": 300},
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def calculator(expression):
    expr = re.sub(r"[^0-9\+\-\*\/\.\(\) ]", "", str(expression))
    return str(eval(expr)) if expr.strip() else "空表达式"


def agent_answer(version, question, tracer):
    """被测 Agent: 组装 prompt -> (可选)工具调用 -> 最终回答, 全程打 span。"""
    span = tracer.start_span("llm_call", version=version, question=question)
    raw = llm([{"role": "system", "content": PROMPTS[version]},
               {"role": "user", "content": question}])
    tracer.end_span(span, raw=raw)

    m = re.search(r'\{\s*"tool"\s*:\s*"calculator"\s*,\s*"expression"\s*:\s*"([^"]+)"\s*\}', raw)
    if m:
        span = tracer.start_span("tool_call", tool="calculator", expression=m.group(1))
        result = calculator(m.group(1))
        tracer.end_span(span, result=result)
        span = tracer.start_span("llm_call", note="基于工具结果作答")
        answer = llm([{"role": "user", "content":
                       f"计算结果: {result}\n问题: {question}\n请给出最终答案。"}])
        tracer.end_span(span, answer=answer)
        return answer
    return raw


# ============================================================
# MockLLM (demo): v1 心算常错, v2 走工具——模拟优化效果
# ============================================================

class MockState:
    answers = []


def mock_llm(messages):
    sys_text = messages[0]["content"]
    user = messages[-1]["content"]
    if "计算结果" in user:                      # v2 第二跳: 基于工具结果作答
        num = re.search(r"\d+(?:\.\d+)?", user)
        return f"最终答案: {num.group(0) if num else '未知'}"
    nums = re.findall(r"\d+(?:\.\d+)?", user)
    if "calculator" in sys_text and len(nums) >= 2:
        return json.dumps({"tool": "calculator",
                           "expression": f"{nums[0]}*{nums[1]}"})
    if len(nums) >= 2:
        # v1: 心算——乘法故意算错 (演示可观测性抓出质量问题)
        return f"心算结果约 {int(nums[0]) + int(nums[1])} (v1 心算)"
    return f"答案: (v1 直接回答) {user[:20]}"


# ============================================================
# 评估集与运行器
# ============================================================

EVAL_SET = [
    {"q": "一个笔记本 45 元，买 12 本要多少钱？", "expect": "540"},
    {"q": "每小时跑 8 公里，跑 3 小时共多少公里？", "expect": "24"},
    {"q": "每箱 60 个苹果，7 箱共多少个？", "expect": "420"},
    {"q": "RAG 是什么?", "expect": "检索"},
    {"q": "什么是上下文窗口?", "expect": "上下文"},
    {"q": "什么是工具白名单?", "expect": "白名单"},
]


def run_eval(version):
    tracer = Tracer(f"eval_{version}")
    passed, total_tokens, t0 = 0, 0, time.time()
    results = []
    for case in EVAL_SET:
        span = tracer.start_span("agent_run", question=case["q"])
        answer = agent_answer(version, case["q"], tracer)
        ok = case["expect"] in answer
        passed += ok
        total_tokens += estimate_tokens(answer)
        results.append((case["q"], answer, ok))
        tracer.end_span(span, answer=answer, passed=ok)
    path = tracer.export()
    elapsed = round(time.time() - t0, 1)
    return {"version": version, "passed": passed, "total": len(EVAL_SET),
            "tokens": total_tokens, "elapsed": elapsed, "results": results,
            "trace_path": path, "tracer": tracer}


def estimate_tokens(text):
    cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
    return cjk + (len(text) - cjk) // 4


# ============================================================
# 主流程: v1 vs v2 对比
# ============================================================

def run(mode):
    print("=" * 64)
    tag = "Demo 模式（MockLLM, 离线）" if DEMO else "真实模式（qwen3.8）"
    print(f"可观测性与评估框架 -- {tag}")
    print("=" * 64)

    print("\n==> [v1] 基线版本 (无工具说明)")
    r1 = run_eval("v1")
    r1["tracer"].print_tree()
    print(f"  通过 {r1['passed']}/{r1['total']}  trace: {os.path.basename(r1['trace_path'])}\n")

    print("==> [v2] 优化版本 (calculator 工具 + 强制说明)")
    r2 = run_eval("v2")
    print(f"  通过 {r2['passed']}/{r2['total']}  trace: {os.path.basename(r2['trace_path'])}\n")

    print("=" * 64)
    print(f"{'版本':<8}{'通过率':>10}{'tokens':>8}{'耗时':>8}")
    for r in (r1, r2):
        print(f"{r['version']:<8}{r['passed']}/{r['total']:>7}{r['tokens']:>8}{r['elapsed']:>7}s")
    print("=" * 64)
    print("对比即结论: v2 通过率更高是工具+指令的功劳; tokens/耗时是它的代价。")
    print(f"每轮运行的完整 span 树已导出到 {TRACE_DIR}/ ，可回放分析慢在哪、错在哪。")
    print("生产对应物: OpenTelemetry SDK + 评估集 CI——结构与本篇完全一致。")


if __name__ == "__main__":
    run("demo" if DEMO else "real")
