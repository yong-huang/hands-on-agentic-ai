"""
Code Execution / Code Mode — 让 Agent 写代码调工具，而非逐个 JSON schema 调用

Anthropic 2025.11 热文 (98.7% token 节省) 的核心思路:
不再把 N 个 MCP 工具暴露为 N 个 JSON schema（模型需逐个调用、中间结果
全部经过上下文），而是把工具函数预载到沙箱命名空间，让 Agent **写一段
Python 代码直接调用**——中间结果留在沙箱里不过上下文，代码即过滤。

本篇对照实验:
  v1 (baseline)   标准工具调用: 每个工具 JSON schema、中间结果过上下文
  v2 (code mode)  沙箱代码执行: Agent 写代码、一次性调多个工具、只回传最终结果

实测指标: LLM 调用次数 / 上下文 token / 结果正确性
"""

import json
import os
import re
import sys
import time

import requests

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO = "--demo" in sys.argv


# ============================================================
# 模拟工具: 电商销售数据管线 (模拟真实 MCP 工具)
# ============================================================

SALES_DATA = [
    {"region": "华东", "product": "笔记本电脑", "qty": 45, "price": 5999},
    {"region": "华东", "product": "手机", "qty": 120, "price": 3999},
    {"region": "华北", "product": "笔记本电脑", "qty": 32, "price": 5999},
    {"region": "华北", "product": "手机", "qty": 98, "price": 4299},
    {"region": "华南", "product": "平板", "qty": 67, "price": 2999},
    {"region": "华南", "product": "笔记本电脑", "qty": 28, "price": 6499},
    {"region": "华东", "product": "平板", "qty": 55, "price": 3199},
    {"region": "华北", "product": "平板", "qty": 41, "price": 2899},
    {"region": "华南", "product": "手机", "qty": 110, "price": 4599},
    {"region": "华北", "product": "耳机", "qty": 200, "price": 299},
]


def query_sales(region=None, product=None):
    """查询销售记录，可按地区/产品过滤。"""
    rows = SALES_DATA
    if region:
        rows = [r for r in rows if r["region"] == region]
    if product:
        rows = [r for r in rows if r["product"] == product]
    return rows


def compute_revenue(qty, price):
    return qty * price


TOOLS = {
    "query_sales": query_sales,
    "compute_revenue": compute_revenue,
}


# ============================================================
# v1: 标准工具调用 (每个工具一次 LLM 往返)
# ============================================================

def run_v1(task):
    tools_desc = "\n".join([
        f"- query_sales(region, product): 查询销售记录（可选过滤）",
        f"- compute_revenue(qty, price): 计算营收",
    ])
    messages = [
        {"role": "system", "content": f"你是数据分析助手。可用工具:\n{tools_desc}\n\n每轮只能调用一个工具，"
                                       "以 JSON 输出: {\"tool\": \"名称\", \"args\": {...}}\n"
                                       "当你有足够信息回答时，输出: {\"answer\": \"...\"}"},
        {"role": "user", "content": task},
    ]
    llm_calls, total_chars = 0, 0
    for _ in range(8):
        raw = _chat(messages)
        llm_calls += 1
        total_chars += len(raw)
        m = re.search(r'\{.*\}', raw, re.S)
        if not m:
            break
        decision = json.loads(m.group(0))
        if "answer" in decision:
            return {"answer": decision["answer"], "llm_calls": llm_calls, "ctx_chars": total_chars}
        tool = TOOLS.get(decision.get("tool"))
        result = tool(**decision.get("args", {})) if tool else "未知工具"
        result_str = json.dumps(result, ensure_ascii=False)
        total_chars += len(result_str)
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"[工具结果]\n{result_str}"})
    return {"answer": "（未收敛）", "llm_calls": llm_calls, "ctx_chars": total_chars}


def _chat(messages):
    if DEMO:
        return mock_llm_v1(messages[-1]["content"])
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": 0.0, "num_predict": 400},
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


# ============================================================
# v2: Code Mode — Agent 写 Python 代码直接调工具
# ============================================================

CODE_MODE_PROMPT = """你是数据分析助手。以下是可用的工具函数签名:

```python
def query_sales(region=None, product=None): ...  # 返回 list[dict]
def compute_revenue(qty, price): ...  # 返回 float
```

写一段 Python 代码完成用户任务，代码可以调用上述函数。只输出代码（```python ... ```）。
代码最后必须把结果赋值给变量 `result`。"""

SANDBOX_PRELUDE = {"__builtins__": __builtins__, "query_sales": query_sales, "compute_revenue": compute_revenue}


