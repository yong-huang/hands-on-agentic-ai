"""
面试项目 4 — ReAct 死循环检测与防护

覆盖面试题: 最大步数怎么设？如何判断 Agent 陷入死循环？

核心: 四层防护 (defense in depth), 任何一层触发即输出诊断并强制"失败总结"
  L1 步数上限        硬兜底: 漏网的循环最终都被它拦住
  L2 重复 Action     连续 N 次完全相同的 (action, input) → 撞墙式重试
  L3 Thought 相似度  Thought 几乎不变而输入微调 → 换汤不换药的复读
                     (签名完全相同的重复归 L2 管, L3 不抢)
  L4 预算熔断        累计 token / 耗时超预算 → 行为没重复但资源在空转

三种死循环场景逐一验证各层的"对应"拦截:
  S1 工具恒失败 → L2 (错误信息诱导重试, 输入不变)
  S2 模型复读   → L3 (忽略 Observation, 思考文本几乎不变)
  S3 目标矛盾   → L4 (在北京/上海间反复摇摆, 每步都不同但永不收敛)
外加消融实验: 关掉 L4 后, S3 由 L1 步数上限兜底拦截。

运行:
  MOCK=1 python loop_guard.py    # 离线: 脚本化病态策略, 结果确定
  python loop_guard.py           # 真实: S1 真模型首轮决策+卡带重放注入;
                                 #       S2/S3 注入脚本病态策略 (健康模型不会自己死循环)
"""

import difflib, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import chat as _llm_chat

MOCK = os.environ.get("MOCK") == "1"

SYSTEM = """你是 ReAct Agent。每轮只输出一个 JSON 决策:
{"thought": "推理", "action": "工具名或 finish", "input": {...}}
可用工具: query_flight(from,to,date) / get_weather(city) / calculator(expression)
能回答时 action 用 "finish"。"""


def est_tokens(text):
    """粗略 token 估算 (中文≈0.6 token/字符)。生产环境应换 tiktoken 精确计数。"""
    return int(len(str(text)) * 0.6) + 1


# ============================================================
# 工具 (query_flight 带故障注入开关, 供 S1 场景使用)
# ============================================================

FAULT = {"flight_broken": False}
FLIGHT_PRICE = {("北京", "广州"): 1280, ("上海", "广州"): 1180, ("北京", "上海"): 520}


def tool_query_flight(**kw):
    if FAULT["flight_broken"]:
        return "错误: 航班服务不可用(503), 请稍后重试"
    dep, arr = kw.get("from", "?"), kw.get("to", "?")
    price = FLIGHT_PRICE.get((dep, arr), 900)
    return f"{kw.get('date', '?')} {dep}->{arr}: 最低价 ¥{price} (直飞)"


def tool_get_weather(city):
    data = {"北京": "晴 28°C", "上海": "多云 25°C", "广州": "小雨 22°C"}
    for k, v in data.items():
        if k in str(city):
            return v
    return f"{city}: 晴 25°C"


def tool_calculator(expression):
    try:
        return str(eval(re.sub(r"[^0-9\+\-\*\/\.\(\) ]", "", str(expression))))
    except Exception as e:
        return f"计算错误: {e}"


TOOLS = {"query_flight": tool_query_flight,
         "get_weather": tool_get_weather,
         "calculator": tool_calculator}


# ============================================================
# 四层防护 LoopGuard
# ============================================================

