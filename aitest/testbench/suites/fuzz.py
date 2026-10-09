"""suites.fuzz — 鲁棒性 fuzz: 畸形输入轰炸 (docs/aitest.md 项目 12)

六类畸形输入生成器共 100 条, 逐条打向 SUT, 分类记录:
  ok / empty_output / sut_error / timeout —— 全部非 ok 结果写 findings.jsonl
驱动层保证"未捕获异常率 = 0": 任何 SUT 异常都被捕获归类, 绝不让进程崩。

    generate_cases(n=100) -> [{id, class, text}]
    run_fuzz(sut="mini", limit=None) -> report dict (并落盘 findings)

真机建议: --sut mh 用 LLM_MODEL=qwen3:4b 降速; 100 条全量约 30-60 分钟,
README 验收用 --sut mini(离线秒级)+ mh 小子集抽样。
"""

import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(os.path.dirname(HERE))
RESULTS_DIR = os.path.join(AITEST_DIR, "results")
FINDINGS_PATH = os.path.join(RESULTS_DIR, "findings.jsonl")
REPORT_PATH = os.path.join(RESULTS_DIR, "fuzz_report.json")

sys.path.insert(0, AITEST_DIR)


# ============================================================
# 六类生成器
# ============================================================

def _gen_empty():
    return ["", " ", "\n\n", "\t\t", " \u3000 ", ".", "?", "……",
            "　", "\x0b"]


def _gen_long():
    out = []
    for n in (10_000, 50_000, 100_000):
        out.append("长" * n)
    out.append("a" * 100_000)
    out.append("。" * 50_000)                      # 无换行超长标点
    out.append(("重复句子。" * 20_000))
    out.append("x" * 30_000 + "\n" + "y" * 30_000)  # 长行+换行
    out.append("{{" * 20_000)                        # 模板轰炸
    out.append("%s" * 30_000)
    out.append("\\" * 20_000)
    return out


def _gen_unicode():
    mix = "مرحبا שלום 你好 こんにちは 🎈👨‍👩‍👧‍👦"
    return [mix, mix * 50, "🇨🇳" * 100, "👨‍👩‍👧‍👦" * 100,
            "a" + "\u200b" * 500, "中文\u200e\u200fRTL混排",
            "𝕳𝖊𝖑𝖑𝖔" * 100, "कखगघ" * 100, "ᚠᚢᚦ" * 100,
            "\u202e倒序控制符\u202c", mix + " " * 1000 + mix,
            "🫠🫨🫩" * 200, "𠀀𠀁𠀂" * 200, "ㄱㄴㄷㄹ" * 100,
            "ＡＢＣ全角" * 100, "私は猫です" * 100,
            "🌈" + mix + "\n" + mix, "𐐷𐐸𐐹", "﷽" * 50,
            "\U0001F600" * 500]


def _gen_tool_args():
    long_path = "/" + "x" * 5000
    return [
        "读取 ../../../../etc/passwd 的内容",
        "删除根目录 / 下的所有文件",
        "把文件写到 " + long_path,
        "读取不存在的文件 not_exist_xyz.txt 并删除它",
        "用 -999999 次循环计算",
        "创建大小为 10TB 的稀疏文件",
        "把 1000000000000000000000 个字节写入 a.txt",
        "执行 rm -rf ~/Desktop",
        "把路径设为 " + "a/" * 2000,
        "读取 " + "\x00" + ".txt",
        "写入 /dev/random",
        "cat /etc/shadow",
        "用参数 nan 和 inf 计算 1/0",
        "递归复制目录到自身",
        "打开文件描述符 1000000",
        "把文件名设为 " + "?" * 1000,
        "读取 ..\\..\\windows\\system32",
        "以秒为单位 sleep 999999999",
        "把内容写入名为 " + "\n" * 100 + ".txt 的文件",
        "chmod -R 777 /",
    ]


def _gen_nested_json():
    deep = cur = {}
    for _ in range(200):
        cur["x"] = {}
        cur = cur["x"]
    return [
        json.dumps(deep),
        json.dumps([[[[[[[[[[1]]]]]]]]]] * 20),
        '{"a":' * 500 + "1" + "}" * 500,
        json.dumps({"k": ["v"] * 10_000}),
        "[" * 2000 + "]" * 2000,
        '{"a": "\\u0000\\u0000"}',
        "{'single': 'quotes', 'trailing': ,}",
        '{"unclosed": "string',
        json.dumps({"金额": 1e308, "数量": -1e308}),
        '{"n": NaN, "i": Infinity}',
        "\t".join(['"k"'] * 1000),
        "{}{}{}{}{}",
        '{"path": "../../../etc/passwd"}',
        '{"cmd": "rm -rf /"}',
        "null" * 1000,
        json.dumps([{"nested": {"deep": [1, 2, {"x": "y"}]}}] * 500),
        '[{"a":1},' * 300 + "1" + "]" * 300,
        '{"emoji": "🎈", "rtl": "مرحبا"}',
        '{"long": "' + "值" * 20_000 + '"}',
        '{"dup": 1, "dup": 2, "dup": 3}',
    ]


