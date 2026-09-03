"""
Agent Loop 完整实现 — 多步骤任务自主完成

在项目 06 的 ReAct 基础上，本项目增加了生产级 Agent Loop 的关键机制：
- 最大步数限制（max_steps）：防止无限循环
- 任务完成判断：Agent 自主决定何时停止
- 中间结果累积（scratchpad）：跨步骤保留工具返回值
- 事件流捕获（EventStream）：记录每一步的完整轨迹，用于可视化和调试

Agent Loop 的生命周期:
  Task → [Thought → Action → Observation] × N → Final Answer
                                            或
  Task → [Thought → Action → Observation] × max_steps → Force Stop
"""

import requests
import json
import re
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# 配置信息 - 本地 Ollama
BASE_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.8:latest"

HEADERS = {
    "Content-Type": "application/json"
}


# ============================================================
# 事件类型与事件流
# ============================================================

class EventType(Enum):
    THINK = "think"
    ACTION = "action"
    OBSERVATION = "observation"
    ANSWER = "answer"
    ERROR = "error"
    MAX_STEPS = "max_steps"


@dataclass
class Event:
    """Agent Loop 中的单步事件，用于记录和可视化"""
    step: int
    event_type: EventType
    content: str
    tool: str = ""
    tool_input: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentResult:
    """Agent 执行结果"""
    answer: Optional[str]
    steps: int
    events: list
    success: bool
    reason: str  # 停止原因: "completed" / "max_steps" / "error"


# ============================================================
# 工具定义
# ============================================================

def tool_calculator(expression: str) -> str:
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)\^]+$', expression):
        return f"错误: 不合法的表达式 '{expression}'"
    try:
        return str(eval(expression.replace('^', '**')))
    except ZeroDivisionError:
        return "错误: 除以零"
    except Exception:
        return f"错误: 无法计算 '{expression}'"


def tool_get_population(city: str) -> str:
    data = {
        "北京": "2189", "上海": "2487", "广州": "1881", "深圳": "1768",
        "成都": "2126", "杭州": "1237", "武汉": "1373", "南京": "949",
    }
    for key, val in data.items():
        if city in key or key in city:
            return f"{key}: {val}万人 (2023)"
    return f"未找到城市 '{city}' 的数据"


def tool_get_gdp(city: str) -> str:
    """查询城市 GDP"""
    data = {
        "北京": "43760", "上海": "47218", "广州": "30355", "深圳": "34606",
        "成都": "22074", "杭州": "20059", "武汉": "20011", "南京": "17421",
    }
    for key, val in data.items():
        if city in key or key in city:
            return f"{key}: {val}亿元 (2023)"
    return f"未找到城市 '{city}' 的数据"


def tool_lookup_fact(keyword: str) -> str:
    facts = {
        "python": "Python 由 Guido van Rossum 于 1991 年发布。",
        "gil": "GIL 限制同一时刻只有一个线程执行 Python 字节码。",
        "rag": "RAG 先检索文档再让 LLM 基于文档生成回答。",
        "react": "ReAct 交替进行推理和工具调用。",
    }
    for key, val in facts.items():
        if key in keyword.lower() or keyword.lower() in key:
            return val
    return f"未找到与 '{keyword}' 相关的事实。"


TOOLS = {
    "Calculator": tool_calculator,
    "GetPopulation": tool_get_population,
    "GetGDP": tool_get_gdp,
    "LookupFact": tool_lookup_fact,
}

TOOLS_DESC = {
    "Calculator": "计算数学表达式，如 '2 + 3 * 4', '2^10'",
    "GetPopulation": "查询中国主要城市的人口（万人）",
    "GetGDP": "查询中国主要城市的 GDP（亿元）",
    "LookupFact": "查询知识库中的事实信息",
}


# ============================================================
# System Prompt — 带完成判断指令
# ============================================================

SYSTEM_PROMPT = """你是一个能自主完成多步骤任务的智能助手。

可用工具:
{tools}

严格输出格式（每行一个字段，不要输出多余内容）:
Thought: 你的推理过程
Action: 工具名称
Action Input: 工具输入参数

收集到足够信息后:
Thought: 总结已有信息
Answer: 最终答案

【关键规则 — 必须严格遵守】
1. 需要实时数据或精确数值（如 GDP、人口、计算）时，使用工具获取；常识性问题可直接 Answer
2. 每一步只输出一组 Thought + Action/Answer，不要输出多组
3. 收到 Observation 后，基于 Observation 中的数据决定下一步
4. 数据足够时立即输出 Answer，不要多余的工具调用
5. Answer 必须简洁完整"""


# ============================================================
# ReAct 输出解析器
# ============================================================

