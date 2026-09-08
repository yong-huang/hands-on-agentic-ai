"""
面试项目 5 — Function Calling 版 Agent 与 ReAct 对比

覆盖面试题: ReAct 和 Function Calling 的关系？可以结合使用吗？

核心: 把项目 3 的 5 个任务用原生 tools/tool_calls 重写, 与提示词版 ReAct 同题对跑:
  解析稳定性   ReAct 从文本抠 JSON (可能失败) vs FC 由 API 结构化返回 arguments
  token 成本   两次实验都取 API 真实 usage (MOCK 模式为字符估算)
  可观测性     ReAct 要解析 trace vs FC 的 message.tool_calls 天然结构化
  模型依赖度   ReAct 任何指令模型可跑 vs FC 需要模型支持 tools
最后演示"可叠加": FC 传输 Action, 模型同时在 content 写 Thought —
即 ReAct 语义跑在 FC 传输层上 (FC 是传输层, ReAct 是提示词模式)。

运行:
  MOCK=1 python fc_vs_react.py    # 离线: 预置响应
  python fc_vs_react.py           # 真实: qwen3.8 (Ollama 原生 tools)
"""

import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
MAX_STEPS = 8

SYSTEM_FC = ("你是 Agent。需要外部信息时调用提供的工具; 拿到足够信息后, "
             "用简洁的一句话直接回答用户, 不再调用工具。")
SYSTEM_REACT = """你是 ReAct Agent。每轮只输出一个 JSON 决策:
{"thought": "推理", "action": "工具名或 finish", "input": {...}}
可用工具: calculator(expression) / get_weather(city)
当能回答时 action 用 "finish"，input 放 {"answer": "答案"}。"""


def est_tokens(text):
    """MOCK 模式的字符级 token 估算 (真实模式直接用 API usage)。"""
    return int(len(str(text)) * 0.6) + 1


# ============================================================
# 工具 (与项目 3 完全一致, 保证双实现同题同工具)
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

TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "calculator", "description": "计算算术表达式, 返回数值结果",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "算术表达式, 如 28*3"}},
            "required": ["expression"]}}},
    {"type": "function", "function": {
        "name": "get_weather", "description": "查询指定城市的实时天气",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "城市名, 如 北京"}},
            "required": ["city"]}}},
]


# ============================================================
# LLM 访问: 返回完整 message + 真实 usage (llm.py 只回文本, 不够用)
# ============================================================

def api_chat(messages, tools=None):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0, "max_tokens": 400}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    msg.pop("reasoning", None)          # qwen3.8 思考字段, 不回传下一轮
    msg.pop("reasoning_content", None)
    return msg, data.get("usage", {})


def est_usage(messages, msg):
    return {"total_tokens": sum(est_tokens(m.get("content", "")) for m in messages)
            + est_tokens(msg.get("content", "")) + 30}


# ============================================================
# 实现 A: 原生 Function Calling Agent (Action 走 API 结构化传输)
# ============================================================

def fc_agent(task, call):
    messages = [{"role": "system", "content": SYSTEM_FC},
                {"role": "user", "content": task}]
    st = {"calls": 0, "tokens": 0, "parse_fail": 0, "trace": []}
    for step in range(1, MAX_STEPS + 1):
        msg, usage = call(messages)
        st["calls"] += 1
        st["tokens"] += usage.get("total_tokens") or est_usage(messages, msg)["total_tokens"]
        tcs = msg.get("tool_calls") or []
        if not tcs:
            ans = (msg.get("content") or "").strip()
            st["trace"].append(f"  [step {step}] ✓ 最终回答: {ans}")
            return ans, st
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": tcs})
        for tc in tcs:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                st["parse_fail"] += 1                 # FC 唯一可能的解析失败点
                args, obs = {}, f"错误: arguments 非法 JSON: {fn.get('arguments')!r}"
            else:
                f = TOOLS.get(fn.get("name", ""))
                try:
                    obs = f(**args) if f else f"未知工具: {fn.get('name')}"
                except Exception as e:
                    obs = f"工具异常: {e}"
            st["trace"].append(f"  [step {step}] {fn.get('name')}({args}) -> {obs}")
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": str(obs)})
    return "（达到最大步数）", st


# ============================================================
# 实现 B: 提示词版 ReAct Agent (同项目 3, 从文本抠 JSON)
# ============================================================

