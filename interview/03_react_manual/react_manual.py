"""
面试项目 3 — 手写 ReAct 循环（面试主线①，不用框架）

覆盖面试题: 手写 ReAct (Thought-Action-Observation)；Action 失败怎么办？
ReAct 怎么解决幻觉？

核心: 纯手写 Thought→Action(JSON)→Observation 循环
  工具: calculator + mock 天气
  容错: JSON 解析失败重试 / 工具异常转 Observation 喂回
  演示: 一条"失败→自愈"轨迹

运行:
  MOCK=1 python react_manual.py    # 离线
  python react_manual.py           # 真实: qwen3.8
"""

import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import chat as _llm_chat

MOCK = os.environ.get("MOCK") == "1"
MAX_STEPS = 6
SYSTEM = """你是 ReAct Agent。每轮输出一个 JSON 决策:
{"thought": "推理", "action": "工具名或 finish", "input": {...}}
可用工具: calculator(expression) / get_weather(city)
当能回答时 action 用 "finish"，input 放 {"answer": "答案"}。"""


# ============================================================
# 工具
# ============================================================

def tool_calculator(expression):
    try:
        return str(eval(re.sub(r"[^0-9\+\-\*\/\.\(\) ]", "", str(expression))))
    except Exception as e:
        return f"计算错误: {e}"


def tool_get_weather(city):
    data = {"北京": "晴 28°C", "上海": "多云 25°C", "广州": "小雨 22°C"}
    for k, v in data.items():
        if k in str(city):
            return v
    return f"{city}: 晴 25°C"


TOOLS = {"calculator": tool_calculator, "get_weather": tool_get_weather}


def llm(messages):
    if MOCK:
        return MOCK_RESPONSES.get(len([m for m in messages if m["role"] == "user"]), "未知")
    return _llm_chat(messages, temperature=0.0, num_predict=300)


# ============================================================
# ReAct 循环
# ============================================================

def extract_decision(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def react_loop(question):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": question}]
    trace = []
    for step in range(1, MAX_STEPS + 1):
        raw = llm(messages)
        decision = extract_decision(raw)
        if decision is None:
            # 解析失败 → 错误回喂重试
            trace.append(f"  [step {step}] ⚠ JSON 解析失败, 回喂重试")
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                             "content": "你的输出不是合法 JSON。请重新输出 JSON 决策。"})
            continue
        action = decision.get("action", "")
        if action == "finish":
            ans = decision.get("input", {}).get("answer", "")
            trace.append(f"  [step {step}] ✓ finish: {ans}")
            return ans, trace
        tool_name = decision.get("action", "")
        tool_input = decision.get("input", {})
        tool_fn = TOOLS.get(tool_name)
        try:
            observation = tool_fn(**tool_input) if tool_fn else f"未知工具: {tool_name}"
        except Exception as e:
            observation = f"工具异常: {e}"
        trace.append(f"  [step {step}] {tool_name}({tool_input}) -> {observation}")
        messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
        messages.append({"role": "user", "content": f"Observation: {observation}"})
    return "（达到最大步数）", trace


# ============================================================
# 测试任务 (5 个多步任务 + 1 个失败自愈演示)
# ============================================================

TASKS = [
    "北京今天的气温乘以 3 是多少？",
    "上海和北京的天气分别是什么？",
    "广州的温度除以 2 等于多少？",
    "北京和广州的温差是多少？",
    "上海温度加 10 再除以 5 等于多少？",
]


# Mock 预置回复 (离线演示)
MOCK_RESPONSES = {}

def _mock_key(n):
    return n

def setup_mock():
    """预置一条'失败→自愈'轨迹的 mock 回复序列。"""
    seq = [
        '{"thought": "查北京天气", "action": "get_weather", "input": {"city": "北京"}}',
        '{"thought": "查上海天气", "action": "get_weather", "input": {"city": "上海"}}',
        '{"thought": "计算", "action": "calculator", "input": {"expression": "28*3"}}',
        '{"thought": "能回答了", "action": "finish", "input": {"answer": "84"}}',
    ]
    MOCK_RESPONSES.clear()
    for i, s in enumerate(seq):
        MOCK_RESPONSES[i + 1] = s


def main():
    setup_mock() if MOCK else None
    print("=" * 64)
    print(f"手写 ReAct 循环 -- {'MOCK (离线)' if MOCK else '真实模式'}")
    print(f"工具: {list(TOOLS)}   max_steps={MAX_STEPS}")
    print("=" * 64)

    print("\n==> 失败→自愈演示 (计算器故意传非法表达式)")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "算一下 abc*3"}]
    for step in range(1, 4):
        raw = llm(messages)
        d = extract_decision(raw)
        if not d:
            print(f"  [step {step}] ⚠ 解析失败")
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "请重新输出合法 JSON。"})
            continue
        action = d.get("action", "")
        if action == "finish":
            print(f"  [step {step}] ✓ {d.get('input',{}).get('answer','')}")
            break
        inp = d.get("input", {})
        fn = TOOLS.get(action)
        try:
            obs = fn(**inp) if fn else f"未知工具: {action}"
        except Exception as e:
            obs = f"异常: {e}"
        print(f"  [step {step}] {action}({inp}) -> {obs}")
        messages.append({"role": "assistant", "content": json.dumps(d, ensure_ascii=False)})
        messages.append({"role": "user", "content": f"Observation: {obs}"})
    print()

    for task in TASKS:
        print(f"\n任务: {task}")
        if MOCK:
            setup_mock()
        answer, trace = react_loop(task)
        for line in trace:
            print(line)
        print(f"  => {answer}\n")

    print("要点: Action 失败(工具异常/解析失败)不会崩溃——错误作为 Observation")
    print("      回喂给模型，Agent 自行调整策略。这就是 ReAct 解决幻觉的机制。")


if __name__ == "__main__":
    main()