def parse_react_output(text: str) -> dict:
    result = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # 不同模型的返回结构不同且随版本漂移，解析需做多变体兼容与回退

        # Thought — 兼容多种变体: Thought: / Thinking Process: / Thinking:
        m = re.match(r'^(?:Thought|Thinking(?:\s*Process)?)\s*[:：]\s*(.+)$', line, re.IGNORECASE)
        if m:
            result['thought'] = m.group(1).strip()
            continue
        m = re.match(r'^Action:\s*(.+)$', line, re.IGNORECASE)
        if m:
            result['action'] = m.group(1).strip()
            continue
        m = re.match(r'^Action Input:\s*(.+)$', line, re.IGNORECASE)
        if m:
            result['action_input'] = m.group(1).strip()
            continue
        m = re.match(r'^Answer:\s*(.+)$', line, re.IGNORECASE)
        if m:
            result['answer'] = m.group(1).strip()
            continue
    return result if result else None


def extract_action_input(raw: str) -> str:
    """清理 Action Input：如果模型传了 JSON 对象，自动提取值。"""
    raw = raw.strip()
    # 尝试解析 JSON，提取第一个字符串值
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            # {"city": "上海", ...} → "上海"
            for v in obj.values():
                if isinstance(v, str):
                    return v
            # {"expression": "47218/2487"} → "47218/2487"
            for v in obj.values():
                return str(v)
        elif isinstance(obj, str):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    # 移除可能的引号包裹
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    return raw


# ============================================================
# Agent Loop — 核心实现
# ============================================================

