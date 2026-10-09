"""gate — CI 门禁分级: 变更 -> 档位路由 -> 退出码 (docs/aitest.md 项目 20)

按变更文件路由 runner 档位, 跑完按结果给 CI 退出码:
    只改 datasets/payloads -> smoke(分钟级)
    改 SUT/测试台代码      -> full(全量)
    未知变更               -> full(fail-safe)

    route(files) -> "smoke"|"full"
    gate(files=None, dry_run=False) -> (level, report, exit_code, reasons)
    python3 -m testbench.gate selftest      # 用假 diff 自检路由与退出码
    python3 -m testbench.gate run [--files a,b] [--dry-run]
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(AITEST_DIR)

sys.path.insert(0, AITEST_DIR)

SMOKE_PREFIXES = ("aitest/datasets/", "aitest/payloads/")
# 触碰这些前缀的变更视为影响被测行为, 必须全量
FULL_PREFIXES = ("harness/", "qa/", "agents/", "aitest/testbench/",
                 "aitest/tests/", "aitest/final_checkup/", "langchain/")


def _is_full(f):
    """SUT/测试台代码变更(含 aitest 根下脚本与 Makefile) -> full。"""
    if any(f.startswith(p) for p in FULL_PREFIXES):
        return True
    if f.startswith("aitest/") and f.count("/") == 1:
        return True                      # aitest/xxx.py, aitest/Makefile
    return False


def route(files):
    """变更文件列表 -> 档位。未知一律 full(宁可多跑)。"""
    files = [f.strip() for f in files if f and f.strip()]
    if not files:
        return "full"
    only_smoke = True
    for f in files:
        if _is_full(f):
            return "full"
        if not any(f.startswith(p) for p in SMOKE_PREFIXES):
            only_smoke = False
    return "smoke" if only_smoke else "full"


def changed_files():
    """git 变更文件(未提交 + 最近一次提交); 取不到则空列表。"""
    names = set()
    for args in (["diff", "--name-only"], ["diff", "--name-only", "HEAD~1"]):
        try:
            out = subprocess.run(["git", *args], cwd=REPO_ROOT,
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0:
                names.update(l for l in out.stdout.splitlines() if l.strip())
        except Exception:                        # noqa: BLE001
            pass
    return sorted(names)


def decide(report):
    """机制类模块结论 -> CI 退出码。返回 (code, reasons)。"""
    reasons = []
    for m in report.get("modules", []):
        if m["status"] == "error":
            reasons.append(f"{m['name']}: 模块崩溃")
        elif m["status"] == "ok" and m.get("passed") is False:
            reasons.append(f"{m['name']}: 机制检查未过")
    return (1 if reasons else 0), reasons


def gate(files=None, dry_run=False, verbose=True):
    """路由 -> (可选)跑 runner -> 退出码。返回 dict。"""
    files = files if files is not None else changed_files()
    level = route(files)
    if verbose:
        print(f"变更文件({len(files)}): {files[:6]}{' ...' if len(files) > 6 else ''}")
        print(f"路由档位: {level}")
    if dry_run:
        return {"files": files, "level": level, "exit_code": 0,
                "reasons": ["dry-run 未执行 runner"]}
    from testbench import runner as R
    report = R.run_all(level=level, verbose=verbose)
    out = R.save_and_validate(report)
    code, reasons = decide(report)
    if verbose:
        print(f"结果 -> {out}")
        print(f"CI 退出码: {code} | 原因: {reasons or '无'}")
    return {"files": files, "level": level, "exit_code": code,
            "reasons": reasons, "report": report}


# ============================================================
# 自检: 假 diff 两态 (验收: selftest 全绿)
# ============================================================

def selftest(verbose=True):
    checks = []
    cases = [
        (["aitest/datasets/tasks.yaml"], "smoke"),
        (["aitest/payloads/jailbreak.yaml", "aitest/datasets/x.yaml"],
         "smoke"),
        (["harness/mh/loop.py"], "full"),
        (["aitest/testbench/runner.py"], "full"),
        (["README.md"], "full"),               # 未知 -> fail-safe
        ([], "full"),                          # 空变更 -> full
    ]
    for files, expect in cases:
        got = route(files)
        ok = got == expect
        checks.append((f"route({files or '空'}) == {expect}", ok))
        if verbose:
            print(f"  {'✅' if ok else '❌'} route({files or '空'}) = {got}")

    fake_ok = {"modules": [{"name": "security", "status": "ok",
                            "passed": True}]}
    fake_bad = {"modules": [{"name": "security", "status": "ok",
                             "passed": False},
                            {"name": "contract", "status": "error",
                             "passed": False}]}
    code, _ = decide(fake_ok)
    checks.append(("全过 -> 退出码 0", code == 0))
    code, reasons = decide(fake_bad)
    checks.append(("机制未过/崩溃 -> 退出码 1", code == 1 and len(reasons) == 2))
    if verbose:
        print(f"  ✅ decide: 全过=0, 双违规=1({len(reasons)} 条原因)")

    passed = sum(1 for _, ok in checks if ok)
    if verbose:
        print(f"\nselftest: {passed}/{len(checks)} 通过")
    return passed == len(checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="CI 门禁分级")
    ap.add_argument("cmd", choices=["run", "selftest"])
    ap.add_argument("--files", default=None, help="逗号分隔的变更文件(调试用)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "selftest":
        sys.exit(0 if selftest() else 1)
    files = args.files.split(",") if args.files else None
    res = gate(files=files, dry_run=args.dry_run)
    sys.exit(res["exit_code"])


if __name__ == "__main__":
    main()
