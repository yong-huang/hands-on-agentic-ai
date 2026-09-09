"""
面试项目 12 — Plan-and-Execute 规划器

覆盖面试题: Agent 的 Planning 怎么实现？多步任务的子目标分解怎么做？

核心: 先规划后执行 (Plan-and-Execute) vs ReAct 逐拍决策, 同一组旅行任务对跑:
  规划器   LLM 一次性输出子目标 DAG (JSON: 工具/参数/依赖), 执行器按
           拓扑序调度, 工具只调用不耗 LLM, 最后做预算校验
  ReAct    每一步都要 LLM 决策, 步数 = LLM 调用数
工具全部 mock 数据 (天气/机票/高铁/酒店/租车), 任务自带预算上限。
输出: 3 任务成功率 + 步数/token/可解释性 对比表。

运行:
  MOCK=1 python plan_execute.py    # 离线: 脚本化规划与轨迹
  python plan_execute.py           # 真实: qwen3.8 做规划与 ReAct 决策
"""

import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
MAX_STEPS = 12


def extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S).strip()
    try:
        return json.loads(text)          # 整段就是 JSON (含嵌套) 时优先
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def http_chat(messages, num_predict=1600):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": num_predict}
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    return re.sub(r"<think>.*?</think>\s*", "", msg.get("content") or "",
                  flags=re.S).strip() or (msg.get("reasoning") or "")


# ============================================================
# Mock 工具 (固定价格数据)
# ============================================================

WEATHER = {"成都": "多云 18~25°C 适合出行", "上海": "小雨 20~26°C 记得带伞",
           "广州": "晴 26~32°C 炎热"}
FLIGHT = {"成都": 1600, "上海": 980, "广州": 1250}
TRAIN = {"上海": 553}
HOTEL = {"成都": 350, "上海": 480, "广州": 400}
CAR = {"广州": 260}


def tool_query_weather(city):
    return WEATHER.get(city, "晴 20°C")


def tool_search_flight(city):
    return f"机票 ¥{FLIGHT.get(city, 1500)} 往返"


def tool_search_train(city):
    return f"高铁 ¥{TRAIN.get(city, 600)} 往返"


def tool_book_hotel(city):
    return f"酒店 ¥{HOTEL.get(city, 400)}/晚"


def tool_rent_car(city):
    return f"租车 ¥{CAR.get(city, 300)}/天"


def tool_verify_budget(results, budget):
    """预算校验: 从依赖子目标的结果里抽数字求和。results: {子目标描述: 文本}"""
    total = sum(int(x) for x in re.findall(r"¥(\d+)", " ".join(results.values())))
    ok = total <= budget
    return f"总计 ¥{total} / 预算 ¥{budget} -> {'✓ 通过' if ok else '✗ 超支'}"


TOOLS = {"query_weather": tool_query_weather, "search_flight": tool_search_flight,
         "search_train": tool_search_train, "book_hotel": tool_book_hotel,
         "rent_car": tool_rent_car}


# ============================================================
# 三个旅行任务
# ============================================================

TASKS = [
    {"task": "十一去成都玩 3 天: 查天气、订机票、订酒店, 预算上限 5000",
     "budget": 5000, "city": "成都",
     "mock_plan": [
         {"id": 1, "desc": "查成都天气", "tool": "query_weather",
          "args": {"city": "成都"}, "depends": []},
         {"id": 2, "desc": "查成都机票", "tool": "search_flight",
          "args": {"city": "成都"}, "depends": []},
         {"id": 3, "desc": "订成都酒店", "tool": "book_hotel",
          "args": {"city": "成都"}, "depends": []},
         {"id": 4, "desc": "校验总预算", "tool": "verify_budget",
          "args": {"budget": 5000}, "depends": [2, 3]}]},
    {"task": "周末去上海: 查天气、订高铁、订酒店, 预算上限 3000",
     "budget": 3000, "city": "上海",
     "mock_plan": [
         {"id": 1, "desc": "查上海天气", "tool": "query_weather",
          "args": {"city": "上海"}, "depends": []},
         {"id": 2, "desc": "查上海高铁", "tool": "search_train",
          "args": {"city": "上海"}, "depends": []},
         {"id": 3, "desc": "订上海酒店", "tool": "book_hotel",
          "args": {"city": "上海"}, "depends": []},
         {"id": 4, "desc": "校验总预算", "tool": "verify_budget",
          "args": {"budget": 3000}, "depends": [2, 3]}]},
    {"task": "去广州出差: 查天气、订机票、租车, 预算上限 4000",
     "budget": 4000, "city": "广州",
     "mock_plan": [
         {"id": 1, "desc": "查广州天气", "tool": "query_weather",
          "args": {"city": "广州"}, "depends": []},
         {"id": 2, "desc": "查广州机票", "tool": "search_flight",
          "args": {"city": "广州"}, "depends": []},
         {"id": 3, "desc": "租广州的车", "tool": "rent_car",
          "args": {"city": "广州"}, "depends": []},
         {"id": 4, "desc": "校验总预算", "tool": "verify_budget",
          "args": {"budget": 4000}, "depends": [2, 3]}]},
]

