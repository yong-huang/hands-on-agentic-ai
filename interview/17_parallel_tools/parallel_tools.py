"""
面试项目 17 — 并行工具调用（依赖分析 DAG）

覆盖面试题: 多工具并行调用怎么实现？工具间依赖怎么处理？

核心: 模型一轮吐出 4 个工具调用, 其中 calc_cost 的参数用 $1/$2 占位符
引用前两个调用的结果。三种调度器对跑同一批调用:
  串行          逐个执行, 结果可用后填给后继          (基线)
  分析后并行    检测 $引用建依赖 DAG, 无依赖层 asyncio.gather
  盲并行        不分析依赖直接全量并发 → 占位符无法解析, 依赖错序失败
工具用 asyncio.sleep(0.3) 模拟耗时, 计时全部可复现 (与 LLM 无关,
真机模式仅额外让模型生成这批调用计划)。

运行:
  MOCK=1 python parallel_tools.py    # 离线: 预置调用批次
  python parallel_tools.py           # 真实: qwen3.8 生成调用批次, 计时同
"""

import asyncio, json, os, re, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
TOOL_LATENCY = 0.3          # 每个工具的模拟耗时 (秒)


def http_chat(messages, num_predict=1500):
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


def extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    for pat in (r"\[[^\[\]]*\]",):
        for m in reversed(re.findall(pat, text, re.S)):
            try:
                return json.loads(m)
            except json.JSONDecodeError:
                continue
    return None


# ============================================================
# 异步工具 (0.3s 模拟耗时)
# ============================================================

PRICES = {"成都": 1600, "上海": 980}
DISTANCES = {("北京", "成都"): 1800}


async def tool_get_price(city: str):
    await asyncio.sleep(TOOL_LATENCY)
    return PRICES.get(city, 1200)


async def tool_get_distance(a: str, b: str):
    await asyncio.sleep(TOOL_LATENCY)
    return DISTANCES.get((a, b), 1000)


async def tool_calc_cost(price, distance):
    await asyncio.sleep(TOOL_LATENCY)
    if isinstance(price, str) and price.startswith("$"):
        return f"ERROR: 参数未解析占位符 {price} (依赖未就绪)"
    if isinstance(distance, str) and distance.startswith("$"):
        return f"ERROR: 参数未解析占位符 {distance} (依赖未就绪)"
    return {"total": int(price) * 0.02 * int(distance) + int(price)}


async def tool_query_hotel(city: str):
    await asyncio.sleep(TOOL_LATENCY)
    return f"{city} 酒店 ¥350/晚"


TOOLS = {"get_price": tool_get_price, "get_distance": tool_get_distance,
         "calc_cost": tool_calc_cost, "query_hotel": tool_query_hotel}


# ============================================================
# 调用批次: calc_cost 用 $1/$2 引用前两个调用的结果
# ============================================================

CALL_BATCH = [
    {"id": 1, "name": "get_price", "args": {"city": "成都"}},
    {"id": 2, "name": "get_distance", "args": {"a": "北京", "b": "成都"}},
    {"id": 3, "name": "calc_cost",
     "args": {"price": "$1", "distance": "$2"}},        # 依赖 1, 2
    {"id": 4, "name": "query_hotel", "args": {"city": "成都"}},
]


def get_call_batch():
    """真机模式: 让 qwen 一轮生成调用批次; 产出不稳则回退预置批次。"""
    if MOCK:
        return CALL_BATCH
    prompt = ("任务: 计算 2kg 货物从北京快递到成都的总成本, 并查询成都酒店。\n"
              "可用工具: get_price(city) / get_distance(a,b) / "
              "calc_cost(price, distance 两个参数可用 \"$N 引用第 N 个调用的结果) / "
              "query_hotel(city)\n"
              "输出完成任务的全部工具调用 (4 个), 只输出 JSON 数组: "
              '[{"id": 1, "name": "...", "args": {...}}, ...]')
    r = extract_json(http_chat([{"role": "user", "content": prompt}]))
    if isinstance(r, list) and len(r) >= 3:
        return r
    return CALL_BATCH


def find_refs(args):
    """参数里的 $N 引用 → 依赖的调用 id 集合。"""
    refs = set()
    for v in (args or {}).values():
        if isinstance(v, str):
            refs |= {int(n) for n in re.findall(r"\$(\d+)", v)}
        elif isinstance(v, dict):
            refs |= find_refs(v)
    return refs


