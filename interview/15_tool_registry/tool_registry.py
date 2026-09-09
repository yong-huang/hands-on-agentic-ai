"""
面试项目 15 — 工具注册表与 Schema 设计

覆盖面试题: Function Calling 的 JSON Schema 怎么设计？嵌套参数怎么处理？

核心: 装饰器式工具注册表:
  @tool 从函数签名 + docstring 自动生成 JSON Schema (含描述)
  嵌套参数 (数组内对象 / 对象内对象) 用显式 JSON Schema 声明, jsonschema 校验
  错误友好化: 路径(items[1].qty) + 期望vs实际 + 修正提示, 结构化喂回模型
  结果标准化: {"ok": true, "data": ...} / {"ok": false, "error": {...}}
验收: 5 个含嵌套参数的工具全通; 故意错参 → 模型读结构化错误自行纠正。

运行:
  MOCK=1 python tool_registry.py    # 离线: 预置模型纠错
  python tool_registry.py           # 真实: qwen3.8 读错误后自行纠正
"""

import json, os, re, sys, inspect, urllib.request

import jsonschema

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"


def http_chat(messages, num_predict=1400):
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
            return {}
    return {}


PY_TYPE = {str: "string", int: "integer", float: "number", bool: "boolean",
           list: "array", dict: "object"}


# ============================================================
# 装饰器式注册表: 签名 + docstring -> JSON Schema
# ============================================================

REGISTRY = {}          # name -> {"fn", "schema", "desc"}


def tool(description="", nested=None):
    """@tool(描述, nested={"参数名": {嵌套 schema}})
    基本类型从函数签名推导; 复杂嵌套结构显式传入 JSON Schema。
    docstring 里 `参数名: 说明` 的行自动变成字段 description。"""
    def deco(fn):
        sig = inspect.signature(fn)
        props, required = {}, []
        param_docs = dict(re.findall(r"^\s*(\w+):\s*(.+)$", fn.__doc__ or "", re.M))
        for name, p in sig.parameters.items():
            if name in nested:
                props[name] = {**nested[name],
                               "description": param_docs.get(name, name)}
            else:
                props[name] = {"type": PY_TYPE.get(p.annotation, "string"),
                               "description": param_docs.get(name, name)}
            if p.default is inspect.Parameter.empty:
                required.append(name)
        schema = {"type": "object", "properties": props, "required": required}
        REGISTRY[fn.__name__] = {"fn": fn, "schema": schema, "desc": description}
        return fn
    return deco


@tool("创建订单, 支持多商品与优惠券",
      nested={"items": {"type": "array", "items": {
          "type": "object",
          "properties": {"sku": {"type": "string"},
                         "qty": {"type": "integer", "minimum": 1}},
          "required": ["sku", "qty"]}}})
def create_order(items, coupon=""):
    """创建订单。
    items: 商品列表 [{sku, qty}]
    coupon: 优惠券码(可选)"""
    total = {"A1": 99, "B2": 199}.get(items[0]["sku"], 50) * sum(i["qty"] for i in items)
    return {"order_id": "ORD-88", "total": total}


@tool("安排会议, 多位参会人",
      nested={"attendees": {"type": "array", "items": {
          "type": "object",
          "properties": {"name": {"type": "string"},
                         "email": {"type": "string", "format": "email"}},
          "required": ["name", "email"]}}})
def add_meeting(title, time, attendees):
    """安排会议。
    title: 会议主题
    time: 开始时间
    attendees: 参会人 [{name, email}]"""
    return {"meeting_id": "MTG-3", "invited": len(attendees)}


@tool("跨行转账",
      nested={"accounts": {"type": "object", "properties": {
          "from": {"type": "object", "properties": {
              "bank": {"type": "string"}, "acct": {"type": "string"}},
              "required": ["bank", "acct"]},
          "to": {"type": "object", "properties": {
              "bank": {"type": "string"}, "acct": {"type": "string"}},
              "required": ["bank", "acct"]}},
          "required": ["from", "to"]}})
def transfer_money(accounts, amount: int):
    """跨行转账。
    accounts: {from: {bank,acct}, to: {bank,acct}}
    amount: 金额"""
    return {"txn_id": "TX-1", "amount": amount}


@tool("查询机票",
      nested={"route": {"type": "object", "properties": {
          "from_city": {"type": "string"}, "to_city": {"type": "string"}},
          "required": ["from_city", "to_city"]},
              "passengers": {"type": "array", "items": {
                  "type": "object",
                  "properties": {"ptype": {"type": "string", "enum": ["adult", "child"]},
                                 "count": {"type": "integer"}},
                  "required": ["ptype", "count"]}}})
def query_flights(route, passengers):
    """查询机票。
    route: {from_city, to_city}
    passengers: 乘客 [{ptype, count}]"""
    n = sum(p["count"] for p in passengers)
    return {"flights": [f"CA{1800+n}", f"¥{900 * n}"]}


@tool("配置告警规则",
      nested={"rules": {"type": "array", "items": {
          "type": "object",
          "properties": {"metric": {"type": "string"},
                         "op": {"type": "string", "enum": [">", "<"]},
                         "threshold": {"type": "number"}},
          "required": ["metric", "op", "threshold"]}}})
