"""mh.subagent — 子代理调度 (项目 13): 上下文隔离的任务分派与回收

子代理 = 独立消息历史 + 独立工具表实例的一次完整 run_agent。
隔离的意义: 子代理跑 10 轮、调 8 次工具, 主代理上下文只多一条摘要 ——
"任务描述就是上下文防火墙"(02 解剖图多 agent 输出层的最小实现)。

spawn_subagent 工厂产出一个可注册的工具:
  入参 = 任务描述(自然语言, 隔离边界)
  返回 = 结果摘要(截断)
  副记录 = 工具对象 .last_trace 保留子代理完整调用轨迹(验收/调试用,
           永不进入主代理上下文)。
"""

from . import loop as mh_loop


def spawn_subagent(*, tools_factory, system=None, max_turns=10,
                   summary_len=500, name="spawn_subagent", desc=None,
                   chat_fn=None):
    """tools_factory() 每次调用返回全新工具表实例 —— 状态隔离从工具层开始。"""
    state = {"last_trace": [], "last_turns": 0}

    def _run(task: str, cwd: str = None) -> str:
        tools = tools_factory()  # 全新实例: 与主代理无共享可变状态
        result = mh_loop.run_agent(task, tools, max_turns=max_turns,
                                   chat_fn=chat_fn, cwd=cwd)
        state["last_trace"] = result["tool_trace"]
        state["last_turns"] = result["turns"]
        return (f"[子代理·{result['turns']} 轮 {len(result['tool_trace'])} 次工具调用] "
                + result["final"][:summary_len])

    def _fn(task: str, cwd: str = None) -> str:
        return _run(task, cwd=cwd)

    schema = {"type": "function", "function": {
        "name": name,
        "description": desc or ("把一个独立子任务交给子代理执行, 它有自己的上下文; "
                                "你只会收到结果摘要, 收不到过程。"),
        "parameters": {"type": "object",
                       "properties": {"task": {"type": "string",
                                               "description": "完整、自洽的子任务描述"}},
                       "required": ["task"]}}}
    tool = {"desc": schema["function"]["description"], "schema": schema, "fn": _fn,
            "_state": state}
    return tool