class AgentLoop:
    """
    完整的 Agent 推理循环，在 ReAct 基础上增加：
    - 事件流记录（EventStream）
    - 中间结果缓存（scratchpad）
    - 结构化结果返回
    """

    def __init__(self, max_steps=8, temperature=0.3):
        self.max_steps = max_steps
        self.temperature = temperature
        self.events = []
        self.scratchpad = {}  # 缓存工具返回的关键数据

    def _emit(self, event_type: EventType, content: str,
              tool: str = "", tool_input: str = ""):
        """记录一个事件到事件流"""
        self.events.append(Event(
            step=len([e for e in self.events if e.event_type in
                      (EventType.THINK, EventType.ACTION, EventType.OBSERVATION, EventType.ANSWER)]),
            event_type=event_type,
            content=content,
            tool=tool,
            tool_input=tool_input,
        ))

    def _call_llm(self, messages: list) -> str:
        """调用 Ollama API，处理 qwen3.8 thinking 模式"""
        payload = {
            "model": MODEL,
            "messages": messages,
            "options": {
                "temperature": self.temperature,
                "num_predict": 1024
            },
            "stream": False
        }
        try:
            resp = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)
            resp.raise_for_status()
            msg = data = resp.json().get("message", {})

            # qwen3.8 thinking 模式: thinking 在单独字段
            # content 是正式输出，thinking 是内部推理
            thinking = msg.get("thinking", "")
            content = msg.get("content", "")

            # 如果 content 为空但 thinking 有内容，用 thinking
            if not content or len(content.strip()) < 5:
                if thinking:
                    content = thinking
                else:
                    return None

            return content
        except requests.exceptions.RequestException as e:
            return None

    def _execute_tool(self, action: str, action_input: str) -> str:
        """执行工具并缓存结果"""
        tool_fn = TOOLS.get(action)
        if not tool_fn:
            return f"错误: 未知工具 '{action}'"
        result = tool_fn(action_input)
        # 缓存到 scratchpad
        self.scratchpad[action] = self.scratchpad.get(action, {})
        self.scratchpad[action][action_input] = result
        return result

    def _clean_response(self, text: str) -> str:
        """清理模型输出：移除 qwen3.8 think 标签等干扰内容"""
        if not text:
            return text
        text = re.sub(r'<think.*?</think\s*>', '', text, flags=re.DOTALL)
        text = re.sub(r'</?think[^>]*>', '', text)
        return text.strip()

    def _scratchpad_summary(self) -> str:
        """生成 scratchpad 摘要，帮助模型了解已获取的数据"""
        if not self.scratchpad:
            return "尚未获取任何数据。"
        parts = []
        for tool, calls in self.scratchpad.items():
            for inp, result in calls.items():
                parts.append(f"{tool}({inp}) → {result}")
        return "已获取: " + "; ".join(parts)

    def run(self, question: str) -> AgentResult:
        """
        执行完整的 Agent Loop。

        生命周期:
        1. 初始化消息列表（system prompt + user question）
        2. 循环: 调用 LLM → 解析输出 → 执行工具/提取答案
        3. 终止条件: Answer 输出 / 达到 max_steps / API 错误
        4. 返回 AgentResult（含事件流）
        """
        # 构造 system prompt（包含工具描述）
        tools_desc = "\n".join(
            f"- {name}({desc}): {TOOLS_DESC[name]}"
            for name, desc in TOOLS_DESC.items()
        )
        system = SYSTEM_PROMPT.format(tools=tools_desc)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]

        print(f"{'='*60}")
        print(f"任务: {question}")
        print(f"最大步数: {self.max_steps}")
        print(f"{'='*60}")

        model_output = self._call_llm(messages)
        if model_output is None:
            self._emit(EventType.ERROR, "API 请求失败")
            return AgentResult(None, 0, self.events, False, "API 错误")

        # 教学实现：催促文案直接硬编码；生产环境应做成可配置的交互策略

        tools_called = 0  # 追踪是否已调用工具

        for step_i in range(self.max_steps):
            messages.append({"role": "assistant", "content": model_output})

            clean_output = self._clean_response(model_output)
            parsed = parse_react_output(clean_output)
            if parsed is None:
                self._emit(EventType.ERROR, "无法解析模型输出")
                print(f"[步骤 {step_i+1}] ⚠ 解析失败，模型输出:\n  {model_output[:300]}")
                messages.append({"role": "user",
                                 "content": f"错误: 无法解析。{self._scratchpad_summary()}\n请严格按格式输出:\nThought: ...\nAction: 工具名\nAction Input: 参数"})
                model_output = self._call_llm(messages)
                if model_output is None:
                    break
                continue

            thought = parsed.get("thought", "")

            # ---- 终止: Answer ----
            if "answer" in parsed:
                answer = parsed["answer"]

                # 校验: Answer 不完整（太短）→ 要求补充
                if len(answer) < 10:
                    self._emit(EventType.THINK, thought)
                    self._emit(EventType.ERROR, "答案不完整，要求补充")
                    print(f"\n[步骤 {step_i+1}] Thought: {thought}")
                    print(f"[步骤 {step_i+1}] ⚠ Answer 不完整，要求补充完整答案")
                    messages.append({"role": "user",
                                     "content": f"你的答案太简短。请给出完整的答案。"})
                    model_output = self._call_llm(messages)
                    if model_output is None:
                        break
                    continue

                self._emit(EventType.THINK, thought)
                self._emit(EventType.ANSWER, answer)
                print(f"\n[步骤 {step_i+1}] Thought: {thought}")
                print(f"[步骤 {step_i+1}] Answer: {answer}")
                print(f"\n{'='*60}")
                print(f"完成 — 共 {step_i+1} 步（调用 {tools_called} 次工具）")
                print(f"{'='*60}")
                return AgentResult(answer, step_i + 1, self.events, True, "completed")

            # ---- Action → Observation ----
            if "action" in parsed:
                action = parsed["action"]
                action_input = extract_action_input(parsed.get("action_input", ""))
                self._emit(EventType.THINK, thought)
                self._emit(EventType.ACTION, f"{action}({action_input})",
                           tool=action, tool_input=action_input)

                observation = self._execute_tool(action, action_input)
                self._emit(EventType.OBSERVATION, observation)
                tools_called += 1

                print(f"\n[步骤 {step_i+1}] Thought: {thought}")
                print(f"[步骤 {step_i+1}] Action: {action}({action_input})")
                print(f"[步骤 {step_i+1}] Observation: {observation}")

                # 如果工具返回错误且已有足够数据，催促直接 Answer
                if "错误" in observation and tools_called >= 3:
                    hint = f"工具出错，已有数据。{self._scratchpad_summary()}\n请直接输出 Answer 给出最终答案。"
                    messages.append({"role": "user", "content": hint})
                else:
                    messages.append({"role": "user",
                                     "content": f"Observation: {observation}\n"
                                                  f"(已调用 {tools_called} 次工具。如果数据足够，请直接输出 Answer)"})
                model_output = self._call_llm(messages)
                if model_output is None:
                    self._emit(EventType.ERROR, "API 请求失败")
                    break
                continue

            # ---- 格式不完整 ----
            self._emit(EventType.ERROR, "格式不完整")
            messages.append({"role": "user",
                             "content": f"错误: 格式不完整。{self._scratchpad_summary()}\n请输出 Thought + Action/Answer。"})
            model_output = self._call_llm(messages)
            if model_output is None:
                break

        # ---- 达到最大步数 ----
        self._emit(EventType.MAX_STEPS, f"已达到最大步数 {self.max_steps}")
        print(f"\n已达到最大步数 {self.max_steps}，强制停止。")
        return AgentResult(None, self.max_steps, self.events, False, "max_steps")