def configure_alert(rules, channel="email"):
    """配置告警。
    rules: [{metric, op, threshold}]
    channel: 通知渠道(可选)"""
    return {"rule_ids": [f"R{i}" for i in range(len(rules))], "channel": channel}


# ============================================================
# 标准化调用: 校验 + 错误友好化
# ============================================================

def call_tool(name, args):
    """统一入口: 未知工具/校验失败/执行异常 全部标准化为模型可读的结构。"""
    t = REGISTRY.get(name)
    if not t:
        return {"ok": False, "error": {
            "code": "UNKNOWN_TOOL",
            "message": f"工具 {name!r} 不存在",
            "available": sorted(REGISTRY)}}
    try:
        jsonschema.validate(args, t["schema"])
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) or "(root)"
        return {"ok": False, "error": {
            "code": "INVALID_ARGS",
            "message": f"参数 {path} 校验失败: {e.message}",
            "expected_schema": e.schema if len(str(e.schema)) < 300 else
            {"type": "见 schema"},
            "hint": "请修正参数后重新调用同一工具"}}
    try:
        return {"ok": True, "data": t["fn"](**args)}
    except Exception as e:
        return {"ok": False, "error": {"code": "EXEC_ERROR", "message": str(e)}}


# 故意错参的调用 (演示纠错链路)
BAD_CALLS = [
    ("create_order", {"items": [{"sku": "A1", "qty": 0}]}),          # qty 违反 minimum
    ("query_flights", {"route": {"from_city": "北京"},                # 缺 to_city
                       "passengers": [{"ptype": "adult", "count": 1}]}),
    ("configure_alert", {"rules": [{"metric": "p99", "op": "≈", "threshold": 1}]}),  # op 不在枚举
]


def main():
    print("=" * 72)
    print(f"工具注册表与 Schema 设计 -- {'MOCK (离线)' if MOCK else '真实 qwen3.8 纠错'}")
    print(f"注册工具 {len(REGISTRY)} 个 (均含嵌套参数) | jsonschema 校验")
    print("=" * 72)

    # --- 5 个嵌套工具全通 ---
    print("\n==> 合法调用 (嵌套参数全通)")
    good = [
        ("create_order", {"items": [{"sku": "A1", "qty": 2}, {"sku": "B2", "qty": 1}]}),
        ("add_meeting", {"title": "评审", "time": "周五 14:00",
                         "attendees": [{"name": "林晓", "email": "lx@x.com"}]}),
        ("transfer_money", {"accounts": {"from": {"bank": "ICBC", "acct": "6222"},
                                         "to": {"bank": "CMBC", "acct": "6211"}},
                            "amount": 500}),
        ("query_flights", {"route": {"from_city": "北京", "to_city": "上海"},
                           "passengers": [{"ptype": "adult", "count": 2}]}),
        ("configure_alert", {"rules": [{"metric": "p99", "op": ">", "threshold": 800}]}),
    ]
    n_ok = 0
    for name, args in good:
        r = call_tool(name, args)
        n_ok += r["ok"]
        print(f"  {name:<16} {'✓' if r['ok'] else '✗'} {json.dumps(r.get('data') or r['error'], ensure_ascii=False)[:60]}")
    print(f"  => {n_ok}/5 通过")

    # --- 故意错参 → 结构化错误 ---
    print("\n==> 故意错参 (错误喂回模型)")
    for name, args in BAD_CALLS:
        r = call_tool(name, args)
        err = r["error"]
        print(f"  {name}: {err['message']}")

    print("\n==> 模型纠错")
    for name, args in BAD_CALLS:
        r = call_tool(name, args)
        if MOCK:
            fixed = {"create_order": {"items": [{"sku": "A1", "qty": 2}]},
                     "query_flights": {"route": {"from_city": "北京", "to_city": "上海"},
                                       "passengers": [{"ptype": "adult", "count": 1}]},
                     "configure_alert": {"rules": [{"metric": "p99", "op": ">",
                                                    "threshold": 1}]}}[name]
        else:
            fixed = extract_json(http_chat([{"role": "user", "content":
                f"你调用 {name} 时参数非法:\n参数: {json.dumps(args, ensure_ascii=False)}\n"
                f"错误信息: {json.dumps(r['error'], ensure_ascii=False)}\n"
                f"完整 Schema: {json.dumps(REGISTRY[name]['schema'], ensure_ascii=False)}\n"
                '请给出修正后的参数。只输出 JSON: {"args": {...}}'}])) or {}
            fixed = fixed.get("args", fixed)
        r2 = call_tool(name, fixed)
        print(f"  {name:<16} 修正后 {'✓ 通过' if r2['ok'] else '✗ ' + str(r2['error'])[:48]}")

    print("""
要点: FC 的 JSON Schema 怎么设计 / 嵌套参数怎么处理
  1) Schema 是给模型看的 API 文档: 类型+枚举+描述缺一不可,
     docstring 的"参数名: 说明"应自动进字段 description (单一事实源)。
  2) 嵌套参数用 items.properties 显式声明, 校验错误必须带路径
     (items[1].qty)——没有路径的报错模型修不了。
  3) 错误友好化 = 结构化 (code/message/hint) 而不是堆栈字符串;
     模型读得懂错误, 才能自行纠正——这是 Agent 稳定性的隐藏关键。
""")


if __name__ == "__main__":
    main()