def extract_decision(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def react_agent(task, call):
    messages = [{"role": "system", "content": SYSTEM_REACT},
                {"role": "user", "content": task}]
    st = {"calls": 0, "tokens": 0, "parse_fail": 0, "trace": []}
    for step in range(1, MAX_STEPS + 1):
        msg, usage = call(messages)
        raw = msg.get("content") or ""
        st["calls"] += 1
        st["tokens"] += usage.get("total_tokens") or est_usage(messages, msg)["total_tokens"]
        decision = extract_decision(raw)
        if decision is None:
            st["parse_fail"] += 1
            st["trace"].append(f"  [step {step}] ⚠ JSON 解析失败, 回喂重试")
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": "输出不是合法 JSON, 请重新输出。"}]
            continue
        action = decision.get("action", "")
        if action == "finish":
            ans = str((decision.get("input") or {}).get("answer", ""))
            st["trace"].append(f"  [step {step}] ✓ finish: {ans}")
            return ans, st
        inp = decision.get("input") or {}
        f = TOOLS.get(action)
        try:
            obs = f(**inp) if f else f"未知工具: {action}"
        except Exception as e:
            obs = f"工具异常: {e}"
        st["trace"].append(f"  [step {step}] {action}({inp}) -> {obs}")
        messages += [{"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)},
                     {"role": "user", "content": f"Observation: {obs}"}]
    return "（达到最大步数）", st


# ============================================================
# 5 个同题任务 (与项目 3 一致) + 验收判定
# ============================================================

TASKS = [
    ("北京今天的气温乘以 3 是多少？", ["84"]),
    ("上海和北京的天气分别是什么？", ["25", "28"]),
    ("广州的温度除以 2 等于多少？", ["11"]),
    ("北京和广州的温差是多少？", ["6"]),
    ("上海温度加 10 再除以 5 等于多少？", ["7"]),
]


def D(thought, action, **inp):
    return json.dumps({"thought": thought, "action": action, "input": inp},
                      ensure_ascii=False)


def TC(name, args):
    """伪造一条带 tool_calls 的 assistant 消息 (mock)。arguments 是 JSON 字符串, 同 API。"""
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_0", "type": "function",
         "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}


# ReAct mock: JSON 决策串序列 / FC mock: message dict 序列
MOCK_SEQ = {
    "北京今天的气温乘以 3 是多少？": {
        "react": [D("查北京天气", "get_weather", city="北京"),
                  D("计算", "calculator", expression="28*3"),
                  D("能回答", "finish", answer="84")],
        "fc": [TC("get_weather", {"city": "北京"}),
               TC("calculator", {"expression": "28*3"}),
               {"role": "assistant", "content": "北京今天 28°C，乘以 3 等于 84。"}]},
    "上海和北京的天气分别是什么？": {
        "react": [D("查上海", "get_weather", city="上海"),
                  D("查北京", "get_weather", city="北京"),
                  D("能回答", "finish", answer="上海 多云 25°C；北京 晴 28°C")],
        "fc": [TC("get_weather", {"city": "上海"}),
               TC("get_weather", {"city": "北京"}),
               {"role": "assistant", "content": "上海 多云 25°C；北京 晴 28°C。"}]},
    "广州的温度除以 2 等于多少？": {
        "react": [D("查广州", "get_weather", city="广州"),
                  D("计算", "calculator", expression="22/2"),
                  D("能回答", "finish", answer="11")],
        "fc": [TC("get_weather", {"city": "广州"}),
               TC("calculator", {"expression": "22/2"}),
               {"role": "assistant", "content": "广州 22°C，除以 2 等于 11。"}]},
    "北京和广州的温差是多少？": {
        "react": [D("查北京", "get_weather", city="北京"),
                  D("查广州", "get_weather", city="广州"),
                  D("计算", "calculator", expression="28-22"),
                  D("能回答", "finish", answer="6")],
        "fc": [TC("get_weather", {"city": "北京"}),
               TC("get_weather", {"city": "广州"}),
               TC("calculator", {"expression": "28-22"}),
               {"role": "assistant", "content": "北京 28°C、广州 22°C，温差 6°C。"}]},
    "上海温度加 10 再除以 5 等于多少？": {
        "react": [D("查上海", "get_weather", city="上海"),
                  D("计算", "calculator", expression="(25+10)/5"),
                  D("能回答", "finish", answer="7")],
        "fc": [TC("get_weather", {"city": "上海"}),
               TC("calculator", {"expression": "(25+10)/5"}),
               {"role": "assistant", "content": "上海 25°C，加 10 再除以 5 等于 7。"}]},
}


def make_call(impl, task):
    """按实现与任务构造 LLM 调用函数 (mock 弹预置序列 / 真实走 API)。"""
    if MOCK:
        seq = list(MOCK_SEQ[task][impl])
        def call(messages):
            msg = seq.pop(0) if seq else {"role": "assistant", "content": "（预置序列耗尽）"}
            if isinstance(msg, str):          # ReAct mock 是 JSON 决策串
                msg = {"role": "assistant", "content": msg}
            return msg, est_usage(messages, msg)
        return call
    if impl == "fc":
        return lambda messages: api_chat(messages, TOOLS_SCHEMA)
    return lambda messages: api_chat(messages)


def run_impl(impl):
    agent = fc_agent if impl == "fc" else react_agent
    rows, total = [], {"calls": 0, "tokens": 0, "parse_fail": 0, "ok": 0}
    print(f"\n==> {'FC(原生 tool_calls)' if impl == 'fc' else 'ReAct(提示词 JSON)'} 逐任务 trace")
    for task, need in TASKS:
        print(f"\n任务: {task}")
        ans, st = agent(task, make_call(impl, task))
        for line in st["trace"]:
            print(line)
        ok = all(k in ans for k in need)
        total["calls"] += st["calls"]
        total["tokens"] += st["tokens"]
        total["parse_fail"] += st["parse_fail"]
        total["ok"] += ok
        rows.append((task, ok, ans, st))
    return rows, total


def main():
    print("=" * 72)
    print(f"Function Calling vs ReAct 同题对跑 -- {'MOCK (离线, token 为估算)' if MOCK else '真实 qwen3.8 (token 为 API usage)'}")
    print("=" * 72)

    react_rows, react_total = run_impl("react")
    fc_rows, fc_total = run_impl("fc")

    print("\n" + "=" * 72)
    print("逐任务对比 (步数 = LLM 调用次数)")
    print(f"{'任务':<22} | {'ReAct':>22} | {'FC':>22}")
    print("-" * 72)
    for (task, ok_r, ans_r, st_r), (_, ok_f, ans_f, st_f) in zip(react_rows, fc_rows):
        col_r = f"{'✓' if ok_r else '✗'} {st_r['calls']} 步 {st_r['tokens']} tok"
        col_f = f"{'✓' if ok_f else '✗'} {st_f['calls']} 步 {st_f['tokens']} tok"
        print(f"{task[:20]:<22} | {col_r:>22} | {col_f:>22}")
    print("-" * 72)
    print(f"合计: ReAct 正确 {react_total['ok']}/5, {react_total['calls']} 次调用, "
          f"{react_total['tokens']} tokens, 解析失败 {react_total['parse_fail']} 次")
    print(f"      FC    正确 {fc_total['ok']}/5, {fc_total['calls']} 次调用, "
          f"{fc_total['tokens']} tokens, 解析失败 {fc_total['parse_fail']} 次")

    pf_r, pf_f = react_total["parse_fail"], fc_total["parse_fail"]
    print("\n维度对比:")
    print(f"{'维度':<10}| {'ReAct (提示词模式)':<30}| FC (原生能力)")
    print("-" * 72)
    print(f"{'解析稳定性':<10}| {'从文本抠 JSON':<30}| arguments 结构化返回")
    print(f"{'实测解析失败':<10}| {pf_r} 次{'':<28}| {pf_f} 次")
    print(f"{'token 成本':<10}| {react_total['tokens']} tok (决策 JSON 全文重发)"[:46]
          + f"| {fc_total['tokens']} tok (含 schema 常驻开销)")
    print(f"{'可观测性':<10}| {'解析文本 trace':<30}| message.tool_calls 天然结构化")
    print(f"{'模型依赖度':<10}| {'任何指令模型可跑':<30}| 要求模型支持 tools")

    # === 叠加演示: ReAct 语义跑在 FC 传输层上 ===
    print("\n==> 叠加演示: FC 传输 + ReAct 提示词 (Thought 与 Action 并存于一条消息)")
    sys2 = SYSTEM_FC + "\n每次调用工具前, 先在 content 用一句话写出你的思考(Thought), 再发起工具调用。"
    messages = [{"role": "system", "content": sys2},
                {"role": "user", "content": "广州的温度除以 2 等于多少？"}]
    if MOCK:
        msg = {"role": "assistant", "content": "Thought: 温度未知, 先查广州天气。",
               "tool_calls": TC("get_weather", {"city": "广州"})["tool_calls"]}
    else:
        msg, _ = api_chat(messages, TOOLS_SCHEMA)
    print(f"  content(Thought)  = {msg.get('content', '')!r}")
    print(f"  tool_calls(Action) = "
          f"{[(t['function']['name'], t['function']['arguments']) for t in msg.get('tool_calls', [])]}")
    print("  => 同一条消息里既有推理又有动作: FC 是传输层, ReAct 是提示词模式, 二者可叠加。")

    print("\n要点: ReAct 和 Function Calling 的关系")
    print("  FC 解决『Action 怎么传』(结构化、可靠、模型必须支持);")
    print("  ReAct 解决『Agent 怎么想』(Thought→Action→Observation 的提示词循环);")
    print("  生产系统通常两者叠加: ReAct 语义 + FC 传输 + max_steps 兜底。")


if __name__ == "__main__":
    main()