# ============================================================
# Demo 模式
# ============================================================

def run_demo():
    """使用模拟数据演示 Agent Loop 的三种终止场景"""
    print("=" * 60)
    print("Agent Loop — Demo 模式（无需 Ollama）")
    print("=" * 60)

    # ---- 场景 1: 正常完成 ----
    print(f"\n{'#'*60}")
    print("场景 1: 正常完成（多步工具调用）")
    print("任务: 上海的人均 GDP 大约是多少？")
    print(f"{'#'*60}")

    agent = AgentLoop(max_steps=8)
    # 模拟步骤: GetPopulation(上海) → GetGDP(上海) → Calculator(GDP/人口) → Answer
    simulated = [
        ("Thought: 需要查询上海的人口和 GDP 数据\nAction: GetPopulation\nAction Input: 上海",
         "上海: 2487万人 (2023)"),
        ("Thought: 已获取人口数据，现在查询 GDP\nAction: GetGDP\nAction Input: 上海",
         "上海: 47218亿元 (2023)"),
        ("Thought: 有了 GDP(47218亿元) 和人口(2487万人)，计算人均 GDP\nAction: Calculator\nAction Input: 47218 / 2487",
         "18.987337715922476"),
        ("Thought: 人均 GDP 约 18.99 万元，可以给出答案\nAnswer: 上海的人均 GDP 约为 18.99 万元（GDP 47218亿元 / 人口 2487万人，2023 年数据）。",
         None),
    ]

    for i, (model_out, obs) in enumerate(simulated):
        agent.events.append(Event(i, EventType.THINK,
                                  parse_react_output(model_out).get("thought", "")))
        if obs is None:
            # Answer
            agent.events.append(Event(i, EventType.ANSWER,
                                      parse_react_output(model_out)["answer"]))
            print(f"  [{i+1}] {parse_react_output(model_out).get('thought', '')}")
            print(f"  [{i+1}] Answer: {parse_react_output(model_out)['answer']}")
            break
        parsed = parse_react_output(model_out)
        agent.events.append(Event(i, EventType.ACTION,
                                  f"{parsed['action']}({parsed['action_input']})",
                                  tool=parsed["action"],
                                  tool_input=parsed.get("action_input", "")))
        agent.events.append(Event(i, EventType.OBSERVATION, obs))
        print(f"  [{i+1}] Thought: {parsed.get('thought', '')}")
        print(f"  [{i+1}] Action: {parsed['action']}({parsed['action_input']})")
        print(f"  [{i+1}] Observation: {obs}")

    print(f"\n  结果: 完成 — 共 {len(simulated)} 步")

    # ---- 场景 2: 快速完成 ----
    print(f"\n{'#'*60}")
    print("场景 2: 快速完成（1 步内回答）")
    print("任务: Python 是什么语言？")
    print(f"{'#'*60}")

    agent2 = AgentLoop(max_steps=8)
    agent2.events.append(Event(0, EventType.THINK, "这是常识性问题，直接回答"))
    agent2.events.append(Event(0, EventType.ANSWER, "Python 是一种高级通用编程语言，由 Guido van Rossum 于 1991 年发布。"))
    print("  [1] Thought: 这是常识性问题，直接回答")
    print("  [1] Answer: Python 是一种高级通用编程语言...")
    print(f"\n  结果: 完成 — 共 1 步")

    # ---- 场景 3: 达到最大步数 ----
    print(f"\n{'#'*60}")
    print("场景 3: 达到最大步数限制")
    print("任务: 复杂的多城市分析（max_steps=3）")
    print(f"{'#'*60}")

    agent3 = AgentLoop(max_steps=3)
    for i in range(3):
        agent3.events.append(Event(i, EventType.THINK, f"继续收集第 {i+1} 个城市的数据"))
        tool_name = ["GetPopulation", "GetGDP", "Calculator"][i]
        tool_inp = ["上海", "上海", "47218 / 2487"][i]
        agent3.events.append(Event(i, EventType.ACTION, f"{tool_name}({tool_inp})"))
        agent3.events.append(Event(i, EventType.OBSERVATION, f"模拟结果 {i+1}"))
        print(f"  [{i+1}] Thought: 继续收集第 {i+1} 个城市的数据")
        print(f"  [{i+1}] Action: {tool_name}({tool_inp})")
    agent3.events.append(Event(3, EventType.MAX_STEPS, "已达到最大步数 3"))
    print(f"\n  结果: 达到最大步数 — 强制停止")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "上海的人均 GDP 大约是多少？"
        agent = AgentLoop(max_steps=8, temperature=0.3)
        result = agent.run(question)
