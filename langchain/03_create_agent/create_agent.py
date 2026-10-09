"""
03 · create_agent：工具绑定与 Agent Loop 内核

三块内容：
  A. 工具契约（离线）— @tool 自动生成 schema；ToolNode 对工具抛错的两种
     策略：默认原样抛出 vs handle_tool_errors=True 转成错误 ToolMessage
  B. 模型侧的 bind_tools（真机）— 模型返回结构化 tool_calls 请求
  C. create_agent 托管循环（真机）— 模型→工具→模型的完整闭环：查询工具
     失败返回错误文本，模型据此改用估算工具并报告结果

用法:
  python langchain/03_create_agent/create_agent.py
  python langchain/03_create_agent/create_agent.py --demo
"""

import operator
import os
import sys
from typing import Annotated, TypedDict
from urllib.request import urlopen

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

MODEL = os.environ.get("LLM_MODEL", "qwen3.8:latest")
OLLAMA = "http://localhost:11434"

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def ollama_alive():
    try:
        with urlopen(f"{OLLAMA}/v1/models", timeout=3):
            return True
    except Exception:
        return False


def _text(msg):
    content = getattr(msg, "content", msg)
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)


# ============================================================
# 工具定义
# ============================================================

@tool
def calculator(expression: Annotated[str, "要计算的数学表达式，如 '6 * 7'"]) -> str:
    """用只含四则运算的表达式计算数值。"""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return f"ERROR: 表达式含不允许的字符: {expression!r}"
    try:
        return str(eval(expression, {"__builtins__": {}}))
    except Exception as e:
        return f"ERROR: {e}"


@tool
def fetch_price(item: Annotated[str, "商品名，英文小写，如 apple"]) -> str:
    """查询商品的实时价格（元）。"""
    return ("ERROR: 实时价格服务不可用 (503)。"
            "请调用 estimate_price 工具获取估算价格，不要自行编造数字。")


@tool
def estimate_price(item: Annotated[str, "商品名，英文小写，如 apple"]) -> str:
    """基于历史数据估算商品价格（元）。"""
    return "4.5"


@tool
def broken_tool(item: Annotated[str, "任意输入"]) -> str:
    """一个必然抛异常的演示工具。"""
    raise RuntimeError("价格服务不可用 (503)")


# ============================================================
# A. 工具契约与 ToolNode 错误策略（离线）
# ============================================================

class MsgState(TypedDict):
    messages: Annotated[list, operator.add]


def run_tool_node(tools, tool_call_msg, handle_tool_errors=None):
    graph = StateGraph(MsgState)
    kwargs = {} if handle_tool_errors is None else {"handle_tool_errors": handle_tool_errors}
    graph.add_node("tools", ToolNode(tools, **kwargs))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile().invoke({"messages": [tool_call_msg]})


def fake_call(name, args, call_id="call_1"):
    return AIMessage(content="", tool_calls=[
        {"name": name, "args": args, "id": call_id, "type": "tool_call"}
    ])


def part_a_tools():
    section("[A] 工具契约与 ToolNode 错误策略（离线）")

    schema = calculator.get_input_schema().model_json_schema()
    props = schema.get("properties", {})
    print(f"  calculator schema 属性: {list(props)}")
    print(f"    expression 描述: {props.get('expression', {}).get('description')}")
    check("@tool 从函数签名与注解生成参数 schema",
          "expression" in props
          and props["expression"].get("type") == "string"
          and bool(props["expression"].get("description")))

    try:
        run_tool_node([broken_tool], fake_call("broken_tool", {"item": "apple"}))
        check("ToolNode 默认策略：工具异常原样抛出", False, "未抛出异常")
    except RuntimeError as e:
        check("ToolNode 默认策略：工具异常原样抛出", True, f"RuntimeError({e})")

    out = run_tool_node(
        [broken_tool], fake_call("broken_tool", {"item": "apple"}),
        handle_tool_errors=True,
    )
    last = out["messages"][-1]
    print(f"  handle_tool_errors=True -> {type(last).__name__} "
          f"status={getattr(last, 'status', None)}")
    print(f"    content: {_text(last)[:70]}")
    check("handle_tool_errors=True 转成错误 ToolMessage",
          getattr(last, "status", None) == "error" and "503" in _text(last))


