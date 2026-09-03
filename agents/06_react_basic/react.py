"""
ReAct 模式基础实现 — 手动实现 Thought → Action → Observation 循环

ReAct (Reasoning + Acting) 是 Agent 的核心模式：
模型交替进行「推理」和「行动」，通过工具获取外部信息来辅助决策。

参考论文: Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (2023)

ReAct 循环步骤:
1. Thought  — 模型思考下一步该做什么
2. Action   — 模型选择一个工具并给出输入
3. Observation — 执行工具，将结果返回给模型
4. 重复 1-3 直到模型输出 Final Answer
"""

import requests
import json
import re
import sys

# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}

# ============================================================
# 工具定义 — 模拟简单的外部工具
# 实际应用中可替换为搜索 API、数据库查询、代码执行等
# ============================================================

def tool_calculator(expression: str) -> str:
    """安全计算器：仅支持加减乘除和幂运算"""
    # 只允许数字、运算符、括号、空格和小数点
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)\^]+$', expression):
        return f"错误: 不合法的表达式 '{expression}'"
    try:
        # 将 ^ 替换为 Python 的 ** 幂运算
        expr = expression.replace('^', '**')
        result = eval(expr)
        return str(result)
    except ZeroDivisionError:
        return "错误: 除以零"
    except Exception:
        return f"错误: 无法计算 '{expression}'"


def tool_get_population(city: str) -> str:
    """模拟城市人口查询（使用小型内置数据集）"""
    # 生产环境应替换为数据库或 API 查询
    data = {
        "北京": "2189万人 (2023)",
        "上海": "2487万人 (2023)",
        "广州": "1881万人 (2023)",
        "深圳": "1768万人 (2023)",
        "成都": "2126万人 (2023)",
        "杭州": "1237万人 (2023)",
        "武汉": "1373万人 (2023)",
        "南京": "949万人 (2023)",
    }
    # 支持模糊匹配
    for key, val in data.items():
        if city in key or key in city:
            return f"{key}的人口: {val}"
    return f"未找到城市 '{city}' 的数据"


def tool_lookup_fact(keyword: str) -> str:
    """模拟知识检索"""
    facts = {
        "python": "Python 由 Guido van Rossum 于 1991 年发布，当前最新稳定版为 3.12。",
        "gil": "GIL (Global Interpreter Lock) 是 CPython 的全局解释器锁，限制同一时刻只有一个线程执行 Python 字节码。",
        "react": "ReAct (Reasoning + Acting) 是 2023 年由 Yao et al. 提出的 Agent 框架，交替进行推理和工具调用。",
        "langchain": "LangChain 是一个 LLM 应用开发框架，提供链式调用、工具集成、RAG 等功能。",
        "rag": "RAG (Retrieval-Augmented Generation) 先从知识库检索相关文档，再让 LLM 基于文档生成回答。",
    }
    keyword_lower = keyword.lower()
    for key, val in facts.items():
        if key in keyword_lower or keyword_lower in key:
            return val
    return f"未找到与 '{keyword}' 相关的事实。"


# 工具注册表
TOOLS = {
    "Calculator": tool_calculator,
    "GetPopulation": tool_get_population,
    "LookupFact": tool_lookup_fact,
}

# ============================================================
# ReAct System Prompt — 定义输出格式和可用工具
# ============================================================

SYSTEM_PROMPT = """你是一个智能助手，通过推理和工具使用来回答问题。

你可以使用以下工具:
- Calculator(expression): 计算数学表达式，如 "2 + 3 * 4", "2^10"
- GetPopulation(city): 查询中国主要城市的人口
- LookupFact(keyword): 查询知识库中的事实信息

请严格按以下格式输出:

Thought: 你的推理过程
Action: 工具名称
Action Input: 工具输入参数

当你有足够信息给出最终答案时，使用以下格式:
Thought: 你的推理总结
Answer: 最终答案

重要: 每次只输出一个 Thought + (Action + Action Input) 或 Thought + Answer。
不要跳过 Thought。"""


# ============================================================
# ReAct 输出解析器 — 逐行状态机
# ============================================================

# ReAct 的本质是一个**有限状态机**，每轮迭代包含三个阶段：

#         ┌──────────────────────────────────────────┐
#         │                                          │
#         ▼                                          │
#    ┌─────────┐    ┌─────────┐    ┌─────────────┐  │
#    │ Thought │───▶│ Action  │───▶│ Observation  │──┘
#    │  (推理)  │    │ (工具)   │    │  (工具结果)  │
#    └─────────┘    └─────────┘    └─────────────┘
#         │
#         ▼ (信息足够时)
#    ┌─────────┐
#    │ Answer  │
#    │ (最终答案)│
#    └─────────┘