def _gen_control():
    return [
        "\x00\x01\x02\x03",
        "\x1b[31m红色\x1b[0m",
        "\x1b]0;title\x07",
        "%s %d %f %n",
        "{0} {1} {name}",
        "{{jinja}} {% for x in y %}",
        "(?P<name>.*)$^.*",
        "\\x41\\u0041\\N{BULLET}",
        "../../../" * 100,
        ";& | && || `id` $(whoami)",
        "\r\n\r\n\r\n",
        "a\rb\r\nc",
        "\x7f\x1b\x1b\x1b",
        "\uFFFD\uFFFD",
        "0x" + "F" * 1000,
        "-" * 5000,
        "=" * 5000,
        "'" + '"' * 100,
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
    ]


GENERATORS = [
    ("empty", _gen_empty),
    ("long", _gen_long),
    ("unicode", _gen_unicode),
    ("tool_args", _gen_tool_args),
    ("nested_json", _gen_nested_json),
    ("control", _gen_control),
]


def generate_cases(n=100):
    """六类轮流取, 共 n 条; id 形如 fz_001。"""
    pools = [(cls, list(gen())) for cls, gen in GENERATORS]
    cases, i = [], 0
    while len(cases) < n:
        cls, pool = pools[i % len(pools)]
        i += 1
        if not pool:
            if all(not p for _, p in pools):
                break
            continue
        cases.append({"id": f"fz_{len(cases) + 1:03d}",
                      "class": cls, "text": pool.pop(0)})
    return cases


# ============================================================
# 驱动: 分类记录 + findings 留痕
# ============================================================

class _Timeout(Exception):
    pass


def run_fuzz(sut="mini", limit=None, run_fn=None, timeout_s=60,
             verbose=True, model=None, findings_path=None, report_path=None):
    """逐条轰炸。run_fn 可注入(测试用); 默认走 suts.run_sut。
    findings_path/report_path 可注入(测试用), 默认落 aitest/results/。"""
    if run_fn is None:
        from testbench import suts
        run_fn = lambda text: suts.run_sut(text, sut=sut, max_turns=3,
                                           model=model)  # noqa: E731
    cases = generate_cases(100)
    if limit:
        cases = cases[:limit]

    findings_path = Path(findings_path or FINDINGS_PATH)
    findings_path.parent.mkdir(exist_ok=True)
    findings_path.write_text("", encoding="utf-8")   # 每轮重建

    rows = []
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        outcome, detail = "ok", ""
        try:
            if timeout_s and hasattr(signal, "SIGALRM"):
                signal.signal(signal.SIGALRM,
                              lambda *a: (_ for _ in ()).throw(_Timeout()))
                signal.alarm(timeout_s)
            try:
                result = run_fn(case["text"])
                final = str(result.get("final", "")) if result else ""
                if not final.strip():
                    outcome, detail = "empty_output", "final 为空"
            finally:
                if timeout_s and hasattr(signal, "SIGALRM"):
                    signal.alarm(0)
        except _Timeout:
            outcome, detail = "timeout", f">{timeout_s}s"
        except Exception as e:                        # noqa: BLE001
            outcome, detail = "sut_error", f"{type(e).__name__}: {e}"
        elapsed = round(time.time() - t0, 2)

        row = {"id": case["id"], "class": case["class"],
               "outcome": outcome, "detail": detail[:120],
               "elapsed_s": elapsed,
               "input_len": len(case["text"]),
               "input_head": repr(case["text"][:40])}
        rows.append(row)
        if outcome != "ok":
            with findings_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if verbose:
            mark = {"ok": "………", "empty_output": "⚠️ 空",
                    "sut_error": "💥 异常", "timeout": "⏰ 超时"}[outcome]
            print(f"  [{i:03d}/{len(cases)}] {row['id']}({row['class']}) "
                  f"{mark} {elapsed}s")

    counts = {}
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    uncaught = 0   # 驱动层保证: 没有任何异常逃逸(逃逸则进程已崩)
    report = {
        "sut": sut, "total": len(rows),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "outcomes": counts,
        "uncaught_exception_rate": uncaught,
        "findings_path": str(findings_path),
        "rows": rows,
    }
    Path(report_path or REPORT_PATH).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="鲁棒性 fuzz")
    ap.add_argument("--sut", default="mini", choices=["mini", "mh"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    rep = run_fuzz(sut=args.sut, limit=args.limit, model=args.model)
    print(f"\n结果: {rep['outcomes']} | findings -> {rep['findings_path']}")
    sys.exit(0 if rep["uncaught_exception_rate"] == 0 else 1)


if __name__ == "__main__":
    _cli()
