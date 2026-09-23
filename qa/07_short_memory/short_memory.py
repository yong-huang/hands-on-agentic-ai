"""
面试项目 7 — 短期记忆管理器（窗口 + 摘要压缩）

覆盖面试题: 上下文窗口溢出怎么办？摘要压缩和滑动窗口各有什么问题？

核心: 20 轮长对话, 前几轮埋 5 个关键事实 (姓名/城市/截止日/预算/咖啡偏好),
两种超限策略对跑:
  滑动窗口   丢最旧消息保预算   → 早期事实整段丢失
  摘要压缩   超限时 LLM 压缩旧对话 → 细节(数字)被抹掉
第 20 轮提问 5 个事实, 统计保留率, 输出对比表。token 计数用字符估算
(生产换 tiktoken), 预算设得很紧以放大两种策略各自的丢失场景。

运行:
  MOCK=1 python short_memory.py    # 离线: 窗口机械执行 + 摘要走预置
  python short_memory.py           # 真实: qwen3.8 做摘要与最终问答
"""

import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
BUDGET = 350          # est.tokens, 人为收紧让 20 轮必然多次溢出 (全量约 500+)
SYSTEM = "你是助理, 根据对话历史简洁回答。"


def est_tokens(text):
    """字符级 token 估算 (中文≈0.6/字符)。生产环境用 tiktoken 精确计数。"""
    return int(len(str(text)) * 0.6) + 1


def llm(messages, num_predict=300):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": num_predict}
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.S).strip()
    if not content:                       # 思考模型可能把内容放进独立字段
        content = (msg.get("reasoning") or msg.get("reasoning_content") or "").strip()
    return content


# ============================================================
# 20 轮对话 (user, mock_assistant); 关键事实埋点: T1/T2/T4, 咖啡在 T16
# ============================================================

TURNS = [
    ("你好, 我叫林晓, 常驻杭州, 以后合作多关照。", "好的林晓, 你好!"),
    ("我们项目的截止日是 10 月 18 日, 预算是 5 万。", "收到, 截止日和预算记下了。"),
    ("先帮我把这句话翻译成英文: 我们承诺按时交付。", "We are committed to on-time delivery."),
    ("帮我把这段介绍压缩到 30 字: 本项目旨在通过多智能体协作提升客服系统的应答效率与用户满意度, 减少人工介入。", "多智能体协作提升客服应答效率与满意度, 减少人工介入。"),
    ("再翻译一句: 望批准。", "Please approve."),
    ("你觉得自己擅长什么? 随便聊聊。", "我擅长文本处理、信息检索和任务编排这类事。"),
    ("写一句朋友圈文案, 主题是加班。", "夜色不错, 代码也是。"),
    ("把 'meeting' 拼写反着写给我看。", "gniteem"),
    ("帮我数一下这句话有几个字: 上下文窗口是稀缺资源。", "11 个字。"),
    ("给我讲个 10 字以内的冷笑话。", "雪 why 融化了? 因为 sun 出来了。"),
    ("帮我想三个产品名, 主题是笔记应用。", "墨痕 / 随记 / 拾言。"),
    ("把 3456 每位数字相加。", "3+4+5+6=18。"),
    ("用一句话解释什么是复利。", "利滚利: 收益并入本金继续生息。"),
    ("推荐一首适合写代码时听的曲子。", "试试 Lo-fi 的《Snowman》。"),
    ("把 '格物致知' 翻译成英文。", "Investigate things to attain knowledge."),
    ("对了帮我记一下, 我咖啡只喝燕麦拿铁。", "好的, 只喝燕麦拿铁, 记住了。"),
    ("帮我写个迟到道歉模板, 20 字内。", "抱歉迟到, 会议要点请同步我, 下次提前到。"),
    ("把这句话改成被动语态: 团队完成了交付。", "交付由团队完成了。"),
    ("给我一个周末杭州周边游的建议。", "可以去莫干山徒步, 当天往返。"),
    ("对了, 考你一下: 我叫什么名字? 在哪个城市? 项目截止日和预算是多少? 我咖啡喝什么?", ""),
]

FACTS = [("姓名", "林晓"), ("城市", "杭州"), ("截止日", "10月18日"),
         ("预算", "5万"), ("咖啡", "燕麦拿铁")]


def grade(answer):
    """按关键词判定每个事实是否被正确召回。"""
    checks = {
        "姓名": "林晓" in answer,
        "城市": "杭州" in answer,
        "截止日": ("10" in answer and "18" in answer),
        "预算": ("5万" in answer.replace(" ", "")) or ("5 万" in answer),
        "咖啡": "燕麦拿铁" in answer,
    }
    return checks


# ============================================================
# 两种记忆管理策略
# ============================================================

def msg_tokens(messages):
    return sum(est_tokens(m["content"]) for m in messages)


def sliding_window(messages, budget, log):
    """策略 A: 从最旧开始丢, 直到装得下。早期事实整段消失。"""
    sys_msg, rest = messages[0], messages[1:]
    kept, used = [], est_tokens(sys_msg["content"])
    for m in reversed(rest):
        t = est_tokens(m["content"])
        if used + t > budget:
            break
        kept.insert(0, m)
        used += t
    dropped = len(rest) - len(kept)
    if dropped:
        log.append(f"窗口截断: 丢弃最旧 {dropped} 条消息")
    return [sys_msg] + kept