# - **Thought**: 模型分析当前信息，决定下一步该做什么
# - **Action**: 模型选择一个工具并指定输入参数
# - **Observation**: 系统执行工具，将结果反馈给模型
# - **Answer**: 模型认为信息充分，输出最终答案（循环终止）

# 与 CoT 的关系

# | 维度     | Chain-of-Thought | ReAct             |
# | :------- | :--------------- | :---------------- |
# | 推理     | 纯内部推理       | 推理 + 外部工具   |
# | 信息来源 | 仅依赖模型参数   | 参数 + 工具返回值 |
# | 输出     | 一次性生成       | 多轮迭代          |
# | 准确性   | 受幻觉影响       | 工具结果可验证    |
# | 延迟     | 单次请求         | 多次请求          |

# ReAct 可以看作 CoT 的"增强版"——当模型的内部知识不足以回答问题时（如实时数据、精确计算），通过工具调用获取可靠信息。
# 项目 03 的 CoT 只需要模型"自己想"，而 ReAct 让模型"边想边查"。

def parse_react_output(text: str) -> dict:
    """解析模型的 ReAct 格式输出"""
    text = text.strip()
    # 清理 qwen3.8 think 标签
    text = re.sub(r'<think.*?</think\s*>', '', text, flags=re.DOTALL)
    text = re.sub(r'</?think[^>]*>', '', text)
    text = text.strip()

    result = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        thought_match = re.match(r'^(?:Thought|Thinking(?:\s*Process)?)\s*[:：]\s*(.+)$', line, re.IGNORECASE)
        if thought_match:
            result['thought'] = thought_match.group(1).strip(); continue
        action_match = re.match(r'^Action:\s*(.+)$', line, re.IGNORECASE)
        if action_match:
            result['action'] = action_match.group(1).strip(); continue
        input_match = re.match(r'^Action Input:\s*(.+)$', line, re.IGNORECASE)
        if input_match:
            result['action_input'] = input_match.group(1).strip(); continue
        answer_match = re.match(r'^Answer:\s*(.+)$', line, re.IGNORECASE)
        if answer_match:
            result['answer'] = answer_match.group(1).strip(); continue
    return result if result else None


def _extract_action_input(raw: str) -> str:
    """清理 Action Input：JSON 对象自动提取值"""
    raw = raw.strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, str): return v
            for v in obj.values(): return str(v)
        elif isinstance(obj, str): return obj
    except (json.JSONDecodeError, ValueError): pass
    # 处理 key=value 格式 (如 "expression=2126+1768")
    if '=' in raw and not raw.startswith('{'):
        parts = raw.split('=', 1)
        return parts[-1].strip()
    if raw.startswith('"') and raw.endswith('"'): return raw[1:-1]
    return raw


def execute_tool(action: str, action_input: str) -> str:
    """执行工具调用并返回结果"""
    tool_fn = TOOLS.get(action)
    if tool_fn:
        return tool_fn(action_input)
    return f"错误: 未知工具 '{action}'。可用工具: {', '.join(TOOLS.keys())}"


# ============================================================
# ReAct Agent — 核心循环
# ============================================================

