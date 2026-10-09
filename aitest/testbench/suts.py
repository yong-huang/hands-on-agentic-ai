"""suts.py — SUT 适配层 (docs/aitest.md 项目 1)

SUT(System Under Test, 被测系统)适配层: 把仓库里两个现成 Agent 包成同一个
可编程调用接口 run_sut(), 测试台其余 20 个项目只面向这个接口写断言。

  主 SUT  "mh":   harness/mh mini-harness —— mh.loop.run_agent 每轮真调 LLM,
                  返回 final/turns/tool_trace/messages, 是行为测试的真靶标;
                  MOCK=1 时注入脚本化 chat_fn, 离线走完 loop 协议。
  辅 SUT  "mini": qa/30_mini_agent —— 纯模板引擎, 零 LLM 调用, 输出确定性,
                  供 CI 快速冒烟与"确定性组件怎么测"的对照样本。

统一结果模型 v0(后续项目 18 会扩成 schema):
  {"sut", "task", "final", "turns", "tool_trace", "cwd", "elapsed_s"}

约定与 qa/llm.py 一致: LLM_BASE_URL/LLM_MODEL/LLM_API_KEY 环境变量;
本模块零第三方依赖(pytest 除外), 探活用标准库 urllib。
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import importlib.util
import urllib.request

# ---- 路径锚定: 本文件位于 <repo>/aitest/testbench/suts.py -------------------
HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(AITEST_DIR)
MH_DIR = os.path.join(REPO_ROOT, "harness")
MINI_AGENT_PY = os.path.join(REPO_ROOT, "qa", "30_mini_agent", "mini_agent.py")

for _p in (AITEST_DIR, MH_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 本地服务不走系统代理(harness/01 实验踩过的坑, 这里提前免疫)
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

DEFAULT_TASK = "用工具创建 hi.txt, 内容为 ok, 然后汇报文件内容。"


# ============================================================
# 探活: 真实模式的前置检查
# ============================================================

def ollama_alive(base_url=None, timeout=3):
    """Ollama OpenAI 兼容端点是否存活。所有真实模式项目开工前先调它。"""
    base = base_url or os.environ.get(
        "LLM_BASE_URL", "http://localhost:11434/v1")
    try:
        with urllib.request.urlopen(f"{base}/models", timeout=timeout):
            return True
    except Exception:  # noqa: BLE001 —— 探活失败只返回 False, 不抛
        return False


# ============================================================
# 主 SUT: harness/mh
# ============================================================

def _run_bash(command: str, cwd: str = None) -> str:
    """测试台默认工具: 与 harness/04 的 v0.1 同款(项目 6 之前不做沙箱)。

    cwd 必须是显式形参: mh.loop 按 'cwd' in signature 注入任务目录。
    """
    p = subprocess.run(["bash", "-c", command], cwd=cwd,
                       capture_output=True, text=True, timeout=15)
    return (p.stdout + p.stderr).strip() or "(无输出)"


DEFAULT_TOOLS = {
    "run_bash": {
        "desc": "在任务目录执行 bash 命令, 返回 stdout+stderr",
        "schema": {"type": "function", "function": {
            "name": "run_bash",
            "description": "在任务目录执行 bash 命令, 返回 stdout+stderr",
            "parameters": {"type": "object",
                           "properties": {"command": {"type": "string",
                                                      "description": "要执行的命令"}},
                           "required": ["command"]}}},
        "fn": _run_bash,
    }
}


def mock_chat_fn(script=None):
    """脚本化 chat_fn 工厂: MOCK=1 离线模式注入 mh.loop。

    默认剧本: 第 1 轮发起一次 run_bash 写文件, 第 2 轮文本收敛。
    剧本是 (tool_call | 文本) 列表, 按调用次序回放, 耗尽后固定收敛句。
    """
    steps = script or [
        ("tool", "run_bash", {"command": "printf 'ok' > hi.txt"}),
        ("final", "已完成: hi.txt 已创建, 内容为 ok。"),
    ]
    calls = {"n": 0}

    def _chat(messages, tools=None, **kw):
        i = min(calls["n"], len(steps) - 1)
        calls["n"] += 1
        step = steps[i]
        if step[0] == "tool":
            return {"content": "", "tool_calls": [
                {"function": {"name": step[1], "arguments": step[2]}}]}
        return {"content": step[1], "tool_calls": None}

    _chat.calls = calls
    return _chat


def _run_mh(task, system=None, max_turns=8, model=None, sandbox=None,
            chat_fn=None, on_event=None, tools=None):
    from mh import loop  # harness/mh, 顶部已入 sys.path

    if model:  # 临时切模型, 不污染调用方环境
        old = os.environ.get("LLM_MODEL")
        os.environ["LLM_MODEL"] = model
    cwd = sandbox or tempfile.mkdtemp(prefix="aitest_sut_")
    t0 = time.time()
    try:
        init_messages = None
        if system is not None:
            # 注入 system 必须在驱动之前 —— run_agent 只在自行播种时写默认
            # SYSTEM, 事后改返回值是化妆不是覆盖(项目 9 首跑踩过: 两版
            # prompt 信号完全相同才暴露)。
            init_messages = [{"role": "system", "content": system},
                             {"role": "user", "content": task}]
        result = loop.run_agent(task, tools or dict(DEFAULT_TOOLS),
                                max_turns=max_turns,
                                chat_fn=chat_fn, cwd=cwd, on_event=on_event,
                                messages=init_messages)
    finally:
        if model:
            if old is None:
                os.environ.pop("LLM_MODEL", None)
            else:
                os.environ["LLM_MODEL"] = old
    result.update({"sut": "mh", "task": task, "cwd": cwd,
                   "elapsed_s": round(time.time() - t0, 2)})
    return result


# ============================================================
# 辅 SUT: qa/30_mini_agent (确定性, 零 LLM)
# ============================================================

_MINI_MOD = None


def _mini_module():
    """按路径加载 qa/30_mini_agent/mini_agent.py, 落盘重定向到临时目录。

    Tracer/Memory 会在模块目录写 trace.jsonl/memory.json; 测试不允许弄脏
    被测对象自己的目录, 全部指到 tempfile。
    """
    global _MINI_MOD
    if _MINI_MOD is None:
        spec = importlib.util.spec_from_file_location("mini_agent", MINI_AGENT_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = tempfile.mkdtemp(prefix="aitest_mini_")
        mod.TRACE_PATH = os.path.join(tmp, "trace.jsonl")
        mod.MEMORY_PATH = os.path.join(tmp, "memory.json")
        _MINI_MOD = mod
    return _MINI_MOD


def _run_mini(task):
    mod = _mini_module()
    t0 = time.time()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):  # mini 的 execute/evaluate 会打印报告
        tracer = mod.Tracer()
        root = tracer.span(None, "agent", "mini-agent", str(task))
        plan_list = mod.plan("A1", 2)
        results = mod.execute(plan_list, tracer, root)
        tracer.finish(root, "done", 0)
        all_ok = bool(mod.evaluate(results))
    trace = [(e["type"], e["name"]) for e in tracer.events]
    return {"sut": "mini", "task": task, "final": "ok" if all_ok else "failed",
            "turns": len(plan_list), "tool_trace": trace,
            "stdout": buf.getvalue(), "all_ok": all_ok,
            "cwd": os.path.dirname(MINI_AGENT_PY),
            "elapsed_s": round(time.time() - t0, 3)}


# ============================================================
# 统一入口
# ============================================================

def run_sut(task=DEFAULT_TASK, sut="mh", system=None, max_turns=8, model=None,
            sandbox=None, chat_fn=None, on_event=None, tools=None):
    """驱动一次被测 Agent, 返回统一结果模型 dict。

    sut="mh"   主 SUT, 真实 LLM; MOCK=1 或显式传 chat_fn 时走离线剧本。
    sut="mini" 辅 SUT, 纯模板零 LLM, 任何环境离线可跑。
    model      临时覆盖 LLM_MODEL(如 qwen3:4b 给跑批降速)。
    sandbox    任务工作目录; 缺省各建临时目录, 测试间互不污染。
    tools      覆盖默认工具表(注入靶场用它挂权限门版本)。
    """
    if sut == "mini":
        return _run_mini(task)
    if sut != "mh":
        raise ValueError(f"未知 SUT: {sut!r} (可选: 'mh' / 'mini')")
    if chat_fn is None and os.environ.get("MOCK") == "1":
        chat_fn = mock_chat_fn()
    return _run_mh(task, system=system, max_turns=max_turns, model=model,
                   sandbox=sandbox, chat_fn=chat_fn, on_event=on_event,
                   tools=tools)


def result_summary(r):
    """一行摘要, 演示与报告复用。兼容两种轨迹形态:
    mh.loop 产 dict {"tool":...}, mini 产 (type, name) 元组。"""
    names = []
    for tc in r.get("tool_trace", []):
        if isinstance(tc, dict):
            names.append(tc.get("tool") or tc.get("name") or "?")
        elif isinstance(tc, (tuple, list)) and len(tc) > 1:
            names.append(tc[1])
        else:
            names.append(str(tc))
    return (f"[{r['sut']}] turns={r['turns']} tools={names or '-'} "
            f"{r['elapsed_s']}s final={str(r['final'])[:40]!r}")


if __name__ == "__main__":  # 最小自检: python3 suts.py
    print("ollama_alive:", ollama_alive())
    print("mock  :", result_summary(run_sut(chat_fn=mock_chat_fn())))
    print("mini  :", result_summary(run_sut(sut="mini")))
    print(json.dumps({"repo_root": REPO_ROOT, "mini": MINI_AGENT_PY}, indent=2))