class LoopGuard:
    """L1 步数上限 / L2 重复 Action / L3 Thought 相似度 / L4 预算熔断"""

    def __init__(self, max_steps=8, repeat_limit=3, sim_threshold=0.85,
                 token_budget=1200, time_budget=30.0):
        self.max_steps = max_steps
        self.repeat_limit = repeat_limit
        self.sim_threshold = sim_threshold
        self.token_budget = token_budget      # None 表示关闭 L4 (消融实验用)
        self.time_budget = time_budget
        self.spend = 0                        # 累计估算 token (含每轮重发的上下文)
        self.t0 = time.time()
        self.events = []                      # [(step, layer, reason)]
        self._recent = []                     # 最近 Action 签名
        self._prev_thought = None
        self._streak = 0                      # 当前决策与上一轮完全相同的连击数

    def add_spend(self, *texts):
        self.spend += sum(est_tokens(t) for t in texts)

    def check_budget(self):
        """L4: 行为不重复、逻辑可能还在推进, 但资源已超支 → 熔断。"""
        if self.token_budget and self.spend >= self.token_budget:
            return "L4", f"token 熔断: 累计≈{self.spend} est.tokens ≥ 预算 {self.token_budget}"
        elapsed = time.time() - self.t0
        if elapsed >= self.time_budget:
            return "L4", f"耗时熔断: {elapsed:.0f}s ≥ 预算 {self.time_budget:.0f}s"
        return None

    def check_repeat(self, decision):
        """L2: 连续 N 次完全相同的 (action, input) → 撞墙式重试。"""
        sig = json.dumps({"a": decision.get("action"), "i": decision.get("input")},
                         sort_keys=True, ensure_ascii=False)
        self._recent.append(sig)
        n = self.repeat_limit
        self._streak = self._streak + 1 if (len(self._recent) >= 2
                                            and self._recent[-2] == sig) else 1
        if len(self._recent) >= n and all(s == sig for s in self._recent[-n:]):
            return "L2", f"连续 {n} 次完全相同的 Action (撞墙式重试)"
        return None

    def check_thought(self, thought):
        """L3: 相邻 Thought 相似度过高 → 复读。完全相同的决策归 L2, 此处让位。"""
        if self._streak >= 2:
            return None
        t = re.sub(r"\s", "", str(thought))
        if self._prev_thought is not None:
            ratio = difflib.SequenceMatcher(None, self._prev_thought, t).ratio()
            if ratio >= self.sim_threshold:
                return "L3", f"相邻 Thought 相似度 {ratio:.2f} ≥ {self.sim_threshold} (复读)"
        self._prev_thought = t
        return None


# ============================================================
# ReAct 循环 (带防护挂钩)
# ============================================================

