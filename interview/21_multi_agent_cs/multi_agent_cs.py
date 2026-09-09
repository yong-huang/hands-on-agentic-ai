"""
面试项目 21 — 多 Agent 客服系统雏形

覆盖面试题: 设计一个多 Agent 协作的客户服务系统 (高频大题的最小实现)

核心: 路由 Agent + 专家 Agent + 共享上下文 + 人工兜底:
  路由 Agent    意图分类: 订单 / 售后 / 闲聊 / 人工 (真机用 LLM, 离线用规则)
  订单专家      query_order / cancel_order 工具
  售后专家      create_ticket / query_refund 工具
  共享上下文    会话级 Session: 用户身份/订单/历史, 转接不丢
  人工兜底      强烈不满/威胁投诉 → 升级人工
10 条请求端到端测试: 路由正确率 + 转接后上下文可见 (不用重复自我介绍)。

运行:
  MOCK=1 python multi_agent_cs.py    # 离线: 规则路由 + 模板回答
  python multi_agent_cs.py           # 真实: qwen3.8 做意图路由, 专家用工具+模板
"""

import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
AGENTS = ["order", "aftersale", "chitchat", "human"]


def http_chat(messages, num_predict=600):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": num_predict}
    req = urllib.request.Request(
        "{}/chat/completions".format(BASE_URL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer {}".format(API_KEY)})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    content = re.sub(r"<think>.*?</think>\s*", "", msg.get("content") or "",
                     flags=re.S).strip()
    return content or (msg.get("reasoning") or "").strip()


def extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    for m in reversed(re.findall(r"\{[^{}]*\}", text, re.S)):
        try:
            return json.loads(m)
        except json.JSONDecodeError:
            continue
    return {}


# ============================================================
# 共享上下文 (会话状态存储) —— 转接不丢的关键
# ============================================================

class Session:
    def __init__(self, user_id):
        self.user_id = user_id
        self.facts = {}            # name / order / vip ...
        self.history = []          # [(agent, text)]

    def set(self, k, v):
        self.facts[k] = v

    def add(self, agent, text):
        self.history.append((agent, text))

    def summary(self):
        """注入每个专家提示的上下文摘要 —— 转接后他人可见。"""
        if not self.facts:
            return "(新会话, 无已知信息)"
        return "; ".join("{}={}".format(k, v) for k, v in self.facts.items())


# ============================================================
# 工具 (mock 数据)
# ============================================================

ORDERS_DB = {
    "A1002": {"item": "机械键盘", "status": "运输中",
              "trace": "杭州转运中心 -> 派送中"},
    "A1007": {"item": "显示器支架", "status": "已签收"},
}
TICKETS = []


def tool_query_order(order_id):
    return ORDERS_DB.get(order_id)


def tool_cancel_order(order_id):
    if order_id in ORDERS_DB:
        ORDERS_DB[order_id]["status"] = "已取消"
        return True
    return False


def tool_create_ticket(order_id, issue):
    tid = "T-{:03d}".format(len(TICKETS) + 1)
    t = {"ticket_id": tid, "order": order_id, "issue": issue}
    TICKETS.append(t)
    return t


def tool_query_refund(order_id):
    return {"order": order_id,
            "refund_status": "审核中, 预计 3 个工作日到账"}


# ============================================================
# 路由 Agent: 意图分类 (离线规则 / 真机 LLM)
# ============================================================

RULES = [
    ("human", ["投诉", "经理", "人工", "曝光", "工商"]),
    ("aftersale", ["退款", "退货", "坏了", "破损", "维修", "售后"]),
    ("order", ["订单", "到哪", "物流", "发货", "取消", "什么时候到", "能到",
               "快递", "签收"]),
    ("chitchat", ["你好", "在吗", "谢谢", "你们是谁", "哈哈"]),
]

ROUTE_PROMPT = ("客服路由器: 判断用户消息应转给哪个 Agent。"
                "可选: order(查订单/物流/取消) / aftersale(退款退货破损维修) / "
                "chitchat(寒暄或无关话题) / human(强烈不满或要求人工)。\n"
                '只输出 JSON: {"agent": "order"}\n用户消息: ')


def route(text):
    if MOCK:
        for agent, kws in RULES:
            if any(k in text for k in kws):
                return agent
        return "chitchat"
    r = extract_json(http_chat([{"role": "user", "content": ROUTE_PROMPT + text}]))
    agent = r.get("agent", "chitchat")
    return agent if agent in AGENTS else "chitchat"


# ============================================================
# 专家 Agent (各自职责 + 工具 + 共享上下文)
# ============================================================

def get_name(session):
    return session.facts.get("name", "您")


def order_agent(text, session):
    order = session.facts.get("order")
    m = re.search(r"A\d{3,4}", text)
    if m:
        order = m.group(0)
        session.set("order", order)
    info = tool_query_order(order) if order else None
    if info is None:
        return "请提供订单号, 我帮您查询。"
    if "取消" in text:
        tool_cancel_order(order)
        return "{}, 您的订单 {} 已取消。".format(get_name(session), order)
    return "{}, 您的订单 {}({}) 状态: {}, 物流: {}。".format(
        get_name(session), order, info["item"], info["status"],
        info.get("trace", "正常"))


def aftersale_agent(text, session):
    order = session.facts.get("order")
    issue = "质量问题" if any(k in text for k in ("坏了", "破损", "破")) else "退款申请"
    t = tool_create_ticket(order or "未知", issue)
    refund = tool_query_refund(order) if order else {}
    return "{}, 已为您创建售后工单 {}({}), 退款{}。".format(
        get_name(session), t["ticket_id"], issue,
        refund.get("refund_status", "需补充订单号"))


def chitchat_agent(text, session):
    return "{}, 我是智能助手, 可以帮您查订单和处理售后。".format(get_name(session))


def human_agent(text, session):
    return ("{}, 非常抱歉给您带来不好的体验, 已为您升级人工专席, 客服将在 "
            "1 分钟内接入(工单已附上您的完整会话记录)。".format(get_name(session)))


EXPERTS = {"order": order_agent, "aftersale": aftersale_agent,
           "chitchat": chitchat_agent, "human": human_agent}


# ============================================================
# 端到端测试: 1 个会话 10 条请求
# ============================================================

REQUESTS = [
    ("我是林晓, 订单 A1002 到哪了?", "order"),
    ("大概什么时候能到?", "order"),
    ("这键盘包装破了个角, 我想退款", "aftersale"),
    ("退款多久能到账?", "aftersale"),
    ("顺便帮我查下订单 A1007 签收没有", "order"),
    ("你们是谁啊", "chitchat"),
    ("哈哈好的谢谢", "chitchat"),
    ("再帮我取消 A1007 吧", "order"),
    ("我要投诉你们经理! 太差劲了!", "human"),
    ("人工什么时候接入?", "human"),
]


def extract_facts(text, session):
    """信息抽取层: 身份/订单进共享上下文 (所有专家可见)。"""
    m = re.search(r"我(?:是|叫)([\u4e00-\u9fff]{2,3})", text)
    if m and not session.facts.get("name"):
        session.set("name", m.group(1))
    m = re.search(r"A\d{3,4}", text)
    if m:
        session.set("order", m.group(0))


def main():
    print("=" * 72)
    print("多 Agent 客服系统 (路由 + 专家 + 共享上下文 + 人工兜底) -- {}".format(
        "MOCK (规则路由)" if MOCK else "真实 qwen3.8 路由"))
    print("=" * 72)

    session = Session("u1001")
    print("\n==> 10 条请求端到端")
    ok_route, ctx_checks = 0, [0, 0]
    for text, expected in REQUESTS:
        extract_facts(text, session)
        agent = route(text)
        reply = EXPERTS[agent](text, session)
        session.add(agent, text)
        ok = (agent == expected)
        ok_route += ok
        # 上下文可见性: 已知用户名后, 任何专家的回复都应能带上称呼
        if session.facts.get("name"):
            ctx_checks[0] += int(get_name(session) in reply)
            ctx_checks[1] += 1
        print("  [{:<4}] {:<28} -> {}".format(
            agent, text[:26], reply[:44]))
        if not ok:
            print("      ^ 期望 {} ✗".format(expected))

    print("\n" + "=" * 72)
    print("路由正确: {}/10".format(ok_route))
    print("上下文可见 (转接后回复带称呼): {}/{}".format(ctx_checks[0], ctx_checks[1]))
    print("会话轨迹: {}".format(
        [a for a, _ in session.history]))
    print("=" * 72)
    print("""
要点: 设计一个多 Agent 客服系统
  1) 路由层决定架构: 意图分类(快) / LLM 路由(准) / 混合(规则先兜底,
     低置信再上模型); 人工兜底是第四个 Agent, 不是失败。
  2) 共享上下文是转接体验的生命线: 身份/订单/已做过的事放会话级
     Session, 专家只读自己需要的部分 —— 用户永远不必重复自我介绍。
  3) 专家各自持工具与提示词, 互不感知; 新增专家 = 注册一个处理器,
     路由表加一项 (项目 22 用 Agent Card 把这件事自动化)。
""")


if __name__ == "__main__":
    main()
