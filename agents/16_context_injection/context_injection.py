"""
上下文构建与注入 — build_system_prompt

项目 01-15 的 system prompt 都是写死的一行字符串。从本篇进入第四阶段：
Agent 的 System Prompt 不该手写，而该**组装**——Identity（角色）、Memory（记忆）、
Workspace（工作区）、Tools（工具）、Rules（规则）五类上下文来源按序拼装成
最终的 System Prompt，并量化每部分的 token 占比。

核心概念:
- build_system_prompt(): 五段式组装器，各来源独立维护、按序拼接
- 占比报告: 组装即计量，为项目 18 的上下文压缩打基础
- 注入验证: 把组装产物发给模型，用"只有注入内容才能答对"的问题验证生效

与手写 prompt 的对比:
  手写 (01-15)                  组装 (本项目)
  ─────────────                 ─────────────
  一行字符串写死                 五类来源独立维护
  改角色要动 prompt              改 IDENTITY 配置即可
  不知道 prompt 有多大           每段字符数 / 估算 token / 占比
  无法验证模型是否"看到"          注入验证: 靠记忆才能答对的问题
"""

import os
import sys

BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

# ============================================================
# 五类上下文来源 —— 每类独立维护，组装时才汇合
# ============================================================

# 1) Identity: 角色定义（对应 Claude Code 的 IDENTITY.md）
IDENTITY = {
    "name": "小助",
    "role": "用户的个人助理 Agent",
    "tone": "简洁、友好，回答不超过三句话",
}

# 2) Memory: 跨会话记忆（对应 MEMORY.md；真实场景来自项目 17/19 的记忆系统）
MEMORY = """## 用户画像
- 姓名: 张三
- 饮食偏好: 喜欢吃火锅，不能吃辣
- 正在学习的技能: AI Agent 开发（已学到工具审批）

## 近期约定
- 用户希望被称呼为"张三同学"
- 每次对话结束前提醒用户休息"""

# 3) Workspace: 工作区快照（当前目录信息，生产环境会做剪裁与过滤）
def get_workspace_info(root=None):
    root = root or os.path.dirname(os.path.abspath(__file__))
    entries = sorted(os.listdir(root))
    files = [e for e in entries if os.path.isfile(os.path.join(root, e))]
    dirs = [e for e in entries if os.path.isdir(os.path.join(root, e))]
    lines = [f"- 工作目录: {root}"]
    if dirs:
        lines.append(f"- 子目录: {', '.join(dirs[:5])}")
    if files:
        lines.append(f"- 文件: {', '.join(files[:8])}")
    return "\n".join(lines)

# 4) Tools: 工具清单（生产场景由 Registry/MCP 动态生成，见项目 12/14）
TOOLS = [
    {"name": "get_weather", "description": "查询指定城市天气"},
    {"name": "calculator", "description": "安全计算器，输入数学表达式"},
    {"name": "read_memory", "description": "检索长期记忆库"},
]

def get_tools_info():
    return "\n".join(f"- {t['name']}: {t['description']}" for t in TOOLS)

# 5) Rules: 行为规则（对应规则文件；违反会有可观测的后果）
RULES = """- 始终用中文回答
- 回答前先检查 Memory 中的用户偏好
- 涉及数字时使用 calculator 工具，不要口算
- 不知道的事明确说不知道，不要编造"""


# ============================================================
# 组装器 —— 五段拼接 + 逐段计量
# ============================================================

def estimate_tokens(text):
    """粗估 token 数: CJK 字符按 1 字 1 token, 其余按 4 字符 1 token。
    仅为教学估算; 生产环境用 tiktoken / 模型自有 tokenizer。"""
    cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
    other = len(text) - cjk
    return cjk + other // 4


def build_system_prompt(identity, memory, workspace, tools, rules):
    """按 Identity -> Memory -> Workspace -> Tools -> Rules 的固定顺序组装。
    顺序即优先级: 模型对靠前的内容更敏感, 角色定义必须最靠前。"""
    sections = [
        ("Identity", f"你是 {identity['name']}，{identity['role']}。语气: {identity['tone']}。"),
        ("Memory", f"## 关于用户的长期记忆\n{memory}"),
        ("Workspace", f"## 当前工作区\n{workspace}"),
        ("Tools", f"## 可用工具\n{tools}"),
        ("Rules", f"## 行为规则\n{rules}"),
    ]
    parts, stats = [], []
    total_chars = sum(len(body) for _, body in sections) or 1
    for name, body in sections:
        parts.append(f"### {name}\n{body}")
        tokens = estimate_tokens(body)
        stats.append({"name": name, "chars": len(body),
                      "tokens": tokens, "pct": len(body) / total_chars * 100})
    return "\n\n".join(parts), stats