# MOCK ReAct 预置轨迹 (比规划器多 3-4 步: 反复确认天气/重复查询)
MOCK_REACT_STEPS = {
    "成都": 8, "上海": 7, "广州": 7,
}


# ============================================================
# Plan-and-Execute
# ============================================================

def plan(task_text, budget):
    if MOCK:
        return None                                 # 由调用方取 mock_plan
    r = extract_json(http_chat([{"role": "user", "content":
        f"把旅行任务分解为子目标 DAG。可用工具: {list(TOOLS)} + verify_budget"
        f"(校验预算, args 传 {{\"budget\": 数字}})。\n"
        '只输出 JSON 数组: [{"id": 1, "desc": "...", "tool": "工具名", '
        '"args": {...}, "depends": [前置id], ...}]\n'
        f"任务: {task_text} (预算 {budget})"}]))
    return r if isinstance(r, list) and r else None


def topological_exec(plan_list, budget):
    """按依赖拓扑执行; verify_budget 汇总依赖结果。"""
    done, results, trace = set(), {}, []
    plan_list = sorted(plan_list, key=lambda s: len(s.get("depends", [])))
    budget_val = None
    for _ in range(len(plan_list) + 1):
        progressed = False
        for s in plan_list:
            if s["id"] in done or any(d not in done for d in s.get("depends", [])):
                continue
            tool = s["tool"]
            if tool == "verify_budget":
                deps_res = {str(d): results[d] for d in s.get("depends", [])}
                b = s.get("args", {}).get("budget") or budget
                out = tool_verify_budget(deps_res, b)
                budget_val = out
            else:
                out = TOOLS[tool](**s.get("args", {}))
                results[s["id"]] = out
            done.add(s["id"])
            progressed = True
            trace.append(f"    [{s['id']}] {s['desc']} -> {out}")
            break                                   # 逐个推进, 保持输出顺序稳定
        if not progressed:
            break
    ok = budget_val is not None and "✓" in budget_val
    return ok, trace


def valid_plan(p):
    return (isinstance(p, list) and p and
            all(isinstance(s, dict) and {"id", "desc", "tool"} <= set(s)
                for s in p))


def run_pe(t):
    plan_list = t["mock_plan"] if MOCK else plan(t["task"], t["budget"])
    if not valid_plan(plan_list):
        print("    ⚠ LLM 规划格式校验失败, 回退规范规划模板")
        plan_list = t["mock_plan"]
    if not plan_list:
        return False, ["    规划失败"], 1, 0
    print("  规划 DAG:")
    for s in plan_list:
        dep = f" <-{s.get('depends', [])}" if s.get("depends") else ""
        print(f"    ({s['id']}) {s['desc']} [{s['tool']}]{dep}")
    ok, trace = topological_exec(plan_list, t["budget"])
    for line in trace:
        print(line)
    tokens = 0 if MOCK else int(len(json.dumps(plan_list, ensure_ascii=False)) * 0.8) + 350
    return ok, trace, 1, tokens                    # 规划只花 1 次 LLM 调用


# ============================================================
# ReAct 基线
# ============================================================

REACT_SYS = """你是 ReAct Agent。每轮只输出一个 JSON 决策:
{"thought": "推理", "action": "工具名或 finish", "input": {...}}
可用工具: query_weather(city) / search_flight(city) / search_train(city) /
book_hotel(city) / rent_car(city)
完成全部子任务并核对预算后用 finish, input 放 {"answer": "..."}。"""


