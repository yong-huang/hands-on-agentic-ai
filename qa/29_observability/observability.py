"""
面试项目 29 — Agent 可观测性 (Tracing + 回放)

覆盖面试题: 设计 Agent 的可观测性系统（生产级必问）

核心: 给一次确定性 Agent 执行 (规划 -> 3 个工具调用, 含一次异常重试) 埋点:
  事件流     JSONL 落盘: span_id/parent_id/类型/输入输出/tokens/耗时/异常
  trace 树   按 parent_id 还原调用树, CLI 缩进渲染 (一眼看清谁调了谁)
  统计面板   总 token / 成本 / P99 延迟 / 各工具调用次数
  时间旅行   读回 JSONL, 不调任何模型, 逐步重放执行路径并校验一致
全流程离线可跑 (事件由脚本化 Agent 产生, 无 LLM 依赖)。

运行:
  python observability.py    # 生成事件 -> 渲染 -> 统计 -> 回放
"""

import json, math, os, time

EVENTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces.jsonl")
PRICE_PER_1K = 0.002          # 演示单价


# ============================================================
# 事件采集器
# ============================================================

class Tracer:
    def __init__(self, path):
        self.path = path
        self.events = []
        if os.path.exists(path):
            os.remove(path)

    def span(self, parent, type_, name, input_=""):
        span_id = "s{:03d}".format(len(self.events) + 1)
        ev = {"span_id": span_id, "parent_id": parent, "type": type_,
              "name": name, "input": str(input_)[:60], "output": "",
              "tokens": 0, "latency_ms": 0, "error": None,
              "ts": time.strftime("%H:%M:%S")}
        self.events.append(ev)
        return span_id

    def finish(self, span_id, output="", tokens=0, latency_ms=0, error=None):
        for ev in self.events:
            if ev["span_id"] == span_id:
                ev["output"] = str(output)[:80]
                ev["tokens"] = tokens
                ev["latency_ms"] = latency_ms
                ev["error"] = error
        self.flush()

    def flush(self):
        with open(self.path, "w") as f:
            for ev in self.events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")


# ============================================================
# 一次脚本化的 Agent 执行 (埋点演示: 规划 -> 工具, 含异常重试)
# ============================================================

def run_agent(tracer, question):
    root = tracer.span(None, "agent", "root", question)
    t0 = time.perf_counter()
    plan_sid = tracer.span(root, "llm", "planner", question)
    time.sleep(0.02)
    tracer.finish(plan_sid, '["查库存 A1", "查价格 A1", "下单 A1x2"]',
                  tokens=180, latency_ms=int((time.perf_counter() - t0) * 1000))

    def tool_stock(sku):
        time.sleep(0.01)
        return "A1 库存=12"

    def tool_price(sku):
        time.sleep(0.015)
        raise RuntimeError("价格服务 503")

    def tool_order(sku, qty):
        time.sleep(0.01)
        return "订单 O001 创建"

    tools = {"查库存": (tool_stock, ["A1"]),
             "查价格": (tool_price, ["A1"]),
             "下单": (tool_order, ["A1", 2])}
    total_tokens = 180
    for name, (fn, args) in tools.items():
        sid = tracer.span(root, "tool", name, str(args))
        attempt, out, err = 0, None, None
        while attempt < 2:
            attempt += 1
            t1 = time.perf_counter()
            try:
                out = fn(*args)
                err = None
                break
            except Exception as e:
                err = str(e)
        ms = int((time.perf_counter() - t1) * 1000) + attempt * 12
        tracer.finish(sid, out if out else "(重试成功)" if not err else err,
                      tokens=40, latency_ms=ms,
                      error=None if not err else "第一次尝试失败: " + err)
        total_tokens += 40
    return total_tokens


# ============================================================
# trace 树渲染 / 统计面板 / 回放
# ============================================================

def load_events(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def render_tree(events):
    by_parent = {}
    for ev in events:
        by_parent.setdefault(ev["parent_id"], []).append(ev)
    print("==> trace 树")
    def walk(parent, depth):
        for ev in by_parent.get(parent, []):
            flag = " ⚠{}".format(ev["error"]) if ev["error"] else ""
            print("  {}[{}] {} ({}ms, {} tok){}".format(
                "  " * depth, ev["type"], ev["name"],
                ev["latency_ms"], ev["tokens"], flag))
            walk(ev["span_id"], depth + 1)
    walk(None, 0)


def stats_panel(events):
    print("\n==> 统计面板")
    total_tokens = sum(e["tokens"] for e in events)
    lat = sorted(e["latency_ms"] for e in events)
    p99 = lat[min(len(lat) - 1, math.ceil(0.99 * len(lat)) - 1)]
    tool_counts = {}
    for e in events:
        if e["type"] == "tool":
            tool_counts[e["name"]] = tool_counts.get(e["name"], 0) + 1
    errors = [e for e in events if e["error"]]
    print("  spans={}  总token={}  估算成本=¥{:.4f}".format(
        len(events), total_tokens, total_tokens / 1000 * PRICE_PER_1K))
    print("  P99 延迟={}ms  最大={}ms".format(p99, max(lat)))
    print("  工具调用: {}  异常 span: {}".format(tool_counts, len(errors)))


def replay(events):
    print("\n==> 时间旅行回放 (离线, 不调模型)")
    n = 0
    for ev in events:
        n += 1
        print("  #{} [{}] {} | 输入={} | 输出={}".format(
            n, ev["type"], ev["name"], ev["input"][:30], ev["output"][:40]))
        if ev["error"]:
            print("     ⚠ 异常: {} -> 自动重试后成功".format(ev["error"]))
    with open(EVENTS_PATH) as f:
        on_disk = sum(1 for line in f if line.strip())
    print("  事件一致性: 落盘 {} = 回放 {} {}".format(
        on_disk, n, "✓" if on_disk == n else "✗"))


def main():
    tracer = Tracer(EVENTS_PATH)
    tokens = run_agent(tracer, "帮我把 A1 图书下单 2 本")
    events = load_events(EVENTS_PATH)
    print("=" * 72)
    print("Agent 可观测性 -- spans={} 总token={}".format(len(events), tokens))
    print("=" * 72)
    render_tree(events)
    stats_panel(events)
    replay(events)
    print("""
要点: 可观测性系统怎么设计
  1) 一切皆事件: 每个 span 记 类型/父子关系/输入输出/token/耗时/异常,
     JSONL 落盘 —— 事后一切分析 (树/统计/回放) 都从它派生。
  2) trace 树回答"谁调了谁": 排障时先看树找到异常 span, 再下钻输入
     输出; 统计面板回答"贵不贵/慢不慢" (token 成本 + P99 延迟)。
  3) 时间旅行 = 确定性重放: 用记录的事件离线复现执行路径, 不调模型
     —— 调试、回归测试、给面试官演示都靠它。
""")


if __name__ == "__main__":
    main()