def print_report(stats, total_tokens):
    print("\n--- System Prompt 占比报告 ---")
    print(f"  {'段':<12}{'字符':>8}{'~token':>8}{'占比':>8}   条形")
    for s in stats:
        bar = "█" * max(1, round(s["pct"] / 4))
        print(f"  {s['name']:<12}{s['chars']:>8}{s['tokens']:>8}{s['pct']:>7.1f}%   {bar}")
    print(f"  {'合计':<12}{sum(s['chars'] for s in stats):>8}{total_tokens:>8}")


# ============================================================
# 演示: 三阶段演进（--demo, 离线）
# ============================================================

def run_demo():
    print("=" * 60)
    print("上下文构建与注入 -- Demo 模式（三阶段演进）")
    print("=" * 60)

    workspace = get_workspace_info()

    print("\n[阶段 1] 只有 Identity —— 项目 01-15 的状态")
    prompt, stats = build_system_prompt(IDENTITY, "", "", "", "")
    print_report(stats, estimate_tokens(prompt))
    print(prompt)

    print("\n[阶段 2] + Memory + Workspace —— Agent 开始'了解'你")
    prompt, stats = build_system_prompt(IDENTITY, MEMORY, workspace, "", "")
    print_report(stats, estimate_tokens(prompt))

    print("\n[阶段 3] + Tools + Rules —— 完整形态")
    prompt, stats = build_system_prompt(IDENTITY, MEMORY, workspace, get_tools_info(), RULES)
    print_report(stats, estimate_tokens(prompt))

    print("\n--- 最终 System Prompt 预览（前 14 行）---")
    for line in prompt.splitlines()[:14]:
        print("  " + line)
    print("  ...")

    print("\n要点: 改任何一段只需改对应来源，组装器与占比报告自动跟随。")
    print("      真实模式将验证: 模型确实'读到'了注入的 Memory 与 Rules。")


# ============================================================
# 真实模式: 组装后发给 qwen3.8, 验证注入生效
# ============================================================

def call_llm(system_prompt, user_msg):
    import requests
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "options": {"temperature": 0.3, "num_predict": 300},
        "stream": False,
        "think": False,
    }
    resp = requests.post(BASE_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def run_real():
    print("=" * 60)
    print(f"上下文构建与注入 -- 真实模式 ({MODEL})")
    print("=" * 60)

    prompt, stats = build_system_prompt(
        IDENTITY, MEMORY, get_workspace_info(), get_tools_info(), RULES)
    print_report(stats, estimate_tokens(prompt))

    # 验证 1: 只有注入 Memory 才能答对 -> 证明记忆注入生效
    print("\n[验证 1] 用户画像（答案只在注入的 Memory 里）")
    print("  Q: 我叫什么名字？我喜欢吃什么？")
    print(f"  A: {call_llm(prompt, '我叫什么名字？我喜欢吃什么？')}")

    # 验证 2: 规则遵循（回答前先看记忆 -> 称呼"张三同学"）
    print("\n[验证 2] 规则遵循（称呼约定写注入的 Memory 里）")
    print("  Q: 打个招呼吧")
    print(f"  A: {call_llm(prompt, '打个招呼吧')}")

    # 对照组: 不注入 Memory 的裸 Identity prompt
    bare, _ = build_system_prompt(IDENTITY, "", "", "", "")
    print("\n[对照组] 同样的问题, 只给裸 Identity")
    print(f"  A: {call_llm(bare, '我叫什么名字？我喜欢吃什么？')}")
    print("\n对照组答不出 -> 差异全部来自注入的上下文, 这就是'注入生效'的证据。")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        print("Usage: python context_injection.py [--demo]")
        print("  --demo   : 离线演示三阶段组装与占比（无需 Ollama）")
        print("  (无参数)  : 真实模式, 组装 System Prompt 并注入 qwen3.8 验证\n")
        run_real()
