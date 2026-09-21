"""mh.sandbox — 执行安全层 (项目 06)

三层防御(词法层 → 进程层 → 输出层):
  1. 路径爬升守卫: 命令含 `../` 直接拒绝(词法防御; 容器级隔离见 README 诚实标注)
  2. 进程组超时杀死: start_new_session + killpg, 死循环 3s 内被处决且不留孤儿
  3. 输出截断: 超 max_bytes 截断并告知模型(防 context 爆炸, 10 项目的前置)

run(command, cwd, timeout, max_bytes) -> (ok: bool, output: str) —— 永不抛异常,
返回的 output 永远是"可回喂给模型"的文本。
"""

import os
import signal
import subprocess

DEFAULT_TIMEOUT = 3
DEFAULT_MAX_BYTES = 8192

_GUARDS = [
    ("../", "路径爬升(../): 沙箱只允许在工作目录内活动"),
    ("..\\", "路径爬升(..\\): 沙箱只允许在工作目录内活动"),
    ("rm -rf /", "递归删除根目录已被权限守卫拒绝"),
    (":(){ :|:& };:", "fork 炸弹已被权限守卫拒绝"),
]


def guard(command: str):
    """词法守卫: 返回 None 表示放行, 否则返回拒绝原因。"""
    for pattern, reason in _GUARDS:
        if pattern in command:
            return reason
    return None


def run(command: str, cwd: str, timeout: int = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES) -> tuple:
    """执行一条 bash 命令: 守卫 → 进程组限时 → 输出截断。"""
    reason = guard(command)
    if reason:
        return False, f"[拒绝] {reason}"
    p = subprocess.Popen(["bash", "-c", command], cwd=cwd,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        status = f"[退出码 {p.returncode}]" if p.returncode else ""
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)  # 杀整个进程组, 不留孤儿
        out, _ = p.communicate()
        status = f"[错误: 超时 {timeout}s, 进程组已杀死]"
    out = out or ""
    if len(out.encode("utf-8")) > max_bytes:
        out = (out.encode("utf-8")[:max_bytes]).decode("utf-8", "ignore")
        out += f"\n[输出已截断: 原始输出超过 {max_bytes} 字节, 只保留前 {max_bytes} 字节]"
    ok = status == ""
    return ok, (out + ("" if ok else "\n" + status)).strip() or status
