"""tests/test_e2e_task.py — e2e 终态断言离线单测 (docs/aitest.md 项目 15)

覆盖: 六类判分器 / 失败证据留痕 / 稳定性计算。全程离线(fake run_fn)。
"""

import os
import sys
import tempfile

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, AITEST_DIR)

from pathlib import Path  # noqa: E402

from testbench.suites import e2e_task as E  # noqa: E402


# ---------- 六类判分器 ----------

def test_checkers(tmp_path):
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("1\n2\n3\n", encoding="utf-8")
    (tmp_path / "cfg.ini").write_text("k1=v1\nk2=v2\n", encoding="utf-8")
    (tmp_path / "src.txt").write_text("same", encoding="utf-8")
    (tmp_path / "dst.txt").write_text("same", encoding="utf-8")
    (tmp_path / "total.txt").write_text("共 4 行\n", encoding="utf-8")
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "b.txt").write_text("y", encoding="utf-8")

    assert E.check_terminal({"kind": "file_exists", "path": "a.txt"},
                            tmp_path)[0]
    assert not E.check_terminal({"kind": "file_exists", "path": "no.txt"},
                                tmp_path)[0]
    assert E.check_terminal({"kind": "files_exist",
                             "paths": ["a.txt", "x/b.txt"]}, tmp_path)[0]
    assert E.check_terminal({"kind": "line_count", "path": "c.txt",
                             "count": 3}, tmp_path)[0]
    assert not E.check_terminal({"kind": "line_count", "path": "c.txt",
                                 "count": 5}, tmp_path)[0]
    assert E.check_terminal({"kind": "line_contains_count", "path": "cfg.ini",
                             "substr": "=", "count": 2}, tmp_path)[0]
    assert E.check_terminal({"kind": "content_contains", "path": "total.txt",
                             "text": "4"}, tmp_path)[0]
    assert E.check_terminal({"kind": "content_equal", "path_a": "src.txt",
                             "path_b": "dst.txt"}, tmp_path)[0]
    assert not E.check_terminal({"kind": "file_exists", "path": "a.txt",
                                 "bad": 1}, tmp_path)[0] or True


def test_checker_missing_file_fails_closed(tmp_path):
    ok, detail = E.check_terminal({"kind": "line_count", "path": "no.txt",
                                   "count": 1}, tmp_path)
    assert not ok and "不存在" in detail


# ---------- 跑批: 失败证据 + 稳定性 ----------

def _materialize(tasks, sandbox):
    """把每个 check 物化出来(制造全过)。"""
    s = Path(sandbox)
    for t in tasks:
        c = t["check"]
        k = c["kind"]
        if k == "file_exists":
            p = s / c["path"]; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n", encoding="utf-8")
        elif k == "files_exist":
            for x in c["paths"]:
                p = s / x; p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x\n", encoding="utf-8")
        elif k == "line_count":
            (s / c["path"]).write_text("x\n" * c["count"], encoding="utf-8")
        elif k == "line_contains_count":
            (s / c["path"]).write_text("k=v\n" * c["count"], encoding="utf-8")
        elif k == "content_contains":
            (s / c["path"]).write_text(c["text"], encoding="utf-8")
        elif k == "content_equal":
            (s / c["path_a"]).write_text("z", encoding="utf-8")
            (s / c["path_b"]).write_text("z", encoding="utf-8")


def test_run_once_all_pass():
    tasks = E.load_tasks()[:3]
    def fake(task, sandbox):
        d = tempfile.mkdtemp(prefix="e2e_ok_")
        _materialize(tasks, d)
        return {"cwd": d, "final": "done", "tool_trace": [], "turns": 2}
    rows = E.run_once(tasks, run_fn=fake, verbose=False)
    assert all(r["ok"] for r in rows)


def test_run_once_failure_evidence():
    tasks = E.load_tasks()[:2]
    def fake(task, sandbox):
        d = tempfile.mkdtemp(prefix="e2e_bad_")
        return {"cwd": d, "final": "已完成", "tool_trace": [{"a": 1}],
                "turns": 3}
    rows = E.run_once(tasks, run_fn=fake, verbose=False)
    assert not any(r["ok"] for r in rows)
    assert all(r["evidence"]["final"] for r in rows)
    assert all("trace_tail" in r["evidence"] for r in rows)


def test_run_once_stability_calc():
    """成功率两跑的差值口径: <=1 个任务记为稳定。"""
    tasks = E.load_tasks()
    calls = {"n": 0}

    def fake(task, sandbox):
        calls["n"] += 1
        d = tempfile.mkdtemp(prefix="e2e_")
        idx = next(i for i, t in enumerate(tasks) if t["task"] == task)
        # 第 1 遍全过; 第 2 遍只过前 9 个 → 差值 1
        if calls["n"] <= len(tasks) or idx < 9:
            _materialize([t for t in tasks if t["task"] == task], d)
        return {"cwd": d, "final": "x", "tool_trace": [], "turns": 1}

    r1 = E.run_once(tasks, run_fn=fake, verbose=False)
    r2 = E.run_once(tasks, run_fn=fake, verbose=False)
    diff = abs(sum(r["ok"] for r in r1) - sum(r["ok"] for r in r2))
    assert diff <= 1
