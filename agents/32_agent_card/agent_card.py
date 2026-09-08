"""
A2A / Agent Card — Agent 能力卡片、发现与互操作

每个 Agent 用一张 JSON Card 描述自己的能力 (skills/schema/端点)。
路由端只看卡片做发现与调度，**新增 Agent 零代码改动**。
对比: MCP 管 Agent 接工具, A2A 管 Agent 之间互发现互调用。

Demo 模式: 全离线, 用模拟卡片和确定性路由。
"""

import json, os, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_DIR = os.path.join(SCRIPT_DIR, "cards")

# Agent Card JSON 规范 (简化版, 对齐 Google A2A AgentCard)
AGENT_CARDS = [
    {"name": "translator", "description": "中英互译",
     "skills": [{"id": "translate", "input_schema": {"text": "str", "target_lang": "str"},
                 "output_schema": {"translated": "str"}}],
     "endpoint": "local://translator"},
    {"name": "weather", "description": "天气查询",
     "skills": [{"id": "get_weather", "input_schema": {"city": "str"},
                 "output_schema": {"temp": "str", "condition": "str"}}],
     "endpoint": "local://weather"},
    {"name": "math", "description": "数学计算",
     "skills": [{"id": "calc", "input_schema": {"expression": "str"},
                 "output_schema": {"result": "float"}}],
     "endpoint": "local://math"},
]

# 模拟 Agent 实现 (真实模式由 LLM 驱动)
def translator_run(skill_input):
    demos = {"hello world": "你好世界", "AI Agent": "AI 智能体"}
    text = skill_input.get("text", "") if isinstance(skill_input, dict) else str(skill_input)
    return {"translated": demos.get(text.lower(), f"[翻译] {text}")}

def weather_run(skill_input):
    return {"temp": "28°C", "condition": "晴"}

def math_run(skill_input):
    import math
    try:
        return {"result": eval(skill_input.get("expression", "0"))}
    except Exception:
        return {"result": 0}

AGENTS = {"translator": translator_run, "weather": weather_run, "math": math_run}


def discover_cards(skill_keyword=None):
    """从卡片注册目录发现 Agent, 可按关键词过滤。"""
    cards = AGENT_CARDS
    if skill_keyword:
        cards = [c for c in cards
                 if any(skill_keyword in s["id"] or skill_keyword in c["description"]
                        for s in c["skills"])]
    return cards


def route_and_call(skill_keyword, query=""):
    """发现 -> 选 Agent -> 调用。新增 Agent 零代码改动。"""
    cards = discover_cards(skill_keyword)
    if not cards:
        return None, "无匹配 Agent"
    card = cards[0]
    skill = card["skills"][0]
    agent_fn = AGENTS.get(card["name"])
    if not agent_fn:
        return None, f"Agent '{card['name']}' 未注册"
    return agent_fn(skill.get("input_schema", {})), card["name"]


def run():
    print("=" * 60)
    print("A2A / Agent Card — 发现与互操作")
    print("=" * 60)
    print(f"已注册 {len(AGENT_CARDS)} 个 Agent: {[c['name'] for c in AGENT_CARDS]}\n")

    print("==> 卡片发现")
    for c in discover_cards():
        print(f"  {c['name']:12s} skills={[s['id'] for s in c['skills']]}")

    print("\n==> 路由与调用")
    tests = [("翻译", "hello world"), ("天气", ""), ("数学", "")]
    for keyword, input_data in tests:
        card = discover_cards(keyword)
        if not card:
            print(f"  [{keyword}] 无匹配"); continue
        name = card[0]["name"]
        result, agent_name = route_and_call(keyword)
        print(f"  [{keyword}] -> {agent_name}: {result}")

    print("\n==> 新增 Agent 零改动演示")
    AGENT_CARDS.append({"name": "new_agent", "description": "新 Agent",
                        "skills": [{"id": "new_skill", "input_schema": {}, "output_schema": {}}],
                        "endpoint": "local://new"})
    print(f"  注册后: {[c['name'] for c in AGENT_CARDS]}")
    print("  路由端零改动——只要卡片注册就能被发现。")
    print("\n要点: A2A 管 Agent 间互发现 (卡片即接口), MCP 管 Agent 接工具;")


if __name__ == "__main__":
    run()
