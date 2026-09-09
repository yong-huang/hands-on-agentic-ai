"""
面试项目 22 — Agent Card 与 A2A 风格互操作

覆盖面试题: A2A 和 MCP 的区别？Agent Card 怎么描述 Agent 能力？

核心: 每个 Agent 对外发布一张 Agent Card (JSON: 描述/技能/输入输出 schema/端点);
客户端闭环 = 发现(拉卡片) -> 匹配(按技能描述) -> 调用(统一 invoke)。
零改动验证: 运行时注册一张新卡片(promo 促销 Agent), 路由端不改一行代码,
下一轮发现即可路由并调用它 —— 这就是 A2A 的开放接入。
真机模式追加 LLM 技能匹配 (把卡片摘要给模型, 让它选 Agent)。

运行:
  MOCK=1 python agent_card.py    # 离线: 关键词技能匹配
  python agent_card.py           # 真实: qwen3.8 选 Agent
"""

import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"


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
# Agent 业务实现 (复用项目 21 的专家逻辑, 简化)
# ============================================================

def order_query(payload):
    return "订单 {} 状态: 运输中(杭州 -> 派送中)".format(payload.get("order_id", "A1002"))


def aftersale_refund(payload):
    return "已为订单 {} 创建退款单, 预计 3 个工作日到账".format(
        payload.get("order_id", "A1002"))


def chitchat_chat(payload):
    return "你好, 我是咨询助手, 订单与售后请转对应专家。"


def human_escalate(payload):
    return "已升级人工专席, 客服 1 分钟内接入。"


def promo_list(payload):
    return "本周大促: 全场满 199 减 30, VIP 折上 9 折。"


# ============================================================
# Agent Card: 能力自描述
# ============================================================

def make_card(name, description, skills, endpoint):
    return {"name": name, "description": description,
            "skills": skills, "endpoint": endpoint}


CARD_BOOK = [
    make_card("order-agent", "查订单、物流跟踪、取消订单",
              [{"id": "query_order",
                "desc": "查询订单状态与物流",
                "input": {"order_id": "string"},
                "output": {"status": "string"}}],
              "a2a://cs/order"),
    make_card("aftersale-agent", "退款、退货、维修等售后处理",
              [{"id": "apply_refund",
                "desc": "对指定订单发起退款",
                "input": {"order_id": "string"},
                "output": {"refund_status": "string"}}],
              "a2a://cs/aftersale"),
    make_card("chitchat-agent", "寒暄与一般咨询",
              [{"id": "chat",
                "desc": "自由对话与常见问题",
                "input": {"text": "string"},
                         'output': {'reply': 'string'}}],
              "a2a://cs/chitchat"),
    make_card("human-agent", "人工专席升级兜底",
              [{"id": "escalate",
                "desc": "升级到人工客服",
                "input": {"reason": "string"},
                "output": {"eta": "string"}}],
              "a2a://cs/human"),
]

# ============================================================
# Registry 与客户端闭环: 发现 -> 匹配 -> 调用
# ============================================================

MATCH_KEYWORDS = {
    "order-agent": ["订单", "物流", "取消", "签收", "到哪"],
    "aftersale-agent": ["退款", "退货", "售后", "维修"],
    "chitchat-agent": ["你好", "谢谢", "闲聊", "你们是谁"],
    "human-agent": ["投诉", "人工", "经理"],
    "promo-agent": ["优惠", "促销", "活动", "满减", "折扣"],
}


def discover():
    """客户端发现: 拉取全部 Agent Card。"""
    return list(CARD_BOOK)


def match_agent(text, cards):
    """按卡片技能描述选 Agent (MOCK: 关键词; 真机: LLM)。"""
    if MOCK:
        best, best_score = None, 0
        for card in cards:
            kws = MATCH_KEYWORDS.get(card["name"], [])
            score = sum(1 for k in kws if k in text)
            if score > best_score:
                best, best_score = card, score
        return best
    desc = chr(10).join(
        '- {}: {} (技能: {})'.format(c['name'], c['description'],
                                    ', '.join(s['id'] for s in c['skills']))
        for c in cards)
    prompt = ('根据用户请求选择最合适的 Agent。可选 Agent:\n' + desc
              + '\n用户请求: ' + text
              + '\n只输出 JSON: {name: ..., skill: ...}, 键和值都用双引号')
    r = extract_json(http_chat([{'role': 'user', 'content': prompt}]))
    for card in cards:
        if card['name'] == r.get('name'):
            return card
    return cards[0]


def invoke(card, text):
    skill = card['skills'][0]['id']
    handler = HANDLERS.get((card['name'], skill))
    if handler is None:
        return '无可用处理器'
    return handler({'text': text, 'order_id': 'A1002'})


PROMO_CARD = make_card('promo-agent', '营销与促销活动查询',
                       [{'id': 'list_promotions',
                         'desc': '查询当前促销与优惠活动',
                         'input': {'text': 'string'},
                         'output': {'reply': 'string'}}],
                       'a2a://cs/promo')


def main():
    print("=" * 72)
    print("Agent Card 与 A2A 风格互操作 -- {}".format(
        "MOCK (关键词匹配)" if MOCK else "真实 qwen3.8 技能匹配"))
    print("=" * 72)

    print("\n==> 发现: 拉取 Agent Card")
    for c in discover():
        skills = ", ".join(s["id"] for s in c["skills"])
        print("  {:<16} {} [{}] {}".format(
            c["name"], c["description"], skills, c["endpoint"]))

    print("\n==> 调用闭环 (发现 -> 匹配 -> 调用)")
    for text in ("帮我查下订单 A1002", "我要退款", "我要投诉"):
        card = match_agent(text, discover())
        print("  {:<20} -> {} :: {}".format(text, card["name"], invoke(card, text)))

    print("\n==> 零改动接入: 运行时注册 promo-agent (只加卡片+服务)")
    CARD_BOOK.append(PROMO_CARD)
    print("  卡片注册完成, 路由端代码零改动")
    text = "有什么优惠活动?"
    card = match_agent(text, discover())
    print("  {:<20} -> {} :: {}".format(text, card["name"], invoke(card, text)))

    print("\n" + "=" * 72)
    print("发现 -> 匹配 -> 调用 闭环完成; 新 Agent 零改动接入 ✓")
    print("""
要点: A2A 与 MCP 的区别 / Agent Card 怎么写
  1) MCP 是 Agent 接工具的协议 (垂直: Agent <-> 工具/资源);
     A2A 是 Agent 之间协作的协议 (水平: Agent <-> Agent)。
  2) Agent Card = Agent 的名片: 描述/技能清单/输入输出 schema/端点。
     对方据此决定"要不要找你、怎么调你", 无需读对方源码。
  3) 开放接入的价值: 新 Agent 只发布卡片即可被网络发现 (本实验
     运行时注册 promo-agent, 路由端零改动) —— 生态从静态组合变成动态发现。
""")


HANDLERS = {
    ("order-agent", "query_order"): order_query,
    ("aftersale-agent", "apply_refund"): aftersale_refund,
    ("chitchat-agent", "chat"): chitchat_chat,
    ("human-agent", "escalate"): human_escalate,
    ("promo-agent", "list_promotions"): promo_list,
}


if __name__ == "__main__":
    main()