def fill_refs(args, results):
    """把 $N 替换为第 N 个调用的结果 (未就绪则原样保留)。"""
    out = {}
    for k, v in (args or {}).items():
        if isinstance(v, str) and re.fullmatch(r"\$(\d+)", v):
            r = results.get(int(v[1:]), v)
            out[k] = r
        else:
            out[k] = v
    return out


# ============================================================
# 三种调度器
# ============================================================

async def run_serial(calls):
    results, t0 = {}, time.perf_counter()
    for c in calls:
        c["args"] = fill_refs(c["args"], results)      # 前序结果已就绪, 回填后执行
        results[c["id"]] = await TOOLS[c["name"]](**c["args"])
    return time.perf_counter() - t0, results


async def run_parallel(calls):
    """依赖分析: 每一轮把"依赖已就绪"的调用 gather 并发, 直至完成。"""
    results, t0 = {}, time.perf_counter()
    pending = list(calls)
    while pending:
        ready = [c for c in pending if find_refs(c["args"]) <= set(results)]
        if not ready:                        # 有环或引用缺失, 防御性直接执行
            ready = pending[:1]
        pending = [c for c in pending if c not in ready]
        for c in ready:
            c = dict(c, args=fill_refs(c["args"], results))
        outs = await asyncio.gather(*(TOOLS[c["name"]](**fill_refs(c["args"], results))
                                      for c in ready))
        for c, o in zip(ready, outs):
            results[c["id"]] = o
    return time.perf_counter() - t0, results


async def run_blind_parallel(calls):
    """盲并行: 不分析依赖, 一把全发。"""
    t0 = time.perf_counter()
    outs = await asyncio.gather(*(TOOLS[c["name"]](**c["args"]) for c in calls))
    results = {c["id"]: o for c, o in zip(calls, outs)}
    return time.perf_counter() - t0, results


def fmt_results(results):
    lines = []
    for i in sorted(results):
        r = results[i]
        ok = not (isinstance(r, str) and r.startswith("ERROR"))
        mark = '✓' if ok else '✗'
        lines.append(f"      #{i} {mark} {str(r)[:52]}")
    return "\n".join(lines)


async def main_async():
    calls = get_call_batch()
    print("=" * 72)
    print(f"并行工具调用 (依赖分析 DAG) -- {'MOCK (预置批次)' if MOCK else "真实 qwen3.8 生成批次"}")
    print(f"调用 {len(calls)} 个 | calc_cost 依赖 $1/$2 | 每工具 {TOOL_LATENCY}s")
    print("=" * 72)

    print("\n==> 调用批次")
    for c in calls:
        print(f"  #{c['id']} {c['name']}({json.dumps(c['args'], ensure_ascii=False)})")

    t_s, r_s = await run_serial([dict(c) for c in calls])
    t_p, r_p = await run_parallel([dict(c) for c in calls])
    t_b, r_b = await run_blind_parallel([dict(c) for c in calls])

    err_p = any(isinstance(v, str) and v.startswith("ERROR") for v in r_p.values())
    err_b = any(isinstance(v, str) and v.startswith("ERROR") for v in r_b.values())
    print(f"\n==> 串行       {t_s:.2f}s  全部成功")
    print(f"==> 分析后并行 {t_p:.2f}s  依赖错序失败={err_p}  (加速 {t_s / t_p:.2f}x)")
    print(f"==> 盲并行     {t_b:.2f}s  依赖错序失败={err_b}  ← 预期 True")
    print("\n盲并行失败详情 (calc_cost 读到未解析占位符):")
    print(fmt_results(r_b))

    ok_half = t_p <= t_s * 0.6 + 0.01
    print("\n" + "=" * 72)
    print(f"验收: 并行耗时 ≈ 串行一半 (≤60%): {'✓' if ok_half else "✗"} "
          f"({t_p:.2f}s / {t_s:.2f}s = {t_p / t_s * 100:.0f}%)")
    print(f"验收: 盲并行因依赖错序失败可复现: {'✓' if err_b else "✗"}")
    print("""
要点: 并行调用与依赖处理
  1) 依赖检测是关键: 扫描参数里的 $N 引用建 DAG, 无依赖的进同一波
     asyncio.gather; 每工具 0.3s 时, 4 调用从 1.2s 降到 0.6s。
  2) 盲并行的失败模式: 占位符还没被回填就开跑, 拿到 "$1" 字符串——
     错得快不等于对, 依赖错序的结果必须拦截。
  3) 回填顺序: 结果按调用 id 归位, 而不是完成顺序——保持与模型的
     tool_call_id 对应关系, 下一轮对话才不会串线。
""")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
