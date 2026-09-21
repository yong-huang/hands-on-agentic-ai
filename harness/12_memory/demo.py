#!/usr/bin/env python3
"""12 · 跨会话记忆 — A 学到 → B 遵循 → C 遗忘 → D 验证 (docs/harness.md 项目 12)

偏好选用"异常可核查"的事实(文件头注释标记), 避免模型凭习惯押中:
  会话 A: 用户声明偏好"所有 Python 文件头部必须加注释 # PROJECT: mh-demo"
          → 收尾 consolidate 自动沉淀进 MEMORY.md
  会话 B: 全新会话直接下发任务"创建 calc.py" → 断言文件头带标记
  会话 C: forget("mh-demo") 遗忘 → 断言 recall() 为空(确定性)
  会话 D: 同任务再跑一次 → 观察是否还遵循(信息性, 模型自发行为不硬断言)

用法:
  python3 demo.py            # 真机四会话
  MOCK=1 python3 demo.py     # 离线管道自检
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh import llm as mh_llm  # noqa: E402
from mh import loop  # noqa: E402
from mh.memory import Memory, consolidate, system_with_memory  # noqa: E402
from mh.sandbox import run  # noqa: E402
from mh.tools import Registry, tool  # noqa: E402

BASE_SYSTEM = "你是严谨的运维助手, 通过工具完成任务。/no_think"
MARK = "# PROJECT: mh-demo"


def build_tools() -> dict:
    reg = Registry()

    @tool
    def run_bash(command: str, cwd: str = None) -> str:
        """在任务目录执行一条 bash 命令(沙箱保护)。"""
        ok, out = run(command, cwd=cwd or ".")
        return out if ok else f"[sandbox] {out}"

    reg.add(run_bash)
    return reg.to_loop_tools()


def session(tag: str, task: str, sandbox: Path, memory: Memory,
            chat_fn=None) -> dict:
    """跑一个会话: 注入记忆 → 执行 → 收尾沉淀。"""
    msgs = [{"role": "system", "content": system_with_memory(BASE_SYSTEM, memory)},
            {"role": "user", "content": task}]
    result = loop.run_agent(task, build_tools(), max_turns=6,
                            chat_fn=chat_fn or mh_llm.chat_with_retry,
                            cwd=str(sandbox), messages=msgs)
    print(f"[{tag}] 轮次 {result['turns']} | {result['final'][:60]}")
    return result


def mock_chat(messages, tools=None, **kw):
    last = str(messages[-1].get("content", ""))
    if "提取值得跨会话" in last:
        return {"role": "assistant", "content": "- 所有 Python 文件头部必须加注释 # PROJECT: mh-demo"}
    return {"role": "assistant", "content": "好的"}


TASK = "创建 hello.py, 内容为打印 hi"


def main():
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    is_mock = os.environ.get("MOCK") == "1"
    chat = mock_chat if is_mock else mh_llm.chat_with_retry
    root = Path(tempfile.mkdtemp(prefix="mh12_"))
    memory = Memory(root / "MEMORY.md")
    results = {}

    # 会话 A: 学到偏好
    sbA = root / "A"
    sbA.mkdir()
    task_a = (f"{TASK}。\n"
              "另外记住一个项目约定: 所有 Python 文件头部必须加注释 "
              f"{MARK}。")
    rA = session("A 学偏好", task_a, sbA, memory, chat)
    added = consolidate(chat, rA["messages"], memory)
    print(f"  沉淀: {added} | MEMORY.md 共 {len(memory.lines)} 条")
    results["A 沉淀"] = any("mh-demo" in a for a in added)

    # 会话 B: 无提示遵循
    sbB = root / "B"
    sbB.mkdir()
    rB = session("B 遵循", "创建 calc.py, 实现两数相加", sbB, memory, chat)
    fB = sbB / "calc.py"
    followed = fB.is_file() and MARK in fB.read_text()
    print(f"  calc.py 头部带标记: {'✅' if followed else '❌'}")
    results["B 遵循"] = followed

    # 会话 C: 遗忘(确定性)
    removed = memory.forget("mh-demo")
    results["C 遗忘"] = removed >= 1 and memory.recall() == ""
    print(f"  forget 移除 {removed} 条, recall 清空: {'✅' if results['C 遗忘'] else '❌'}")

    # 会话 D: 观察性(不硬断言——模型可能自发写标记)
    sbD = root / "D"
    sbD.mkdir()
    rD = session("D 遗忘后", "创建 calc.py, 实现两数相加", sbD, memory, chat)
    fD = sbD / "calc.py"
    still = fD.is_file() and MARK in fD.read_text()
    print(f"  遗忘后自发写标记(信息性): {'是(模型习惯)' if still else '否'}")

    print("\n===== 验收 =====")
    for k, v in results.items():
        print(f"  {k}: {'✅' if v else '❌'}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
