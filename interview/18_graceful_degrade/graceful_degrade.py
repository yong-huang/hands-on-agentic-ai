"""
面试项目 18 — 工具优雅降级

覆盖面试题: Agent 调用工具失败了怎么优雅降级？

核心: 机票价格查询的降级链, 主工具注入 100% 超时:
  主工具(超时) → 备用工具(覆盖部分城市) → 本地缓存(覆盖部分城市)
   → 诚实拒答(附原因, 真机由 LLM 组织话术)
配套机制:
  可降级标记   价格查询可降级; 支付类标记 critical, 失败直接拒绝不走降级
  熔断器       连续失败 N=3 次打开熔断 (跳过主工具), 冷却后半开探测
验收: 主工具全挂时仍能答 80% 问题 (备用+缓存), 熔断日志可见。

运行:
  MOCK=1 python graceful_degrade.py    # 离线: 拒答话术用模板
  python graceful_degrade.py           # 真实: 拒答话术由 qwen3.8 生成
"""

import asyncio, json, os, re, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
PRIMARY_TIMEOUT = 0.4          # 主工具超时 (秒), 主工具实际要睡 2s → 必超时
BREAKER_THRESHOLD = 3          # 连续失败 3 次打开熔断
BREAKER_COOLDOWN = 1.0         # 冷却时间 (秒)


def http_chat(messages, num_predict=600):
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
# 工具与数据
# ============================================================

BACKUP_PRICES = {"成都": 1600, "上海": 980, "广州": 1250, "深圳": 1380, "西安": 1100}
CACHE_PRICES = {"成都": 1590, "上海": 995, "拉萨": 2200, "海口": 1500, "昆明": 980}
QUESTIONS = ["成都", "上海", "广州", "深圳", "西安", "拉萨", "海口", "昆明",
             "乌鲁木齐", "三亚"]      # 前两个也验证缓存/备用重叠


async def primary_live_price(city):
    """主工具: 实时报价 (注入 100% 超时故障)。"""
    await asyncio.sleep(2.0)
    return {"city": city, "price": 1500, "source": "live"}


async def backup_price(city):
    """备用工具: 批发价接口, 只覆盖部分城市。"""
    await asyncio.sleep(0.05)
    if city in BACKUP_PRICES:
        return {"city": city, "price": BACKUP_PRICES[city], "source": "backup"}
    raise KeyError(city)


def cache_price(city):
    """本地缓存: 数据略旧, 覆盖部分城市。"""
    if city in CACHE_PRICES:
        return {"city": city, "price": CACHE_PRICES[city], "source": "cache"}
    return None


# ============================================================
# 熔断器
# ============================================================

class CircuitBreaker:
    def __init__(self, threshold=3, cooldown=1.0):
        self.threshold, self.cooldown = threshold, cooldown
        self.consecutive_failures = 0
        self.state = "closed"           # closed / open / half-open
        self.opened_at = 0.0
        self.log = []

    def allow(self):
        if self.state == "open":
            if time.monotonic() - self.opened_at >= self.cooldown:
                self.state = "half-open"
                self.log.append("熔断器 half-open: 冷却结束, 放行一次探测")
                return True
            return False
        return True

    def record_success(self):
        self.consecutive_failures = 0
        if self.state != "closed":
            self.log.append("熔断器 closed: 探测成功, 恢复主链路")
        self.state = "closed"

    def record_failure(self):
        self.consecutive_failures += 1
        if self.state == "half-open":
            self.state = "open"
            self.opened_at = time.monotonic()
            self.log.append("熔断器 open: 探测仍失败, 继续熔断")
        elif self.consecutive_failures >= self.threshold:
            self.state = "open"
            self.opened_at = time.monotonic()
            self.log.append(f"熔断器 open: 连续失败 {self.consecutive_failures} 次, "
                            f"暂时摘除主工具 {self.cooldown}s")


# ============================================================
# 降级链
# ============================================================

