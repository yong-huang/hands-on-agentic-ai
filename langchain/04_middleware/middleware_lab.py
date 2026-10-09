"""
04 · Middleware：Agent 运行时钩子

四块内容：
  A. 自定义中间件的两个核心动作（离线）— wrap_tool_call 拦截指定工具、
     放行其他工具
  B. 钩子与循环的交错次序（真机）— before_model / wrap_tool_call 的调用
     序列与计数
  C. 策略中间件实战（真机）— 禁止删除文件，但计算工具照常放行
  D. 预置中间件（真机）— ModelCallLimitMiddleware 截断超限循环、
     ToolRetryMiddleware 自动重试瞬时失败的工具

用法:
  python langchain/04_middleware/middleware_lab.py
  python langchain/04_middleware/middleware_lab.py --demo
"""

import os
import sys
from typing import Annotated
from urllib.request import urlopen

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

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
# 工具与中间件定义
# ============================================================

DELETED = []
FLAKY_CALLS = {"n": 0}


@tool
def calculator(expression: Annotated[str, "数学表达式，如 '2 + 2'"]) -> str:
    """计算数学表达式。"""
    return str(eval(expression, {"__builtins__": {}}))


@tool
def delete_file(path: Annotated[str, "要删除的文件路径"]) -> str:
    """删除指定文件（危险操作）。"""
    DELETED.append(path)
    return f"已删除 {path}"


@tool
def flaky_fetch(url: Annotated[str, "要抓取的地址"]) -> str:
    """抓取网页内容（可能瞬时失败）。"""
    FLAKY_CALLS["n"] += 1
    if FLAKY_CALLS["n"] <= 2:
        raise RuntimeError(f"瞬时故障 #{FLAKY_CALLS['n']}")
    return "ok-after-retries"


class SpyMiddleware(AgentMiddleware):
    """只观察不干预：记录钩子调用序列与计数。"""

    def __init__(self):
        super().__init__()
        self.events = []

    def before_model(self, state, runtime):
        self.events.append("before_model")
        return None

    def wrap_tool_call(self, request, handler):
        self.events.append(f"tool:{request.tool_call['name']}")
        return handler(request)


class TaggedSpy(AgentMiddleware):
    """记录 before/after 钩子序列的观察者（带标签，用于叠加顺序实验）。"""

    def __init__(self, tag, log):
        super().__init__()
        self.tag = tag
        self.log = log

    def before_model(self, state, runtime):
        self.log.append(f"{self.tag}:before_model")
        return None

    def after_model(self, state, runtime):
        self.log.append(f"{self.tag}:after_model")
        return None


class SpyA(TaggedSpy):
    pass


class SpyB(TaggedSpy):
    pass


class PolicyMiddleware(AgentMiddleware):
    """工具级策略：拦截黑名单工具，其余放行。"""

    def __init__(self, blocked_tools):
        super().__init__()
        self.blocked = set(blocked_tools)
        self.blocked_count = 0

    def wrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        if name in self.blocked:
            self.blocked_count += 1
            return ToolMessage(
                content=f"操作被策略拦截：{name} 不在允许列表内。",
                tool_call_id=request.tool_call["id"],
                name=name,
            )
        return handler(request)


def make_request(name, args, call_id="call_1"):
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": call_id, "type": "tool_call"},
        tool=None,
        state=None,
        runtime=None,
    )


# ============================================================
# A. 自定义中间件的拦截与放行（离线，直接调钩子）
# ============================================================

def part_a_direct():
    section("[A] 自定义中间件：拦截与放行（离线）")
    policy = PolicyMiddleware(blocked_tools=["delete_file"])

    called = []

    def handler(request):
        called.append(request.tool_call["name"])
        return ToolMessage(content="handler-ran", tool_call_id=request.tool_call["id"])

    blocked_result = policy.wrap_tool_call(
        make_request("delete_file", {"path": "old.txt"}), handler
    )
    print(f"  拦截 delete_file -> {_text(blocked_result)}")
    check("黑名单工具被拦截（handler 未执行）",
          "策略拦截" in _text(blocked_result) and called == [],
          f"handler 调用={called}")

    allowed_result = policy.wrap_tool_call(
        make_request("calculator", {"expression": "2 + 2"}), handler
    )
    print(f"  放行 calculator  -> {_text(allowed_result)}（handler 调用={called}）")
    check("白名单工具正常执行", _text(allowed_result) == "handler-ran"
          and called == ["calculator"])

    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    try:
        create_agent(
            model=FakeListChatModel(responses=["x"]), tools=[],
            middleware=[SpyA("A", []), SpyA("A", [])],
        )
        check("同类中间件实例不可重复注册", False, "未抛出 AssertionError")
    except AssertionError as e:
        check("同类中间件实例不可重复注册",
              "duplicate" in str(e).lower(), str(e))


# ============================================================
# B. 钩子与循环的交错次序（真机）
# ============================================================

def part_b_spy(llm):
    section("[B] SpyMiddleware：钩子次序与计数（真机）")
    from langchain.agents import create_agent

    spy = SpyMiddleware()
    agent = create_agent(
        model=llm, tools=[calculator], middleware=[spy],
        system_prompt="You are a calculator. ALWAYS use the tool.",
    )
    result = agent.invoke({"messages": [HumanMessage("请用工具计算 6 * 7。")]})
    print(f"  钩子序列: {spy.events}")
    tool_msgs = [m for m in result["messages"] if type(m).__name__ == "ToolMessage"]
    check("钩子按 模型前→工具→模型前 交错触发",
          spy.events == ["before_model", "tool:calculator", "before_model"],
          f"events={spy.events}")
    check("计数：工具调用 1 次、模型调用 2 次",
          len(tool_msgs) == 1 and spy.events.count("before_model") == 2)