def extract_decision(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def finish_answer(decision):
    """提取 finish 答案。模型不一定守 answer 字段约定, 兼容 message/result。"""
    inp = decision.get("input") or {}
    if isinstance(inp, str):
        return inp
    return inp.get("answer") or inp.get("message") or inp.get("result") or ""


def force_summary(messages, policy, layer, reason):
    """拦截后强制收尾: 让模型基于已有 Observation 产出失败总结, 而非静默截断。"""
    messages.append({"role": "user", "content":
        f"⚠ 系统防护[{layer}]触发: {reason}\n"
        "不要再调用工具。请基于已有 Observation 输出失败总结, JSON 格式:\n"
        '{"thought": "...", "action": "finish", "input": {"answer": "失败总结: ..."}}'})
    d = extract_decision(policy(messages, "summary"))
    if d and d.get("action") == "finish" and finish_answer(d):
        return finish_answer(d)
    return f"失败总结(兜底): {reason}"


def react_loop(task, policy, guard):
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": task}]
    trace, step = [], 0
    while True:
        step += 1
        if step > guard.max_steps:
            violation = ("L1", f"步数上限 {guard.max_steps} 已到, 强制收尾")
        else:
            violation = guard.check_budget()
        if violation is None:
            raw = policy(messages, step)
            # 每次 LLM 调用都要重发全部上下文, 所以 token 消耗按全量 messages 计
            guard.add_spend(*[m["content"] for m in messages], raw)
            decision = extract_decision(raw)
            if decision is None:
                trace.append(f"  [step {step}] ⚠ JSON 解析失败, 回喂重试")
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": "输出不是合法 JSON, 请重新输出。"}]
                continue
            violation = (guard.check_repeat(decision)
                         or guard.check_thought(decision.get("thought", "")))
        if violation:
            layer, reason = violation
            guard.events.append((step, layer, reason))
            trace.append(f"  [step {step}] 🛑 [{layer}] {reason}")
            answer = force_summary(messages, policy, layer, reason)
            trace.append(f"  [step {step}] 强制失败总结 => {answer[:46]}…")
            return answer, trace, guard
        action = decision.get("action", "")
        if action == "finish":
            ans = finish_answer(decision)
            trace.append(f"  [step {step}] ✓ finish: {ans}")
            return ans, trace, guard
        tool_input = decision.get("input", {})
        fn = TOOLS.get(action)
        try:
            obs = fn(**tool_input) if fn else f"未知工具: {action}"
        except Exception as e:
            obs = f"工具异常: {e}"
        trace.append(f"  [step {step}] {action}({json.dumps(tool_input, ensure_ascii=False)})"
                     f" -> {obs}")
        messages += [{"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)},
                     {"role": "user", "content": f"Observation: {obs}"}]


# ============================================================
# 两种策略: 真实 LLM / 脚本化病态策略 (可复现的死循环)
# ============================================================

def real_policy(messages, step):
    return _llm_chat(messages, temperature=0.0, num_predict=300)


class ReplayStuck:
    """真模型 + 卡带故障注入: 第一轮用真实 LLM 对真故障工具的真实决策,
    之后每轮原样重放该决策, 模拟"卡死的 Agent"。
    健康模型不会自己死循环 (实测 qwen3.8 一次失败即自行放弃),
    所以测防护必须注入病态策略——这本身是考点。强制总结仍由真模型产出。"""

    def __init__(self):
        self.first = None

    def __call__(self, messages, step):
        if self.first is None:
            self.first = real_policy(messages, step)
            return self.first
        return self.first if step != "summary" else real_policy(messages, "summary")


class Scripted:
    """脚本化病态策略: 循环复播 decisions, 模拟降级/失控的模型; summary 供强制总结阶段。"""

    def __init__(self, decisions, summary):
        self.decisions, self.summary, self.i = decisions, summary, 0

    def __call__(self, messages, step):
        if step == "summary":
            return self.summary
        d = self.decisions[self.i % len(self.decisions)]
        self.i += 1
        return d


def D(thought, action, **inp):
    return json.dumps({"thought": thought, "action": action, "input": inp},
                      ensure_ascii=False)


# ============================================================
# 三种死循环场景
# ============================================================

FLIGHT_RETRY = D("查询9月10日北京到上海的航班", "query_flight",
                 **{"from": "北京", "to": "上海", "date": "2026-09-10"})

S1 = {"name": "S1 工具恒失败", "expect": "L2", "live": True, "broken": True,
      "task": "查询 2026-09-10 北京到上海的航班",
      "decisions": [FLIGHT_RETRY],
      "summary": D("航班服务持续 503, 无法完成查询", "finish",
                   answer="失败总结: 航班查询服务持续返回 503, 第 3 次发起完全相同的调用时被防护拦截。"
                          "建议: 稍后重试或改用备用查询渠道。")}

S2 = {"name": "S2 模型复读", "expect": "L3", "live": False,
      "task": "上海现在的天气怎么样？",
      "decisions": [D("我需要查询上海的天气情况", "get_weather", city="上海"),
                    D("我需要查询一下上海的天气情况", "get_weather", city="上海市")],
      "summary": D("检测到重复思考, 其实第一步已拿到天气", "finish",
                   answer="失败总结: 连续两轮 Thought 相似度 ≥0.85 (复读), 已熔断。"
                          "回看 Observation: 上海天气第一步已查到 = 多云 25°C。答案: 多云 25°C")}

S3 = {"name": "S3 目标矛盾", "expect": "L4", "live": False,
      "task": "帮我订 9月10日前后 北京或上海 出发到广州的最低价机票",
      "decisions": [
          D("先查北京出发的航班价格", "query_flight",
            **{"from": "北京", "to": "广州", "date": "2026-09-10"}),
          D("等等, 上海出发也许有特价, 改查上海", "query_flight",
            **{"from": "上海", "to": "广州", "date": "2026-09-10"}),
          D("对比后还是觉得北京直飞更稳, 换回北京", "query_flight",
            **{"from": "北京", "to": "广州", "date": "2026-09-11"}),
          D("可是听说上海票在打折, 再看一眼上海", "query_flight",
            **{"from": "上海", "to": "广州", "date": "2026-09-11"}),
          D("临近日期票价可能浮动, 查北京12日", "query_flight",
            **{"from": "北京", "to": "广州", "date": "2026-09-12"}),
          D("上海12日说不定也降了, 再查上海", "query_flight",
            **{"from": "上海", "to": "广州", "date": "2026-09-12"}),
      ],
      "summary": D("反复摇摆未收敛, 接受强制终止", "finish",
                   answer="失败总结: 在北京/上海出发方案间反复摇摆未收敛 (目标矛盾), 已被防护强制终止。"
                          "已查得: 北京->广州 ¥1280, 上海->广州 ¥1180。"
                          "建议: 明确出发城市或给定决策规则后一次定案。")}


def run_scenario(scn, disable_l4=False):
    if MOCK:
        policy, tag = Scripted(scn["decisions"], scn["summary"]), "脚本注入病态策略"
    elif scn.get("live"):
        policy, tag = ReplayStuck(), "真模型首轮决策+重放注入(模拟卡死)"
    else:
        policy, tag = Scripted(scn["decisions"], scn["summary"]), "脚本注入病态策略"
    kw = {} if not disable_l4 else {"token_budget": None}
    guard = LoopGuard(**kw)
    FAULT["flight_broken"] = bool(scn.get("broken"))
    label = scn["name"] + ("  [消融: 关L4]" if disable_l4 else "")
    expect = "L1" if disable_l4 else scn["expect"]

    print(f"\n==> {label}   (期望拦截层: {expect} | 策略: {tag})")
    answer, trace, guard = react_loop(scn["task"], policy, guard)
    for line in trace:
        print(line)

    fired = guard.events[-1][1] if guard.events else "-"
    step = guard.events[-1][0] if guard.events else "-"
    ok = "✓" if fired == expect else "✗"
    print(f"  => 拦截层 {fired} (期望 {expect}) {ok}  步数={step}  累计≈{guard.spend} est.tokens")
    return {"name": label, "fired": fired, "expect": expect,
            "step": step, "spend": guard.spend, "pass": fired == expect}


def main():
    print("=" * 72)
    print(f"ReAct 死循环检测与防护 -- {'MOCK (离线)' if MOCK else '真实模式'}")
    print(f"防护参数: max_steps=8 | repeat_limit=3 | thought_sim≥0.85 | "
          f"token_budget=1200 | time_budget=30s")
    print("=" * 72)

    results = [run_scenario(S1),
               run_scenario(S2),
               run_scenario(S3),
               run_scenario(S3, disable_l4=True)]

    print("\n" + "=" * 72)
    print(f"{'场景':<24}{'期望':>6}{'实际':>6}{'步数':>6}{'token':>8}{'结果':>8}")
    print("-" * 72)
    for r in results:
        print(f"{r['name']:<24}{r['expect']:>6}{r['fired']:>6}{r['step']:>6}"
              f"{r['spend']:>8}{'✓ 拦截' if r['pass'] else '✗ 失败':>8}")
    print("=" * 72)

    print("""
要点: 最大步数怎么设 / 怎么判断死循环
  1) 步数上限不是唯一防护, 而是最后兜底——按任务复杂度分级 (简单 3-5 / 研究 10-20),
     触发后必须"强制总结"有意义地收尾, 而不是静默截断。
  2) 判断死循环要看三层信号: 行为层 (重复 Action)、语义层 (Thought 相似度)、
     资源层 (token/耗时趋势)——单一信号都会误报/漏报, 分层互为补充。
  3) 每层拦截都要产出"失败总结": S2 里答案其实早就拿到 (复读掩盖了已有 Observation),
     强制总结能把半成品结果交接出来, 这是护栏的核心价值。
""")


if __name__ == "__main__":
    main()