def run_v2(task):
    llm_calls, total_chars = 0, 0

    # round 1: Agent 写代码
    raw = _chat([{"role": "system", "content": CODE_MODE_PROMPT},
                 {"role": "user", "content": task}])
    llm_calls += 1
    total_chars += len(raw)
    code = re.search(r"```(?:python)?\s*(.*?)```", raw, re.S)
    code_text = code.group(1) if code else raw

    # round 2: 沙箱执行 + 把结果回喂 LLM 生成最终回答
    sandbox = dict(SANDBOX_PRELUDE)
    try:
        exec(code_text, sandbox)
        result = sandbox.get("result")
    except Exception as ex:
        result = f"代码执行出错: {ex}"
    result_str = json.dumps(result, ensure_ascii=False, default=str) if not isinstance(result, str) else result
    total_chars += len(result_str)

    final = _chat([{"role": "user", "content":
                    f"任务: {task}\n代码执行结果:\n{result_str}\n\n请给出简洁的最终回答。"}])
    llm_calls += 1

    return {"answer": final, "llm_calls": llm_calls, "ctx_chars": total_chars}


# ============================================================
# Mock (离线)
# ============================================================

def mock_llm_v1(user_msg):
    if "查询" in user_msg or "工具结果" not in user_msg:
        return '{"tool": "query_sales", "args": {}}'
    return '{"answer": "三个地区均有销售记录，共计 10 条。"}'


# ============================================================
# 对照实验
# ============================================================

TASK = "查询所有销售记录，统计总营收和每种产品的总销量，并给出各地区的营收占比。"


def run(mode):
    global DEMO
    DEMO = (mode == "demo")
    print("=" * 64)
    tag = "Demo 模式（MockLLM, 离线）" if DEMO else f"真实模式（{MODEL}）"
    print(f"Code Execution vs 标准工具调用 -- {tag}")
    print(f"任务: {TASK}")
    print("=" * 60)

    global _chat
    if DEMO:
        def _chat(messages):
            content = messages[-1]["content"]
            if "代码执行结果" in content or "[工具结果]" in content:
                return "总营收 1,632,233 元。笔记本 105 台、手机 328 台、平板 163 台。华东 42%、华北 29%、华南 29%。"
            if "```python" in content or "Python 代码" in content:
                return ("```python\n"
                        "rows = query_sales()\n"
                        "total_rev = sum(compute_revenue(r['qty'], r['price']) for r in rows)\n"
                        "product_qty = {}\n"
                        "for r in rows:\n"
                        "    product_qty[r['product']] = product_qty.get(r['product'], 0) + r['qty']\n"
                        "region_rev = {}\n"
                        "for r in rows:\n"
                        "    region_rev[r['region']] = region_rev.get(r['region'], 0) + compute_revenue(r['qty'], r['price'])\n"
                        "result = {'total_revenue': total_rev, 'product_qty': product_qty, 'region_rev': region_rev}\n"
                        "```")
            return '{"tool": "query_sales", "args": {}}'
    else:
        def _chat(messages):
            resp = requests.post(BASE_URL, json={
                "model": MODEL, "messages": messages, "stream": False, "think": False,
                "options": {"temperature": 0.0, "num_predict": 600},
            }, timeout=120)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()

    print("\n==> [v1] 标准工具调用（逐个 JSON schema）")
    r1 = run_v1(TASK)
    print(f"  LLM 调用 {r1['llm_calls']} 次, 上下文累计 {r1['ctx_chars']} 字符")
    print(f"  回答: {r1['answer'][:80]}…")

    print("\n==> [v2] Code Mode（沙箱代码执行）")
    r2 = run_v2(TASK)
    print(f"  LLM 调用 {r2['llm_calls']} 次, 上下文累计 {r2['ctx_chars']} 字符")
    print(f"  回答: {r2['answer'][:80]}…")

    print(f"\n{'=' * 64}")
    print(f"{'指标':<16}{'v1 标准调用':>14}{'v2 Code Mode':>16}")
    print(f"{'LLM 调用次数':<16}{r1['llm_calls']:>14}{r2['llm_calls']:>16}")
    print(f"{'上下文字符':<16}{r1['ctx_chars']:>14}{r2['ctx_chars']:>16}")
    print("=" * 64)
    print("结论: Code Mode 把 N 次工具往返压缩为 1 次代码写入 + 1 次执行,")
    print("      中间结果留在沙箱不过上下文——工具越多、数据越大，差距越大。")


if __name__ == "__main__":
    run("demo" if DEMO else "real")