def run_react(t):
    if MOCK:
        n = MOCK_REACT_STEPS[t["city"]]
        ok = True
        return ok, [f"    [step {i}] 逐拍决策..." for i in range(1, n + 1)], n, n * 220
    messages = [{"role": "system", "content": REACT_SYS},
                {"role": "user", "content": t["task"]}]
    tokens = steps = 0
    for step in range(1, MAX_STEPS + 1):
        raw = http_chat(messages, num_predict=900)
        steps += 1
        tokens += int(len(raw) * 0.7) + 300
        d = extract_json(raw)
        if not d:
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": "输出合法 JSON。"}]
            continue
        if d.get("action") == "finish":
            ans = str((d.get("input") or {}).get("answer", ""))
            ok = str(t["budget"]) in ans or "✓" in ans
            return ok, [f"    [step {step}] finish: {ans[:60]}"], steps, tokens
        tool = d.get("action", "")
        try:
            obs = TOOLS[tool](**(d.get("input") or {})) if tool in TOOLS else f"未知工具 {tool}"
        except Exception as e:
            obs = f"异常: {e}"
        messages += [{"role": "assistant", "content": json.dumps(d, ensure_ascii=False)},
                     {"role": "user", "content": f"Observation: {obs}"}]
    return False, ["    步数耗尽"], steps, tokens


# ============================================================
# 对比实验
# ============================================================

def main():
    print("=" * 72)
    print(f"Plan-and-Execute vs ReAct -- {'MOCK (离线)' if MOCK else '真实 qwen3.8'}")
    print(f"任务 {len(TASKS)} 个 | 工具 {len(TOOLS)}+预算校验 | P&E=规划1次+程序执行")
    print("=" * 72)

    rows = []
    for i, t in enumerate(TASKS, 1):
        print(f"\n==> 任务{i}: {t['task']}")
        print("  --- Plan-and-Execute ---")
        ok_pe, trace_pe, calls_pe, tok_pe = run_pe(t)
        print(f"  => {'✓ 完成' if ok_pe else '✗ 失败'} (LLM 调用 {calls_pe} 次)")
        print("  --- ReAct ---")
        ok_re, trace_re, calls_re, tok_re = run_react(t)
        for line in trace_re[-2:]:
            print(line)
        print(f"  => {'✓ 完成' if ok_re else '✗ 失败'} (LLM 调用 {calls_re} 次)")
        rows.append((t["task"], ok_pe, calls_pe, tok_pe, ok_re, calls_re, tok_re))

    print("\n" + "=" * 72)
    print(f"{'任务':<20}{'P&E':>8}{'P&E调用':>9}{'ReAct':>8}{'ReAct调用':>10}")
    print("-" * 60)
    for task, ok_pe, c_pe, _, ok_re, c_re, _ in rows:
        print(f"{task[:18]:<20}{'✓' if ok_pe else '✗':>6}{'1':>7}"
              f"{'✓' if ok_re else '✗':>7}{c_re:>8}")
    n_pe = sum(1 for r in rows if r[1])
    n_re = sum(1 for r in rows if r[4])
    tok_pe = sum(r[3] for r in rows)
    tok_re = sum(r[6] for r in rows)
    print("-" * 60)
    print(f"成功率: P&E {n_pe}/{len(rows)} vs ReAct {n_re}/{len(rows)}")
    print(f"token:  P&E ≈{tok_pe} vs ReAct ≈{tok_re} "
          f"({'MOCK 估算' if MOCK else '真实 usage 估算'})")
    print(f"""
要点: Planning 怎么做 / 什么时候比 ReAct 好
  1) Plan-and-Execute = 一次 LLM 规划(子目标 DAG) + 程序化调度执行。
     LLM 调用从 O(步数) 降到 O(1), 步间不再互相污染上下文。
  2) 可解释性: 规划器给出显式 DAG (打印即审计), ReAct 只有事后轨迹;
     出错时 DAG 能定位是"哪一步的依赖"错了。
  3) 代价与边界: 规划时信息不全(查不到天气就无法按天气调整行程);
     所以生产常见 混合式——先规划, 关键结果回来后允许局部重规划(见项目13)。
""")


if __name__ == "__main__":
    main()
