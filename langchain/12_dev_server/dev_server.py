"""
12 · 本地服务化总装：dev_server.py 编排脚本（🏁）

零云依赖地把 research_agent 装进 langgraph dev 本地服务并验收：
  1. 启动服务（无云 key），探测 /ok
  2. SDK 场景 A：检索问答 —— 答案含正确来源
  3. SDK 场景 B：删除请求先中断，approve 后工具才执行（审计文件取证）
  4. 追踪回调 JSONL 落盘（llm / 工具事件）
  5. 重启服务后同 thread 状态仍可查（平台持久化）

用法:
  python langchain/12_dev_server/dev_server.py
"""

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
PORT = 2030
URL = f"http://127.0.0.1:{PORT}"
TRACE_PATH = HERE / "trace_server.jsonl"
DELETED_LOG = HERE / "deleted_notes.txt"
SERVER_LOG = Path(os.environ.get("TMPDIR", "/tmp")) / "langchain12_server.log"

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def server_alive(timeout=2):
    try:
        with urlopen(f"{URL}/ok", timeout=timeout):
            return True
    except Exception:
        return False


def start_server():
    log = open(SERVER_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(Path(sys.executable).parent / "langgraph"),
         "dev", "--no-browser", "--port", str(PORT)],
        cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(60):
        if server_alive():
            return proc, log
        if proc.poll() is not None:
            break
        time.sleep(1)
    raise RuntimeError(f"服务未就绪，日志见 {SERVER_LOG}")


def stop_server(proc, log):
    if proc is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=10)
    log.close()


# ============================================================
# SDK 场景
# ============================================================

async def _run_scenarios() -> dict:
    from langgraph_sdk import get_client

    c = get_client(url=URL)
    out = {}

    # A. 检索问答
    t = await c.threads.create()
    r = await c.runs.wait(
        t["thread_id"], "research_agent",
        input={"messages": [{"role": "user",
                             "content": "langgraph dev 本地起服务需要云 key 吗？"}]},
    )
    msgs = r.get("messages", [])
    out["research_thread"] = t["thread_id"]
    out["research_answer"] = str(msgs[-1]["content"]) if msgs else ""
    out["tool_outputs"] = "\n".join(
        str(m.get("content", "")) for m in msgs if m.get("type") == "tool")

    # B. 删除请求 → 中断 → approve
    t2 = await c.threads.create()
    r2 = await c.runs.wait(
        t2["thread_id"], "research_agent",
        input={"messages": [{"role": "user", "content": "请删除笔记 old-note.md"}]},
    )
    out["delete_thread"] = t2["thread_id"]
    out["interrupt"] = r2.get("__interrupt__")
    if out["interrupt"]:
        r3 = await c.runs.wait(
            t2["thread_id"], "research_agent",
            command={"resume": {"decisions": [{"type": "approve"}]}},
        )
        out["after_resume"] = str(r3["messages"][-1]["content"])
    return out


async def _check_persist(thread_id: str) -> dict:
    from langgraph_sdk import get_client

    c = get_client(url=URL)
    st = await c.threads.get_state(thread_id)
    msgs = st["values"].get("messages", [])
    return {"contents": "\n".join(str(m.get("content", "")) for m in msgs),
            "last": str(msgs[-1]["content"]) if msgs else ""}


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 64)
    print("[12] 本地服务化总装：langgraph dev + SDK（真机，零云依赖）")
    print("=" * 64)

    if server_alive():
        print(f"❌ 端口 {PORT} 已有服务在运行，请先停掉再跑本脚本")
        return 1

    # 清掉上一轮的产物与服务持久化残留：dev 会在下次启动重放历史任务，
    # 不清会让上一轮的删除任务重复执行（审计文件两行、验收失败）
    TRACE_PATH.unlink(missing_ok=True)
    DELETED_LOG.unlink(missing_ok=True)
    shutil.rmtree(HERE / ".langgraph_api", ignore_errors=True)

    proc = log = None
    try:
        section("[1] 启动本地服务（无云 key）")
        proc, log = start_server()
        log_text = SERVER_LOG.read_text(encoding="utf-8", errors="ignore")
        print(f"  /ok 存活；日志: {SERVER_LOG}")
        check("langgraph dev 本地起服务成功且无需云 key",
              server_alive() and "No license key or control plane API key" in log_text)

        section("[2] SDK 场景：检索问答 + 危险工具审批")
        out = asyncio.run(_run_scenarios())
        answer = out["research_answer"]
        print(f"  检索问答: {answer[:80]}")
        check("检索工具被调用且答案含正确来源与结论",
              "langchain.md" in out["tool_outputs"]
              and "不需要" in answer and "langchain.md" in answer)

        iv = out["interrupt"]
        print(f"  删除请求中断: {'delete_note' in json.dumps(iv, ensure_ascii=False) if iv else False}")
        check("危险工具执行前中断（中断载荷含 delete_note）",
              bool(iv) and "delete_note" in json.dumps(iv, ensure_ascii=False))

        deleted = DELETED_LOG.read_text(encoding="utf-8").strip() if DELETED_LOG.exists() else ""
        print(f"  approve 后审计文件: {deleted!r} | 最终回复: {out.get('after_resume', '')[:50]}")
        check("approve 后工具才执行（审计文件取证）", deleted == "old-note.md")

        section("[3] 追踪回调 JSONL")
        events = [json.loads(line) for line in TRACE_PATH.read_text(encoding="utf-8").splitlines()]
        kinds = {e["event"] for e in events}
        print(f"  事件数: {len(events)}，类型: {sorted(kinds)}")
        check("llm 与工具事件均落盘 JSONL",
              {"llm_start", "llm_end", "tool_start", "tool_end"} <= kinds)

        section("[4] 重启服务：thread 状态仍在")
        # dev 模式的持久化是周期刷盘：等一拍再停，尽量取到最新检查点
        print("  等待 dev 持久化刷盘（约 8 秒）…")
        time.sleep(8)
        stop_server(proc, log)
        proc = log = None
        check("服务已停止", not server_alive())
        proc, log = start_server()
        persisted = asyncio.run(_check_persist(out["research_thread"]))
        print(f"  重启后同 thread 快照末条: {persisted['last'][:60]}")
        check("重启后同 thread 状态仍可查（平台持久化）",
              "不需要" in persisted["contents"])
    finally:
        stop_server(proc, log)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
