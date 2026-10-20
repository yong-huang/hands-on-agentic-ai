"""
多智能体辩论与投票 — 三个专家 Agent 对同一架构决策正面对辩

单个 LLM 对争议问题的回答是"一碗水端平的综述"。辩论式多 Agent 让三个
不同立场的专家各自陈述、互相反驳，最后投票产生结论——用角色对立逼出
真实的权衡分析。

辩题（系列内真实存在的架构分歧）:
  "Agent 的工具调用应该用 Function Calling（协议级，项目 11）
   还是文本协议 ReAct（提示词级，项目 06）？"

三方: 架构师(倾向 FC) / 兼容性工程师(倾向 ReAct) / 求实审计师(中立偏成本)
流程: 第 1 轮各自立论 -> 第 2 轮互相反驳 -> 投票(可投给任何一方, 含理由)
      -> 主持人宣布多数派结论
Demo 模式: 预置全部发言与投票, 离线走完流程。
"""

import json
import os
import sys
import requests

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

DEBATE_TOPIC = ("Agent 的工具调用应该用 Function Calling（协议级，模型直接输出"
                "结构化 tool_calls）还是文本协议 ReAct（提示词约定 Thought/Action "
                "格式，正则解析）？")

AGENTS = [
    {"id": "architect", "name": "架构师", "bias": "你天然倾向标准化与协议化方案。"},
    {"id": "compat", "name": "兼容性工程师", "bias": "你天然关注模型兼容性与实现成本，倾向简单方案。"},
    {"id": "auditor", "name": "求实审计师", "bias": "你中立，只看成本、可靠性与团队现状的证据。"},
]

POSITION_PROMPT = """辩题: {topic}

你的角色: {name}。{bias}
请陈述你的立场与两条核心理由，限 120 字内，直接给结论。"""

REBUTTAL_PROMPT = """辩题: {topic}

你的角色: {name}。{bias}

上一轮各方的立场:
{transcript}

请针对性反驳与你对立的观点（限 120 字），可以修正自己的立场，但必须给结论。"""

VOTE_PROMPT = """辩题: {topic}

你的角色: {name}。{bias}

两轮辩论实录:
{transcript}

请投票。只输出 JSON: {{"vote": "FC 或 ReAct", "reason": "一句话理由"}}"""


def chat(messages, temperature=0.5):
    resp = requests.post(BASE_URL, json={
        "model": MODEL, "messages": messages, "stream": False, "think": False,
        "options": {"temperature": temperature, "num_predict": 300},
    }, timeout=180)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def speak(agent, prompt, temperature=0.5, **kw):
    return chat([{"role": "user", "content": prompt.format(
        topic=DEBATE_TOPIC, name=agent["name"], bias=agent["bias"], **kw)}], temperature)


def vote(agent, transcript):
    raw = chat([{"role": "user", "content": VOTE_PROMPT.format(
        topic=DEBATE_TOPIC, name=agent["name"], bias=agent["bias"],
        transcript=transcript)}], temperature=0.0)
    m = json_match = None
    import re
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"vote": "无效", "reason": raw[:60]}


def run_real():
    print("=" * 60)
    print(f"多智能体辩论 -- 真实模式 ({MODEL})")
    print(f"辩题: {DEBATE_TOPIC}")
    print("=" * 60)

    transcript = ""
    print("\n==> [round 1] 各自立论")
    positions = {}
    for agent in AGENTS:
        positions[agent["id"]] = speak(agent, POSITION_PROMPT)
        transcript += f"\n【{agent['name']}】{positions[agent['id']]}\n"
        print(f"\n  [{agent['name']}] {positions[agent['id']]}")

    print("\n==> [round 2] 互相反驳")
    for agent in AGENTS:
        rebuttal = speak(agent, REBUTTAL_PROMPT, transcript=transcript)
        transcript += f"\n【{agent['name']}·反驳】{rebuttal}\n"
        print(f"\n  [{agent['name']}] {rebuttal}")

    print("\n==> [vote] 投票")
    votes = []
    for agent in AGENTS:
        v = vote(agent, transcript)
        votes.append((agent["name"], v.get("vote", "?"), v.get("reason", "")))
        print(f"  [{agent['name']}] 投给 {v.get('vote')} —— {v.get('reason', '')}")

    tally = {}
    for _, v, _ in votes:
        tally[v] = tally.get(v, 0) + 1
    winner = max(tally, key=tally.get)
    print(f"\n==> 结论: {winner} 获胜 {tally} "
          f"(投票即共识机制——结论带全部辩论上下文, 可追溯)")


# ============================================================
# Demo 模式: 预置发言与投票 (离线)
# ============================================================

CANNED = {
    "round1": {
        "架构师": "我支持 Function Calling：协议级结构化输出免解析、参数有 "
                  "Schema 类型约束，还支持并行调用——文本协议在模型升级时最脆。",
        "兼容性工程师": "我支持 ReAct：不依赖模型支持 tools 字段，本地小模型和 "
                        "老模型都能跑；一个正则解析器可控可修。",
        "求实审计师": "中立看数据：FC 的解析失败率接近零，ReAct 的解析器要养 "
                      "兼容变体清单；团队应按模型支持度决定。"},
    "round2": {
        "架构师": "兼容性问题可以用模型升级解决，解析正确性问题却会随任务复杂度 "
                  "指数放大——Schema 约束不可替代。",
        "兼容性工程师": "团队现状是 30% 流量在老模型上，FC 等于放弃这部分；"
                        "ReAct 解析器已有完整测试覆盖。",
        "求实审计师": "反驳双方：FC 不是零成本（调试黑盒），ReAct 也不是零成本"
                      "（维护解析器）；应量化两条路的一次性投入。"},
    "votes": [
        ("架构师", "FC", "结构化保证可靠性"),
        ("兼容性工程师", "ReAct", "现状兼容优先"),
        ("求实审计师", "FC", "长期解析成本更低"),
    ],
}


def run_demo():
    print("=" * 60)
    print("多智能体辩论 -- Demo 模式（预置发言与投票, 离线）")
    print(f"辩题: {DEBATE_TOPIC}")
    print("=" * 60)

    for rnd in ("round1", "round2"):
        print(f"\n==> [{rnd}]")
        for name, speech in CANNED[rnd].items():
            print(f"\n  [{name}] {speech}")

    print("\n==> [vote] 投票")
    tally = {}
    for name, v, reason in CANNED["votes"]:
        tally[v] = tally.get(v, 0) + 1
        print(f"  [{name}] 投给 {v} —— {reason}")

    winner = max(tally, key=tally.get)
    print(f"\n==> 结论: {winner} 以 {tally[winner]} 票获胜 {tally}")
    print("      (真实模式: 全部发言与投票由 qwen3.8 依角色提示词生成)")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        print("Usage: python agent_debate.py [--demo]\n"
              "  --demo   : 离线演示辩论与投票\n"
              "  (无参数)  : 真实模式, 三专家两轮辩论 + 投票\n")
        run_real()