def summarize_compress(messages, budget, log):
    """策略 B: 超限时把最旧的 60% 压成一条摘要, 保留最近原文。细节会被抹掉。"""
    if MOCK:
        # 预置摘要只覆盖前 60% 轮次 (T1-T12), 故意抹掉 "预算 5 万" —— 演示摘要丢数字细节
        summary = "[历史摘要] 用户林晓, 常驻杭州, 项目截止 10 月 18 日; 另有若干翻译/文案类闲聊。"
    else:
        old = messages[1:1 + int((len(messages) - 1) * 0.6)]
        text = "\n".join(f"{m['role']}: {m['content']}" for m in old)
        summary = llm([{"role": "user", "content":
                        "把以下对话压缩成一条要点摘要, 必须保留用户的姓名/城市/日期/数字等"
                        f"关键信息, 100 字以内:\n{text}"}], num_predict=200)
        summary = f"[历史摘要] {summary}"
    # 摘要也塞不进预算时, 继续丢更旧的原文
    packed = [messages[0], {"role": "user", "content": summary}] + \
        messages[1 + int((len(messages) - 1) * 0.6):]
    while msg_tokens(packed) > budget and len(packed) > 3:
        packed.pop(2)
    log.append(f"摘要压缩: 前 60% 对话 → {len(summary)} 字摘要")
    return packed


class ShortTermMemory:
    def __init__(self, budget, strategy):
        self.budget, self.strategy = budget, strategy
        self.buf = [{"role": "system", "content": SYSTEM}]
        self.log = []

    def add_turn(self, user, assistant):
        self.buf += [{"role": "user", "content": user}]
        if assistant:
            self.buf += [{"role": "assistant", "content": assistant}]
        while msg_tokens(self.buf) > self.budget:
            before = msg_tokens(self.buf)
            if self.strategy == "window":
                self.buf = sliding_window(self.buf, self.budget, self.log)
            else:
                self.buf = summarize_compress(self.buf, self.budget, self.log)
            if msg_tokens(self.buf) >= before:      # 防御: 压不动了就硬截断
                self.buf = sliding_window(self.buf, self.budget, self.log)
                break

    def ask(self, question):
        self.add_turn(question, "")
        answer = llm(self.buf) if not MOCK else MOCK_ANSWERS[self.strategy]
        return answer


# 预置最终回答 (MOCK): 模拟两种策略下模型"能看到什么就答什么"
MOCK_ANSWERS = {
    "window": "抱歉, 前面的对话被截掉了, 我不记得你的名字/城市/项目信息。"
              "只看到你咖啡只喝燕麦拿铁。",
    "summary": "你叫林晓, 常驻杭州, 项目截止 10 月 18 日, 咖啡只喝燕麦拿铁;"
               "预算这条摘没有记全, 我不确定。",
}


def run_strategy(strategy):
    mem = ShortTermMemory(BUDGET, strategy)
    for i, (user, asst) in enumerate(TURNS[:-1], 1):
        mem.add_turn(user, asst)
    answer = mem.ask(TURNS[-1][0])
    checks = grade(answer)
    kept = sum(checks.values())
    return {"strategy": strategy, "answer": answer, "checks": checks, "kept": kept,
            "tokens": msg_tokens(mem.buf), "events": len(mem.log), "log": mem.log}


def main():
    print("=" * 72)
    print(f"短期记忆管理器 (滑动窗口 vs 摘要压缩) -- {'MOCK (离线)' if MOCK else '真实 qwen3.8'}")
    print(f"20 轮对话 | token 预算 {BUDGET} (est) | 埋点: T1 姓名/城市 T2 截止日/预算 T16 咖啡")
    print("=" * 72)

    results = []
    for strategy in ("window", "summary"):
        print(f"\n==> 策略 [{strategy}]")
        r = run_strategy(strategy)
        results.append(r)
        for line in r["log"][:3]:
            print(f"  · {line}")
        print(f"  最终上下文 {r['tokens']} est.tokens, 管理 {r['events']} 次")
        print(f"  最终回答: {r['answer'][:80]}")

    print("\n" + "=" * 72)
    print(f"{'事实':<8}{'滑动窗口':>12}{'摘要压缩':>12}")
    print("-" * 40)
    for fact, _ in FACTS:
        w = "✓" if results[0]["checks"][fact] else "✗"
        s = "✓" if results[1]["checks"][fact] else "✗"
        print(f"{fact:<8}{w:>10}{s:>10}")
    print("-" * 40)
    print(f"{'保留率':<8}{results[0]['kept']}/5{results[1]['kept']:>9}/5")
    print("""
要点: 溢出怎么办 / 两种策略各输在哪
  1) 滑动窗口: 简单可靠、零成本, 但"最近的才存在"——早期事实整段蒸发。
  2) 摘要压缩: 保留语义骨架, 但细节被抹平——数字/日期/专名最容易丢。
  3) 生产组合拳: 窗口保近期原文 + 摘要保远期骨架 + 关键事实抽取进
     长期记忆库 (项目 8) 按需检索, 三层各管一段。
""")


if __name__ == "__main__":
    main()
