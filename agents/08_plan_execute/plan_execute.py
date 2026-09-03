"""
Plan-and-Execute — 先规划，后执行

项目 06/07 的 ReAct 是"边想边做"：每一步走完才决定下一步。本篇换成另一种
主流架构 Plan-and-Execute（LangGraph 生态的热门模式）：先让 LLM 把任务
**一次性分解成 JSON 计划**，再按计划逐步执行工具，最后汇总所有结果作答。

两种架构的对比:
  ReAct (06/07)                Plan-and-Execute (本篇)
  ─────────────                ─────────────
  Thought/Action 交替          先输出完整计划(JSON)
  每步都要过一次 LLM           规划 1 次 + 汇总 1 次, 中间纯本地执行
  走一步看一步, 灵活           全局视图, 计划可审计、可并行
  适合探索型任务               适合结构明确的多步任务

结构化输出复用项目 03 的经验: JSON 提取两级回退 (代码围栏 -> 全文花括号)。
"""

import json
import re
import sys
import requests

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

# ============================================================
# 本地工具 (与项目 07 同款)
# ============================================================

def tool_calculator(expression):
    if not re.match(r"^[\d\s\+\-\*\/\.\(\)]+$", str(expression)):
        return f"错误: 表达式含非法字符 '{expression}'"
    return str(eval(expression.replace("×", "*")))


def tool_get_population(city):
    data = {"北京": "2189万人", "上海": "2487万人", "深圳": "1768万人",
            "成都": "2126万人", "广州": "1881万人"}
    for name, value in data.items():
        if name in str(city) or str(city) in name:
            return value
    return f"未收录城市: {city}"


TOOLS = {"calculator": tool_calculator, "get_population": tool_get_population}

PLANNER_PROMPT = """把用户任务分解为 2-4 步的执行计划。只能使用这些工具:
- calculator(expression): 数学计算, expression 是纯数字算式
- get_population(city): 查询中国城市人口

如果某一步需要用到前面步骤的结果，在入参里用 {{"N"}} 引用第 N 步的输出
（例如 {{"3"}} 表示第 3 步的结果），执行时会自动替换。

只输出 JSON（不要其他文字），格式:
{{"steps": [{{"tool": "工具名", "input": "入参", "why": "这一步做什么"}}]}}"""


# ============================================================
# LLM 调用与 JSON 提取 (两级回退, 复用项目 03 的经验)
# ============================================================

def call_llm(messages):
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": 0.0, "num_predict": 500},
    }, timeout=120)
    resp.raise_for_status()
    content = resp.json()["message"]["content"].strip()
    return content if content else "（模型返回为空）"


def extract_json(text):
    """两级回退: 代码围栏优先, 全文第一个 {...} 兜底。"""
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


def make_plan(question):
    """规划器: 任务 -> JSON 计划 (steps 列表)。"""
    raw = call_llm([{"role": "user", "content": f"用户任务: {question}\n\n{PLANNER_PROMPT}"}])
    plan = extract_json(raw)
    if not plan or "steps" not in plan:
        return None, raw
    return plan["steps"], raw


# ============================================================
# 执行器与汇总
# ============================================================

def substitute(arg, results, tool):
    """把入参里的 {{N}} 引用替换成第 N 步的输出。
    calculator 只接受纯数字: 引用替换时从步骤输出里提取数值部分。"""
    def fill(m):
        n = int(m.group(1))
        out = next((r["output"] for r in results if r["step"] == n), m.group(0))
        if tool == "calculator":
            num = re.search(r"-?\d+(?:\.\d+)?", str(out))
            return num.group(0) if num else str(out)
        return str(out)
    return re.sub(r"\{\{(\d+)\}\}", fill, str(arg))


def execute_plan(steps):
    """按计划逐步执行本地工具 (不经过 LLM), 返回步骤结果列表。"""
    results = []
    for i, step in enumerate(steps, 1):
        tool, arg = step.get("tool", ""), step.get("input", "")
        arg = substitute(arg, results, tool)
        fn = TOOLS.get(tool)
        output = fn(arg) if fn else f"未知工具: {tool} (可用: {list(TOOLS)})"
        results.append({"step": i, "tool": tool, "input": arg, "output": output})
        print(f"  步骤 {i}: {tool}({arg}) -> {output}")
    return results


def aggregate(question, results):
    """汇总器: 问题 + 全部步骤结果 -> 最终答案。"""
    lines = "\n".join(f"- {r['tool']}({r['input']}) = {r['output']}" for r in results)
    return call_llm([{"role": "user", "content":
                      f"任务: {question}\n\n计划执行结果:\n{lines}\n\n"
                      "基于以上结果给出最终答案（一句话）。"}])


def run(question):
    print(f"任务: {question}\n")

    print("==> [plan] 规划器生成 JSON 计划")
    steps, raw = make_plan(question)
    if steps is None:
        print(f"  计划解析失败, 模型原始输出:\n{raw[:300]}")
        return
    for s in steps:
        print(f"  - {s.get('tool')}({s.get('input')})  # {s.get('why', '')}")
    print()

    print("==> [execute] 按计划逐步执行 (纯本地, 不经过 LLM)")
    results = execute_plan(steps)

    print("\n==> [aggregate] 汇总结果生成最终答案")
    answer = aggregate(question, results)
    print(f"  {answer}")


# ============================================================
# Demo 模式: 预置计划 + 真实本地工具 (离线)
# ============================================================

CANNED_PLAN = {"steps": [
    {"tool": "get_population", "input": "上海", "why": "查上海人口"},
    {"tool": "get_population", "input": "北京", "why": "查北京人口"},
    {"tool": "calculator", "input": "2487+2189", "why": "人口求和"},
]}
CANNED_ANSWER = "上海（2487 万）与北京（2189 万）人口合计约 4676 万。"


def run_demo():
    print("=" * 60)
    print("Plan-and-Execute -- Demo 模式（预置计划, 离线）")
    print("=" * 60)
    question = "上海和北京的人口加起来是多少？"
    print(f"任务: {question}\n")

    print("==> [plan] 计划 (预置 JSON, 真实模式由 LLM 生成)")
    steps = CANNED_PLAN["steps"]
    print(json.dumps(CANNED_PLAN, ensure_ascii=False, indent=2))

    print("\n==> [execute] 逐步执行 (真实本地工具)")
    results = execute_plan(steps)

    print("\n==> [aggregate] 汇总 (预置模板, 真实模式由 LLM 生成)")
    print(f"  {CANNED_ANSWER}")
    print("\n要点: 规划 1 次就看清全局, 执行阶段零 LLM 调用——")
    print("      真实模式将验证 LLM 生成的 JSON 计划能否被稳定解析与执行。")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        run(" ".join(sys.argv[1:]))
    else:
        print("Usage: python plan_execute.py [--demo | '任务']\n"
              "  --demo      : 离线演示（预置计划 + 真实本地工具）\n"
              "  '任务文字'   : 真实模式, LLM 规划 + 执行 + 汇总\n"
              "  (无参数)     : 真实模式, 默认任务\n")
        run("上海和北京的人口加起来是多少？")
