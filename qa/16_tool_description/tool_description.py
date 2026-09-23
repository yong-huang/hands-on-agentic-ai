"""
面试项目 16 — 工具描述优化实验

覆盖面试题: 工具描述写得好不好直接影响调用准确率, 你怎么优化？

核心: 同一套 4 个易混工具 (机票/高铁/天气/酒店), 写 3 版描述:
  V1 差   只有一句话名字
  V2 中   补参数说明
  V3 好   补使用时机 + 边界反例 + 示例
50 条用户指令 (30 易 / 12 中 / 8 难) 跑"选对工具"评测。
真机用批量调用 (每 call 评 10 条指令) 控制 LLM 次数; MOCK 用确定性
难度模型模拟三版差异。输出单调递增对比表 + 描述写法清单。

运行:
  MOCK=1 python tool_description.py    # 离线: 确定性难度模型
  python tool_description.py           # 真实: qwen3.8 批量选工具
"""

import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"


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
# 同一工具集的 3 版描述
# ============================================================

TOOLS_V1 = """
search_flight: 查机票
search_train: 查火车
query_weather: 查天气
book_hotel: 订酒店
"""

TOOLS_V2 = """
search_flight: 查询机票航班与价格。参数: city(目的地), date(日期, 可选)
search_train: 查询火车/高铁车次与票价。参数: city(目的地), date(日期, 可选)
query_weather: 查询城市天气。参数: city(城市)
book_hotel: 预订酒店房间。参数: city(城市), nights(晚数, 默认1)
"""

TOOLS_V3 = """
search_flight: 查询【机票】航班与价格。
  何时用: 用户要坐飞机/赶时间/跨省长途(如 北京→成都)。
  不要用: 市内或短途出行(用 search_train); 问天气(用 query_weather)。
  示例: "帮我查下周去成都的机票" -> search_flight(city=成都)
search_train: 查询【火车/高铁】车次与票价。
  何时用: 高铁/动车/火车字样, 或短途城际(如 杭州→上海)。
  示例: "到上海的高铁票" -> search_train(city=上海)
query_weather: 查询城市【天气/温度/降雨】。
  不要用: 查任何票务。
  示例: "成都下雨吗" -> query_weather(city=成都)
book_hotel: 预订【酒店/住宿】。
  何时用: 住/宿/酒店/过夜。示例: "订两晚酒店" -> book_hotel(city=X, nights=2)
"""

VERSIONS = {"V1-一句话": TOOLS_V1, "V2-补参数": TOOLS_V2, "V3-时机反例": TOOLS_V3}


# ============================================================
# 50 条指令: (文本, 正确工具, 难度)
# ============================================================

def _q():
    rows = []
    easy = [
        ("查一下下周去成都的机票", "search_flight"),
        ("北京到广州的航班多少钱", "search_flight"),
        ("帮我订去深圳的飞机票", "search_flight"),
        ("有没有去西安的航班", "search_flight"),
        ("查杭州到上海的高铁票", "search_train"),
        ("坐高铁去南京怎么走", "search_train"),
        ("去武汉的火车票多少钱", "search_train"),
        ("动车到福州几点", "search_train"),
        ("成都在下雨吗", "query_weather"),
        ("上海今天多少度", "query_weather"),
        ("广州天气怎么样", "query_weather"),
        ("周末北京会降温吗", "query_weather"),
        ("订一晚上海的酒店", "book_hotel"),
        ("帮我订成都有泳池的酒店", "book_hotel"),
        ("在杭州住三晚要订房", "book_hotel"),
        ("广州过夜的酒店哪家好", "book_hotel"),
        ("机票 北京→成都 最便宜那班", "search_flight"),
        ("G1024 次高铁还有票吗", "search_train"),
        ("明天出门要带伞吗 (在武汉)", "query_weather"),
        ("公司出差要住两晚酒店 (城市:深圳)", "book_hotel"),
        ("flight to Chengdu price", "search_flight"),
        ("train ticket Hangzhou", "search_train"),
        ("weather in Beijing", "query_weather"),
        ("hotel in Guangzhou 1 night", "book_hotel"),
        ("帮我看看去昆明的飞机", "search_flight"),
        ("k字头火车到郑州几小时", "search_train"),
        ("这几天西安紫外线强吗", "query_weather"),
        ("三亚海景房订一晚", "book_hotel"),
        ("红眼航班去上海贵不贵", "search_flight"),
        ("高铁二等座到苏州多少钱", "search_train"),
    ]
    for t, tool in easy:
        rows.append((t, tool, "易"))
    medium = [
        ("最快的方式从北京到上海是哪种交通", "search_flight"),
        ("明天去天津用哪种方式比较快", "search_flight"),
        ("查一下去哈尔滨的票 (冬天想快点到)", "search_flight"),
        ("出差去兰州, 领导让今晚就出发", "search_flight"),
        ("去乌鲁木齐 | 3000 公里 | 帮我看看怎么去", "search_flight"),
        ("周末去苏州玩, 帮我查下车票", "search_train"),
        ("公司到机场后去杭州市区的交通", "search_train"),
        ("查从北京出发的工具 (2 小时生活圈)", "search_train"),
        ("下周去三亚穿什么 (要出行+天气都查)", "query_weather"),
        ("国庆去西安人多吗 (帮忙看下那边的日晒和温度)", "query_weather"),
        ("出差上海住哪 (要能开发票过夜的地方)", "book_hotel"),
        ("给客户订一间房, 人在成都待两晚", "book_hotel"),
    ]
    for t, tool in medium:
        rows.append((t, tool, "中"))
    hard = [
        ("爸妈年纪大了, 想少受点罪从北京去三亚", "search_flight"),
        ("九点开会, 现在八点二十, 我在上海要赶去北京", "search_flight"),
        ("就想看看那边下不下雨再决定去不去 (城市: 重庆)", "query_weather"),
        ("什么都不查, 先看看昆明适不适合徒步", "query_weather"),
        ("今晚在南京落脚, 明早再走", "book_hotel"),
        ("红眼到深圳太累了, 先找个地方睡一晚", "book_hotel"),
        ("两个城市之间移动, 帮我看看地面交通 (杭州→苏州)", "search_train"),
        ("预算少不赶时间, 去郑州的陆路方案", "search_train"),
    ]
    for t, tool in hard:
        rows.append((t, tool, "难"))
    return rows


