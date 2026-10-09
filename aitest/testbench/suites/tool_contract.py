"""suites.tool_contract — 工具调用契约测试 (docs/aitest.md 项目 14)

给 SUT 挂一组 mock 工具并记录每次调用, 对调用日志做两类断言:
  1. 参数契约: 每次调用的参数过 CONTRACT(必填键 + 类型)
  2. 序列契约: 调用序列是期望剧本的有序子序列, 多余调用记违规

三个"工具描述被写坏"的变体用于自证测试有效(诱导真模型传错参/漏参/多调):
  wrong_type    参数 schema 声明成 string, 诱导模型传 "21" 而非 21
  missing_param 必填参数在 schema/描述里被抹掉, 诱导模型漏传
  extra_call    塞一个描述极具诱惑的"调试工具", 诱导模型多调

    run_contract(variant=None, model=...) -> report dict
"""

import os
import sys
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(os.path.dirname(HERE))
RESULTS_DIR = os.path.join(AITEST_DIR, "results")
REPORT_PATH = os.path.join(RESULTS_DIR, "tool_contract.json")

sys.path.insert(0, AITEST_DIR)

# 期望剧本: 先写笔记, 再算数
EXPECTED_SEQUENCE = ["write_note", "calc_sum"]

# 参数契约: 工具名 -> {参数: 期望类型(元组=任一)}
CONTRACT = {
    "write_note": {"title": str, "body": str},
    "calc_sum": {"a": (int, float), "b": (int, float)},
    "list_notes": {},
}

TASK = ("请先调用 write_note 工具写一条标题为 hello、内容为 world 的笔记; "
        "再调用 calc_sum 工具计算 21 加 21。不要调用其他工具。")
# extra_call 变体专用: 不点名用哪个写笔记工具, 让"等价诱饵工具"有机会被选中
TASK_EXTRA = ("请写一条标题为 hello、内容为 world 的笔记; "
              "再调用 calc_sum 工具计算 21 加 21。")


def _fn_schema(name, desc, properties, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": properties,
                       "required": required}}}


def describe_tools(variant=None):
    """构造工具表; variant 对描述/schema 做定向破坏。"""
    defs = {
        "write_note": _fn_schema(
            "write_note", "写一条笔记到任务目录。",
            {"title": {"type": "string", "description": "笔记标题"},
             "body": {"type": "string", "description": "笔记内容"}},
            ["title", "body"]),
        "calc_sum": _fn_schema(
            "calc_sum", "计算两个数之和。",
            {"a": {"type": "number", "description": "第一个加数"},
             "b": {"type": "number", "description": "第二个加数"}},
            ["a", "b"]),
        "list_notes": _fn_schema(
            "list_notes", "列出任务目录里的笔记。",
            {}, []),
    }
    if variant == "wrong_type":
        defs["calc_sum"]["function"]["description"] = \
            "计算两个数之和。注意: 参数必须以字符串形式传入, 如 \"21\"。"
        for k in ("a", "b"):
            defs["calc_sum"]["function"]["parameters"]["properties"][k] = {
                "type": "string", "description": "加数(字符串形式)"}
    elif variant == "missing_param":
        defs["write_note"]["function"]["description"] = "写一条笔记。"
        defs["write_note"]["function"]["parameters"]["required"] = ["title"]
        defs["write_note"]["function"]["parameters"]["properties"].pop("body")
    elif variant == "extra_call":
        # 写坏 write_note 的描述(说成只读), 让诱饵工具承接"写笔记"语义
        defs["write_note"]["function"]["description"] = \
            "查看一条笔记的模板(只读, 不写入任何内容)。"
        defs["save_memo"] = _fn_schema(
            "save_memo", "把标题与内容保存为一条笔记(写入任务目录)。",
            {"title": {"type": "string", "description": "笔记标题"},
             "body": {"type": "string", "description": "笔记内容"}},
            ["title", "body"])
    elif variant is not None:
        raise ValueError(f"未知变体: {variant}")
    return defs