async def get_price(city, breaker, logs):
    """降级链: 主(熔断感知) → 备用 → 缓存 → 诚实拒答。"""
    if breaker.allow():
        try:
            r = await asyncio.wait_for(primary_live_price(city), PRIMARY_TIMEOUT)
            breaker.record_success()
            return r, None
        except asyncio.TimeoutError:
            breaker.record_failure()
            logs.append(f"  · [主工具] {city} 超时 (>{PRIMARY_TIMEOUT}s), "
                        f"熔断状态={breaker.state}")
    else:
        logs.append(f"  · [主工具] 熔断打开, 跳过 ({city})")
    try:
        r = await backup_price(city)
        logs.append(f"  · [备用工具] 命中 {city}")
        return r, None
    except KeyError:
        cached = cache_price(city)
        if cached:
            logs.append(f"  · [缓存] 命中 {city} (数据略旧)")
            return cached, None
    reason = (f"主工具超时且熔断打开; 备用工具与缓存均无 {city} 的数据")
    return None, reason


async def critical_pay(order):
    """不可降级工具示例: 支付失败 = 直接拒绝, 绝不悄悄用别的方式扣款。"""
    await asyncio.sleep(0.05)
    return None, "支付通道异常; 支付是不可降级操作, 直接拒绝而非找替代"


async def main_async():
    breaker = CircuitBreaker(BREAKER_THRESHOLD, BREAKER_COOLDOWN)
    print("=" * 72)
    print(f"工具优雅降级 -- {'MOCK (拒答用模板)' if MOCK else '真实 qwen3.8 (拒答话术 LLM 生成)'}")
    print(f"查询 {len(QUESTIONS)} 个城市 | 主工具注入 100% 超时 | "
          f"熔断: 连续 {BREAKER_THRESHOLD} 次打开")
    print("=" * 72)

    answered, refused = 0, 0
    for city in QUESTIONS:
        logs = []
        result, reason = await get_price(city, breaker, logs)
        if result:
            answered += 1
            src = {"live": "实时", "backup": "备用接口", "cache": "本地缓存"}[result["source"]]
            print(f"Q {city:<6} ✓ ¥{result['price']}  [{src}]")
        else:
            refused += 1
            if MOCK:
                reply = f"抱歉, {reason}, 暂时无法报价。建议稍后重试。"
            else:
                reply = http_chat([{"role": "user", "content":
                                    f"机票价格查询失败。原因: {reason}\n"
                                    "请生成一句诚实的拒答话术 (说明原因+建议), 40 字内。"}])
            print(f"Q {city:<6} ✗ 拒答: {reply[:56]}")
        for line in logs:
            print(line)

    # 不可降级工具对照
    _, pay_reason = await critical_pay("ORD-1")
    print(f"\n[对照] 不可降级工具 (支付): {pay_reason}")

    for line in breaker.log:
        print(f"  ⚡ {line}")

    rate = answered * 100 // len(QUESTIONS)
    print("\n" + "=" * 72)
    ok_mark, bad_mark = chr(0x2713), chr(0x2717)
    print(f"可用率: {answered}/{len(QUESTIONS)} ({rate}%)  "
          f"{ok_mark if rate >= 80 else bad_mark} (备用+缓存兜底, 验收线 80%)")
    print(f"熔断器日志 {len(breaker.log)} 条 "
          f"{ok_mark + ' 可见' if breaker.log else bad_mark}")
    print("""
要点: 工具失败怎么优雅降级
  1) 降级链是逐级放宽的一致性: 实时价 → 批发价 → 旧缓存 → 拒答,
     每降一级都要让用户知道数据来源, 拒答必须带原因。
  2) 可降级性是工具的属性: 查询类可降级, 资金/删除类不可降级——
     支付失败找个"替代通道"是事故, 不是降级。
  3) 熔断器保护的是系统: 连续失败 N 次就摘除主工具, 避免每个请求
     都白等一个超时; 冷却后半开探测, 恢复要及时。
""")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
