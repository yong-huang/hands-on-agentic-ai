"""report — 评测报告生成器 (docs/aitest.md 项目 19)

读统一 runner 的 results.json, 用 Python 字符串模板生成单文件 report.html:
五区块(总览/评测/安全/行为/性能), 纯内联 CSS, 零前端依赖。
劣化/超标/崩溃项红色高亮, skipped 灰色列出原因。

    build_html(report) -> str
    verify(html, report) -> [(检查项, ok)]   抽查数字与 JSON 一致
    python3 -m testbench.report results.json [--out x.html] [--verify]
"""

import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(HERE)
DEFAULT_IN = os.path.join(AITEST_DIR, "results", "run_results.json")
DEFAULT_OUT = os.path.join(AITEST_DIR, "results", "report.html")

sys.path.insert(0, AITEST_DIR)

CSS = """
body{font-family:-apple-system,'PingFang SC',sans-serif;margin:0;background:#f5f6f8;color:#1c2430}
.wrap{max-width:920px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 4px}
.meta{color:#667;font-size:13px;margin-bottom:20px}
.cards{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:10px 14px;font-size:13px}
.card b{font-size:18px;display:block}
section{background:#fff;border:1px solid #e3e6ea;border-radius:10px;margin-bottom:16px;padding:16px 20px}
h2{font-size:16px;margin:0 0 10px;border-left:4px solid #4a7dfc;padding-left:8px}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border-bottom:1px solid #eef0f3;text-align:left;padding:6px 8px}
.bad{color:#c0392b;font-weight:600}
.good{color:#1e8e4e}
.gray{color:#98a2ad}
.small{color:#667;font-size:12px}
"""


def _fmt(v):
    if isinstance(v, dict):
        return " / ".join(f"{k}={_fmt(x)}" for k, x in v.items())
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _module_map(report):
    return {m["name"]: m for m in report["modules"]}


def _status_class(m):
    if m["status"] == "error":
        return "bad"
    if m["status"] == "skipped":
        return "gray"
    if m.get("passed") is False:
        return "bad"
    return "good"


def build_html(report):
    mods = _module_map(report)
    meta = report["meta"]
    ok_n = sum(1 for m in report["modules"] if m["status"] == "ok")
    err_n = sum(1 for m in report["modules"] if m["status"] == "error")
    skip_n = sum(1 for m in report["modules"] if m["status"] == "skipped")

    rows = []
    for m in report["modules"]:
        cls = _status_class(m)
        rows.append(
            f"<tr><td>{m['name']}</td>"
            f"<td class='{cls}'>{m['status']}</td>"
            f"<td>{_fmt(m.get('passed'))}</td>"
            f"<td>{_fmt(m.get('metrics'))}</td>"
            f"<td>{m.get('elapsed_s')}s</td>"
            f"<td class='small'>{m.get('detail', '')}</td></tr>")

    def sec(title, sid, body):
        return f"<section id='{sid}'><h2>{title}</h2>{body}</section>"

    overview = (
        f"<div class='cards'>"
        f"<div class='card'><b>{ok_n}</b>ok</div>"
        f"<div class='card'><b class='bad'>{err_n}</b>error</div>"
        f"<div class='card'><b class='gray'>{skip_n}</b>skipped</div>"
        f"<div class='card'><b>{meta['elapsed_s']}s</b>总耗时</div></div>"
        f"<table><tr><th>模块</th><th>状态</th><th>passed</th>"
        f"<th>metrics</th><th>耗时</th><th>detail</th></tr>{''.join(rows)}</table>")

    def mrow(name, key, val):
        return f"<tr><td>{name}</td><td>{key}</td><td>{_fmt(val)}</td></tr>"

    ev = mods.get("eval", {}).get("metrics", {})
    rg = mods.get("regression", {}).get("metrics", {})
    eval_body = "<table><tr><th>来源</th><th>指标</th><th>值</th></tr>"
    eval_body += mrow("eval", "overall_pass_rate", ev.get("overall_pass_rate"))
    for k, v in (ev.get("rates") or {}).items():
        eval_body += mrow("eval", f"rate.{k}", v)
    for k, v in rg.items():
        eval_body += mrow("regression", k, v)
    eval_body += "</table>"

    se = mods.get("security", {}).get("metrics", {})
    sec_body = "<table><tr><th>维度</th><th>值</th></tr>"
    for k, v in se.items():
        sec_body += f"<tr><td>{k}</td><td>{_fmt(v)}</td></tr>"
    sec_body += "</table>"

    beh = []
    ct = mods.get("contract", {})
    beh.append(f"<p class='small'>契约（违规数）: {_fmt(ct.get('metrics'))}"
               f" <span class='{_status_class(ct)}'>passed={ct.get('passed')}</span></p>")
    e2 = mods.get("e2e", {}).get("metrics", {})
    beh.append(f"<p class='small'>e2e 成功率: {e2.get('success')}/{e2.get('total')}"
               f" = {e2.get('rate')}</p>")
    tr = mods.get("trajectory", {}).get("metrics", {})
    beh.append(f"<p class='small'>轨迹自证: fast={tr.get('fast')} "
               f"slow={tr.get('slow')} loop={tr.get('loop')}</p>")
    behavior_body = "".join(beh)

    pf = mods.get("perf", {}).get("metrics", {})
    perf_body = "<table><tr><th>指标</th><th>值</th></tr>"
    for k, v in pf.items():
        perf_body += f"<tr><td>{k}</td><td>{_fmt(v)}</td></tr>"
    perf_body += "</table>"

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>aitest 评测报告</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>aitest 评测报告</h1>
<div class="meta">SUT={meta['sut']} · 档位={meta['level']} · 模型=
{meta.get('model')} · 生成于 {meta['generated_at']}</div>
{sec('总览', 'overview', overview)}
{sec('评测', 'eval', eval_body)}
{sec('安全', 'security', sec_body)}
{sec('行为', 'behavior', behavior_body)}
{sec('性能', 'performance', perf_body)}
</div></body></html>"""


def verify(html, report, samples=3):
    """抽查 samples 个数字: 其 JSON 原值字符串应出现在 HTML 中。"""
    mods = _module_map(report)
    candidates = []
    ev = mods.get("eval", {}).get("metrics", {})
    if ev.get("overall_pass_rate") is not None:
        candidates.append(("eval.overall_pass_rate", ev["overall_pass_rate"]))
    se = mods.get("security", {}).get("metrics", {})
    for k, v in se.items():
        if v is not None:
            candidates.append((f"security.{k}", v))
            break
    e2 = mods.get("e2e", {}).get("metrics", {})
    if e2.get("success") is not None:
        candidates.append(("e2e.success", e2["success"]))
    pf = mods.get("perf", {}).get("metrics", {})
    if pf.get("p50_s") is not None:
        candidates.append(("perf.p50_s", pf["p50_s"]))
    checks = [(name, _fmt(val) in html) for name, val in candidates[:samples]]
    return checks


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="评测报告生成器")
    ap.add_argument("results", nargs="?", default=DEFAULT_IN)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)

    report = json.loads(Path(args.results).read_text(encoding="utf-8"))
    html = build_html(report)
    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"报告 -> {out} ({len(html)} 字节, 五区块)")

    if args.verify:
        checks = verify(html, report)
        for name, ok in checks:
            print(f"  {'✅' if ok else '❌'} 抽查 {name}")
        sys.exit(0 if all(ok for _, ok in checks) else 1)


if __name__ == "__main__":
    main()