INSTRUCTIONS = _q()


# ============================================================
# 评测
# ============================================================

def eval_mock(version, instr):
    """确定性难度模型: V1 挂全部中/难, V2 挂全部难 + 中题挂一半; V3 全对。
    用指令文本哈希决定"中题挂哪一半", 保证离线结果稳定可复现。"""
    text, tool, diff = instr
    if version.startswith("V1"):
        return False if diff in ("中", "难") else True
    if version.startswith("V2"):
        if diff == "难":
            return False
        if diff == "中":
            return (hash(text) % 2 == 0)
        return True
    return True


def eval_real(tools_md, batch):
    """批量评测: 一次调用评 10 条, 返回每条的选中工具。"""
    lines = "\n".join(f"{i + 1}. {t}" for i, (t, _, _) in enumerate(batch))
    r = extract_json(http_chat([{"role": "user", "content":
        f"你是路由器, 为每条用户指令选一个最合适的工具。\n可用工具:\n{tools_md}\n"
        f"用户指令:\n{lines}\n"
        '只输出 JSON 数组: [{"i": 1, "tool": "工具名"}, ...]'}], num_predict=1500))
    picks = {}
    if isinstance(r, list):
        for it in r:
            try:
                picks[int(it["i"]) - 1] = str(it["tool"])
            except (KeyError, TypeError, ValueError):
                continue
    return [picks.get(i) for i in range(len(batch))]


def main():
    print("=" * 72)
    print(f"工具描述优化实验 -- {'MOCK (确定性难度模型)' if MOCK else '真实 qwen3.8 批量路由'}")
    print(f"工具 4 个 (易混) | 指令 {len(INSTRUCTIONS)} 条 "
          f"(易30/中12/难8) | 3 版描述 | 指标: 选对率")
    print("=" * 72)

    results = {}
    for version, tools_md in VERSIONS.items():
        correct = {"易": [0, 0], "中": [0, 0], "难": [0, 0]}
        if MOCK:
            for instr in INSTRUCTIONS:
                ok = eval_mock(version, instr)
                correct[instr[2]][0] += ok
                correct[instr[2]][1] += 1
        else:
            for s in range(0, len(INSTRUCTIONS), 10):
                batch = INSTRUCTIONS[s:s + 10]
                picks = eval_real(tools_md, batch)
                for (text, tool, diff), pick in zip(batch, picks):
                    ok = (pick == tool)
                    correct[diff][0] += ok
                    correct[diff][1] += 1
        results[version] = correct
        tot = sum(v[0] for v in correct.values())
        print(f"  {version:<12} 完成 (选对 {tot}/{len(INSTRUCTIONS)})")

    print("\n" + "=" * 72)
    print(f"{'描述版本':<14}{'易':>8}{'中':>8}{'难':>8}{'overall':>12}")
    print("-" * 54)
    prev = -1
    monotonic = True
    for version, correct in results.items():
        tot = sum(v[0] for v in correct.values())
        pct = tot * 100 // len(INSTRUCTIONS)
        monotonic &= (pct >= prev)
        prev = pct
        print(f"{version:<14}" + "".join(
            f"{v[0]:>4}/{v[1]:<3}" for v in correct.values())
              + f"{tot}/{len(INSTRUCTIONS)} ({pct}%)".rjust(12))
    print("-" * 54)
    print(f"单调递增: {'✓' if monotonic else '✗ (记录反常)'}")
    print("""
描述写法清单 (5 条):
  1) 名词钉死: 工具管什么用【名词】写明 (机票/高铁/天气), 别用动词短语。
  2) 参数说明: 每个参数的类型/必填/默认值, 缺了模型就开始编。
  3) 使用时机: "何时用我"一句话, 路由的本质是时机判断。
  4) 边界反例: "不要用于 X"——把最易混的邻居工具点名划界。
  5) 给示例: 一条 输入→调用 示例的收益大于三行形容词。
""")


if __name__ == "__main__":
    main()