# ============================================================
# B. bind_tools：模型侧的工具调用请求（真机）
# ============================================================

def part_b_bind_tools(llm):
    section("[B] bind_tools：模型返回结构化 tool_calls（真机）")
    bound = llm.bind_tools([calculator])
    resp = bound.invoke([HumanMessage("请用工具计算 6 * 7 等于多少。")])
    calls = getattr(resp, "tool_calls", None) or []
    print(f"  tool_calls: {[(c['name'], c['args']) for c in calls]}")
    check("模型按工具请求格式返回 tool_calls",
          bool(calls) and calls[0]["name"] == "calculator")


# ============================================================
# C. create_agent：多步工具循环与失败回退（真机）
# ============================================================

def part_c_agent(llm):
    section("[C] create_agent：查询失败 → 改用估算 → 汇报（真机）")
    from langchain.agents import create_agent

    agent = create_agent(
        model=llm,
        tools=[calculator, fetch_price, estimate_price],
        system_prompt=(
            "你是购物助手。查询价格时先调用 fetch_price；"
            "如果它返回 ERROR，必须调用 estimate_price 工具获取估算值；"
            "任何价格数字都必须来自工具返回值，不允许自己计算或编造。最终用一句话报告。"
        ),
    )
    result = agent.invoke({"messages": [HumanMessage("帮我查一下 apple 的价格。")]})
    messages = result["messages"]

    print("  消息轨迹：")
    for m in messages:
        kind = type(m).__name__
        if getattr(m, "tool_calls", None):
            names = [c["name"] for c in m.tool_calls]
            print(f"    {kind:12s} -> tool_calls {names}")
        elif kind == "ToolMessage":
            print(f"    {kind:12s} [{m.name}] {_text(m)[:48]}")
        else:
            print(f"    {kind:12s} {_text(m)[:60]}")

    tool_names = [m.name for m in messages if type(m).__name__ == "ToolMessage"]
    ai_tool_calls = [m for m in messages if getattr(m, "tool_calls", None)]
    final = _text(messages[-1])

    check("查询失败后模型改用估算工具",
          "fetch_price" in tool_names and "estimate_price" in tool_names,
          f"工具调用={tool_names}")
    check("最终报告包含估算价格 4.5", "4.5" in final, f"final={final[:60]}")
    check("消息序列呈现 模型→工具→模型 循环",
          len(ai_tool_calls) >= 2 and len(tool_names) >= 2,
          f"模型发起工具调用 {len(ai_tool_calls)} 次")


def part_d_demo_loop():
    section("[D] 演示：手动装配一次 Agent Loop（离线）")
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    state = {"messages": [HumanMessage("请用工具计算 6 * 7。")]}
    planner = fake_call("calculator", {"expression": "6 * 7"})
    state["messages"].append(planner)

    graph = StateGraph(MsgState)
    graph.add_node("tools", ToolNode([calculator], handle_tool_errors=True))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    state = graph.compile().invoke(state)
    tool_msg = state["messages"][-1]
    print(f"  工具节点执行 {planner.tool_calls[0]['name']}(6 * 7) -> {_text(tool_msg)}")

    fake = FakeListChatModel(responses=["6 * 7 = 42。"])
    final = fake.invoke(state["messages"])
    print(f"  下一轮模型收尾 -> {_text(final)}")
    check("手动循环：工具执行结果正确回填", _text(tool_msg) == "42")
    check("手动循环：模型看到结果后收尾", "42" in _text(final))


def main():
    demo = "--demo" in sys.argv
    print("=" * 64)
    print("[03] create_agent：工具绑定与 Agent Loop 内核")
    print(f"模式: {'离线演示' if demo else f'真机（{MODEL}）'}")
    print("=" * 64)

    part_a_tools()

    if demo:
        part_d_demo_loop()
    else:
        from langchain_ollama import ChatOllama

        if not ollama_alive():
            print("\n⏭️ Ollama 未启动，真机部分无法运行：先 `ollama serve`，"
                  "或加 `--demo` 看离线行为")
            return 2
        llm = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_predict=512)
        part_b_bind_tools(llm)
        part_c_agent(llm)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