# ============================================================
# C. 策略中间件实战（真机）
# ============================================================

def part_c_policy(llm):
    section("[C] 策略中间件：禁删文件、计算放行（真机）")
    from langchain.agents import create_agent

    DELETED.clear()
    policy = PolicyMiddleware(blocked_tools=["delete_file"])
    agent = create_agent(
        model=llm, tools=[delete_file, calculator], middleware=[policy],
        system_prompt="你是文件助手。用户要求删除文件时必须调用 delete_file 工具。",
    )

    r1 = agent.invoke({"messages": [HumanMessage("请删除 old.txt 文件。")]})
    blocked_msgs = [m for m in r1["messages"]
                    if type(m).__name__ == "ToolMessage" and "策略拦截" in _text(m)]
    print(f"  删除请求 -> 拦截消息 {len(blocked_msgs)} 条，实际删除 {DELETED}")
    check("删除请求被中间件拦截（磁盘无操作）",
          bool(blocked_msgs) and DELETED == [], f"DELETED={DELETED}")

    r2 = agent.invoke({"messages": [HumanMessage("请计算 2 + 2 等于多少。")]})
    calc_msgs = [m for m in r2["messages"]
                 if type(m).__name__ == "ToolMessage" and _text(m) == "4"]
    print(f"  计算请求 -> 工具结果 {[_text(m) for m in calc_msgs]}，"
          f"最终答案: {_text(r2['messages'][-1])[:40]}")
    check("计算工具不受影响，正常返回 4", bool(calc_msgs))


# ============================================================
# E. 叠加两个中间件：钩子顺序（真机）
# ============================================================

def part_e_order(llm):
    section("[E] 叠加中间件：进入顺序、返回逆序（真机）")
    from langchain.agents import create_agent

    log = []
    agent = create_agent(
        model=llm, tools=[calculator],
        middleware=[SpyA("A", log), SpyB("B", log)],
        system_prompt="You are a calculator. ALWAYS use the tool.",
    )
    agent.invoke({"messages": [HumanMessage("请用工具计算 5 * 5。")]})
    print(f"  钩子序列（前两轮）: {log[:8]}")
    expected = ["A:before_model", "B:before_model", "B:after_model", "A:after_model"]
    check("进入顺序 A→B、返回逆序 B→A", log[:4] == expected, f"log[:4]={log[:4]}")
    counts_ok = (
        log.count("A:before_model") == log.count("A:after_model")
        == log.count("B:before_model") == log.count("B:after_model")
        and len(log) % 4 == 0
    )
    check("每轮 before/after 成对出现", counts_ok)


# ============================================================
# D. 预置中间件（真机）
# ============================================================

def part_d_prebuilt(llm):
    from langchain.agents import create_agent
    from langchain.agents.middleware import ModelCallLimitMiddleware, ToolRetryMiddleware

    section("[D] 预置中间件：限次与重试（真机）")

    limit_agent = create_agent(
        model=llm, tools=[calculator],
        middleware=[ModelCallLimitMiddleware(run_limit=1, exit_behavior="end")],
        system_prompt="You are a calculator. ALWAYS use the tool.",
    )
    r = limit_agent.invoke({"messages": [HumanMessage("请用工具计算 6 * 7。")]})
    tool_msgs = [m for m in r["messages"] if type(m).__name__ == "ToolMessage"]
    final = _text(r["messages"][-1])
    print(f"  限次运行：工具结果 {[_text(m) for m in tool_msgs]}，结束语: {final[:50]}")
    check("超限前工具照常执行", any(_text(m) == "42" for m in tool_msgs))
    check("超限后被截断并给出结束语", "Model call limits exceeded" in final)

    FLAKY_CALLS["n"] = 0
    retry_agent = create_agent(
        model=llm, tools=[flaky_fetch],
        middleware=[ToolRetryMiddleware(max_retries=3, initial_delay=0.01, jitter=False)],
        system_prompt="你必须调用 flaky_fetch 工具一次，然后报告结果。",
    )
    r2 = retry_agent.invoke({"messages": [HumanMessage("抓取 example.com 并告诉我结果。")]})
    final2 = _text(r2["messages"][-1])
    print(f"  重试运行：工具实际被调用 {FLAKY_CALLS['n']} 次，"
          f"最终答案: {final2[:50]}")
    check("瞬时失败被自动重试到成功", FLAKY_CALLS["n"] == 3)
    check("模型拿到重试后的成功结果", "ok-after-retries" in final2)


def main():
    demo = "--demo" in sys.argv
    print("=" * 64)
    print("[04] Middleware：Agent 运行时钩子")
    print(f"模式: {'离线演示' if demo else f'真机（{MODEL}）'}")
    print("=" * 64)

    part_a_direct()

    if demo:
        print("\n  （--demo 只运行离线部分：B/C/D 需要 Ollama 与真机模型）")
    else:
        from langchain_ollama import ChatOllama

        if not ollama_alive():
            print("\n⏭️ Ollama 未启动，真机部分无法运行：先 `ollama serve`，"
                  "或加 `--demo` 看离线行为")
            return 2
        llm = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_predict=256)
        part_b_spy(llm)
        part_c_policy(llm)
        part_e_order(llm)
        part_d_prebuilt(llm)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
