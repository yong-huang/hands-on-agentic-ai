"""mh.loop — Agent 主循环 (项目 04, mini-harness v0.1)

Agent = Model + Harness 里的"Harness"最小形态:
  while 轮次未超限:
    1. 带工具 schema 请求模型推理
    2. 模型返回 tool_calls → 逐个执行 → role:tool 回填
    3. 无 tool_calls → 视为最终回答, 收敛退出
先执行再收尾(01 实验: 命令与"完成"同轮时漏执行是致命 bug)。

接口:
  run_agent(task, tools, max_turns=8, chat_fn=None, on_event=None) -> dict
    tools: {name: {"desc": str, "schema": dict, "fn": callable}}
    返回: {"final": 最终回答, "turns": 实际轮次, "tool_trace": [...], "messages": 完整历史}
"""

from . import llm as mh_llm

SYSTEM = ("你是严谨的运维助手, 通过工具完成用户任务。工具调用前先确认参数。"
          "任务全部完成后, 用一句话汇报结果。/no_think")


def _schema_of(tools):
    return [tools[n]["schema"] for n in tools]


def run_agent(task, tools, max_turns=8, chat_fn=None, cwd=None, on_event=None,
              messages=None):
    """执行一个任务直到模型收敛或超轮次。cwd 传给工具 fn 的 kwargs。

    messages 可选: 传入已有历史即为"恢复会话"(11 项目用), 此时 task 仍作为
    元信息记录但不再重复播种。其余参数语义不变 —— 加法扩展, 不改旧行为。
    """
    chat_fn = chat_fn or mh_llm.chat_with_retry
    emit = on_event or (lambda *a, **k: None)
    if messages is None:
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": task}]
    tool_trace, turns = [], 0
    for turn in range(1, max_turns + 1):
        turns = turn
        msg = chat_fn(messages, tools=_schema_of(tools))
        tool_calls = msg.get("tool_calls") or []
        emit("round", turn, msg.get("content", ""),
             [(tc["function"]["name"], tc["function"].get("arguments", {}))
              for tc in tool_calls])
        if not tool_calls:  # 无工具调用 = 最终回答
            messages.append({"role": "assistant", "content": msg.get("content", "")})
            break
        messages.append(msg)  # 先落 assistant(含 tool_calls), 再回填 tool 结果
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = tc["function"].get("arguments", {}) or {}
            entry = tools.get(name)
            if not entry:
                out = f"错误: 未知工具 {name}"
            else:
                try:
                    out = entry["fn"](**args, cwd=cwd) if "cwd" in _params(entry["fn"]) \
                        else entry["fn"](**args)
                except Exception as e:  # 原始错误直传 —— 05 项目会治理这里
                    out = f"{type(e).__name__}: {e}"
            tool_trace.append({"tool": name, "args": args, "result": str(out)[:200]})
            messages.append({"role": "tool", "tool_name": name, "content": str(out)})
    else:
        emit("max_turns", max_turns)
    return {"final": msg.get("content", ""), "turns": turns,
            "tool_trace": tool_trace, "messages": messages}


def _params(fn):
    import inspect
    return inspect.signature(fn).parameters