class ReActAgent:
    """ReAct 模式 Agent：Thought → Action → Observation → ... → Answer"""

    def __init__(self, max_steps=6, temperature=0.3):
        self.max_steps = max_steps
        self.temperature = temperature
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.trace = []  # 记录每一步的完整轨迹

    def call_llm(self, user_message: str) -> str:
        """调用 Ollama API"""
        self.messages.append({"role": "user", "content": user_message})

        payload = {
            "model": MODEL,
            "messages": self.messages,
            "options": {
                "temperature": self.temperature,
                "num_predict": 1024
            },
            "stream": False
        }

        try:
            response = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            msg = data.get("message", {})
            thinking = msg.get("thinking", "")
            content = msg.get("content", "")
            if not content or len(content.strip()) < 5:
                content = thinking if thinking else None

            self.messages.append({"role": "assistant", "content": content})
            return content
        except requests.exceptions.RequestException as e:
            return f"API 请求失败: {e}"

    def step(self, model_output: str) -> dict:
        """解析模型输出，如果需要执行工具则执行"""
        parsed = parse_react_output(model_output)

        if parsed is None:
            return {"type": "error", "message": "无法解析模型输出"}

        self.trace.append(parsed)
        thought = parsed.get("thought", "")

        # 如果模型输出了 Answer，循环结束
        if "answer" in parsed:
            return {"type": "answer", "thought": thought, "answer": parsed["answer"]}

        # 如果模型输出了 Action，执行工具
        if "action" in parsed:
            action = parsed["action"]
            action_input = _extract_action_input(parsed.get("action_input", ""))
            observation = execute_tool(action, action_input)
            return {
                "type": "action",
                "thought": thought,
                "action": action,
                "action_input": action_input,
                "observation": observation,
            }

        return {"type": "error", "message": "格式不完整，缺少 Action 或 Answer"}

    def run(self, question: str) -> str:
        """运行完整的 ReAct 循环"""
        print(f"{'='*60}")
        print(f"问题: {question}")
        print(f"{'='*60}")

        # 第一步：发送用户问题
        output = self.call_llm(question)

        # 进入 Thought → Action → Observation 循环
        for i in range(self.max_steps):
            print(f"\n--- 步骤 {i+1}/{self.max_steps} ---")
            print(f"模型输出:\n{output}")

            result = self.step(output)

            if result["type"] == "answer":
                print(f"\n{'='*60}")
                print(f"最终答案: {result['answer']}")
                print(f"{'='*60}")

                # 如果有answer，这里就直接返回了，不会走到`print(f"\n已达到最大步数 {self.max_steps}，强制停止。")`
                return result["answer"]

            if result["type"] == "action":
                print(f"\n>> Thought: {result['thought']}")
                print(f">> Action: {result['action']}({result['action_input']})")
                print(f">> Observation: {result['observation']}")

                # 将 Observation 作为新的用户消息发给模型
                feedback = f"Observation: {result['observation']}"
                output = self.call_llm(feedback)

            elif result["type"] == "error":
                print(f"\n错误: {result['message']}")
                # 将错误反馈给模型让它重试
                output = self.call_llm(f"错误: {result['message']}。请按格式输出 Thought + Action/Answer。")

        print(f"\n已达到最大步数 {self.max_steps}，强制停止。")
        print("总结:")
        for i, step in enumerate(self.trace):
            print(f"  步骤 {i+1}: Thought={step.get('thought', 'N/A')[:50]}...")
        return None


# ============================================================
# Demo 模式 — 使用预定义的模型回复，无需 Ollama
# ============================================================

DEMO_RESPONSES = [
    # 问题: "成都和深圳的人口加起来是多少？"
    [
        "Thought: 我需要先查询成都和深圳各自的人口数据\nAction: GetPopulation\nAction Input: 成都",
        "Thought: 已经获取了成都的人口，现在查询深圳\nAction: GetPopulation\nAction Input: 深圳",
        "Thought: 现在有了两个城市的人口数据：成都2126万人，深圳1768万人。需要把它们加起来。\nAction: Calculator\nAction Input: 2126 + 1768",
        "Thought: 计算结果是3894万人，这就是最终答案。\nAnswer: 成都和深圳的人口加起来是3894万人（成都2126万 + 深圳1768万，2023年数据）。",
    ],
    # 问题: "Python 的 GIL 是什么？"
    [
        "Thought: 这是一个关于 Python 的知识性问题，我可以在知识库中搜索。\nAction: LookupFact\nAction Input: gil",
        "Thought: 知识库返回了 GIL 的定义，已经足够回答用户的问题。\nAnswer: GIL (Global Interpreter Lock) 是 CPython 的全局解释器锁，限制同一时刻只有一个线程执行 Python 字节码。",
    ],
]


def run_demo():
    """使用模拟数据运行 Demo，无需连接 Ollama"""
    print("=" * 60)
    print("ReAct Agent — Demo 模式（无需 Ollama）")
    print("=" * 60)

    questions = [
        "成都和深圳的人口加起来是多少？",
        "Python 的 GIL 是什么？",
    ]

    for idx, question in enumerate(questions):
        print(f"\n{'#'*60}")
        print(f"示例 {idx+1}: {question}")
        print(f"{'#'*60}")

        responses = DEMO_RESPONSES[idx]
        trace = []

        for i, model_output in enumerate(responses):
            print(f"\n--- 步骤 {i+1}/{len(responses)} ---")
            print(f"模型输出:\n{model_output}")

            parsed = parse_react_output(model_output)
            trace.append(parsed)

            if parsed and "answer" in parsed:
                print(f"\n{'='*60}")
                print(f"最终答案: {parsed['answer']}")
                print(f"{'='*60}")
                break

            if parsed and "action" in parsed:
                action = parsed["action"]
                action_input = parsed.get("action_input", "")
                observation = execute_tool(action, action_input)
                print(f"\n>> Thought: {parsed.get('thought', '')}")
                print(f">> Action: {action}({action_input})")
                print(f">> Observation: {observation}")


# ============================================================
# 主入口
# ============================================================

def main():
    if "--demo" in sys.argv:
        run_demo()
        return

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "成都和深圳的人口加起来是多少？"

    print(f"ReAct Agent")
    print(f"模型: {MODEL}")
    print(f"最大步数: 6\n")

    agent = ReActAgent(max_steps=6, temperature=0.3)
    agent.run(question)


if __name__ == "__main__":
    main()