def build_tools(variant=None):
    """把 defs 包成 mh 工具表 + 调用日志。"""
    defs = describe_tools(variant)
    log = []

    def write_note(title, body):
        return f"已写笔记 {title}"

    def calc_sum(a, b):
        return str(a + b)

    def list_notes():
        return "(空)"

    def save_memo(title, body):
        return f"已保存备忘 {title}"

    impls = {"write_note": write_note, "calc_sum": calc_sum,
             "list_notes": list_notes, "save_memo": save_memo}

    tools = {}
    for name, schema in defs.items():
        fn = impls[name]

        def _wrap(fn=fn, name=name):
            def _call(**kwargs):
                log.append({"name": name, "args": kwargs})
                return fn(**kwargs)
            return _call

        tools[name] = {"desc": schema["function"]["description"],
                       "schema": schema, "fn": _wrap()}
    return tools, log


# ============================================================
# 契约断言
# ============================================================

def check_args(log):
    """参数契约: 必填齐全 + 类型匹配。返回违规列表。"""
    violations = []
    for entry in log:
        spec = CONTRACT.get(entry["name"])
        if spec is None:
            continue                      # 多余工具由序列断言负责
        args = entry["args"]
        for key, typ in spec.items():
            if key not in args:
                violations.append(
                    {"kind": "missing_param", "tool": entry["name"],
                     "detail": f"缺少必填参数 {key}"})
            elif not isinstance(args[key], typ):
                violations.append(
                    {"kind": "wrong_type", "tool": entry["name"],
                     "detail": f"参数 {key}={args[key]!r} 类型应为 {typ}"})
    return violations


def check_sequence(log, expected=None):
    """序列契约: expected 是有序子序列; 白名单外的调用= 多余调用。"""
    expected = expected or EXPECTED_SEQUENCE
    violations = []
    names = [e["name"] for e in log]
    cursor = 0                               # 每项找 cursor 之后的最早匹配
    for want in expected:                    # 失败不推进 cursor(后续项仍可匹配)
        match = next((j for j in range(cursor, len(names))
                      if names[j] == want), None)
        if match is None:
            violations.append({"kind": "missing_call", "tool": want,
                               "detail": f"剧本要求调用 {want}, 实际序列 {names}"})
        else:
            cursor = match + 1
    allowed = set(expected) | {"list_notes"}
    for n in names:
        if n not in allowed:
            violations.append({"kind": "extra_call", "tool": n,
                               "detail": f"调用了剧本外的工具 {n}"})
    return violations


def run_contract(variant=None, model="qwen3:4b", verbose=True):
    """真机跑一遍任务, 返回 {violations, args, sequence, log, final}。"""
    from testbench import suts
    variant = None if variant in (None, "normal") else variant
    tools, log = build_tools(variant)
    task = TASK_EXTRA if variant == "extra_call" else TASK
    r = suts.run_sut(task, sut="mh", model=model, max_turns=6, tools=tools)
    v_args = check_args(log)
    v_seq = check_sequence(log)
    violations = v_args + v_seq
    if verbose:
        names = [e["name"] for e in log]
        print(f"  variant={variant or 'normal'}: 调用序列={names} "
              f"违规={len(violations)}")
        for v in violations:
            print(f"    - [{v['kind']}] {v['detail']}")
    return {"variant": variant or "normal",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "model": model, "sequence": [e["name"] for e in log],
            "violations": violations, "log": log,
            "final": str(r.get("final", ""))[:120]}


def _cli():
    import argparse
    import json
    ap = argparse.ArgumentParser(description="工具调用契约测试")
    ap.add_argument("--variant", default=None,
                    choices=[None, "wrong_type", "missing_param", "extra_call"])
    ap.add_argument("--model", default="qwen3:4b")
    args = ap.parse_args()
    rep = run_contract(args.variant, model=args.model)
    out = Path(REPORT_PATH)
    out.parent.mkdir(exist_ok=True)
    history = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    history[rep["variant"]] = rep
    out.write_text(json.dumps(history, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"落盘 -> {out}")
    sys.exit(1 if rep["violations"] else 0)


if __name__ == "__main__":
    _cli()
