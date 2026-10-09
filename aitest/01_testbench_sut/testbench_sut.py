#!/usr/bin/env python3
"""01 · 测试台骨架 + SUT 适配层 — aitest 线首航 (docs/aitest.md 项目 1)

验收: 一条命令演示"两个被测对象、一个调用接口"——
  probe   探活 Ollama(真实模式的前置检查, 不在线不硬跑)
  mock    离线层: 脚本化 chat_fn 驱动 mh.loop + mini 模板链路
  real    真实层: mh 真调 LLM 写文件, 断言"声称完成=磁盘真变化"
  pytest  跑测试台冒烟套件(MOCK=1)
无参数按 probe → mock → real → pytest 全流程走; Ollama 不在线时 real
诚实跳过并给出启动指引, 其余照常。

用法:
  python3 testbench_sut.py            # 全流程(含真机, qwen3.8 单任务约 30s)
  python3 testbench_sut.py mock       # 只看离线层
  LLM_MODEL=qwen3:4b python3 testbench_sut.py real   # 换快模型
"""

import os
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR.parent))          # aitest/ → testbench 可导入

from testbench import suts  # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_probe():
    step("probe", "Ollama 探活(真实模式前置检查)")
    alive = suts.ollama_alive()
    print(f"  http://localhost:11434/v1/models -> {'存活 ✅' if alive else '不在线 ❌'}")
    print(f"  LLM_MODEL = {os.environ.get('LLM_MODEL', 'qwen3.8:latest (默认)')}")
    return alive


def do_mock():
    step("mock", "离线层: 同一个 run_sut 接口, 两个被测对象")
    r_mh = suts.run_sut(chat_fn=suts.mock_chat_fn())
    print("  mh  (脚本剧本):", suts.result_summary(r_mh))
    r_mini = suts.run_sut(sut="mini")
    print("  mini(模板链路):", suts.result_summary(r_mini))
    assert r_mh["final"] and r_mini["all_ok"], "离线层自检失败"
    print("  断言: mh 收敛有 final ✅ / mini 全链路自评 ok ✅")


def do_real():
    step("real", "真实层: mh 真调 LLM, 声称完成必须等于磁盘真变化")
    if not suts.ollama_alive():
        print("  ⚠️ Ollama 不在线, 真实层诚实跳过 —— 这是预期行为不是故障")
        print("     启动: ollama serve (或打开 Ollama.app) 后重跑 real")
        return
    r = suts.run_sut()
    print("  模型回复:", suts.result_summary(r))
    hi = Path(r["cwd"]) / "hi.txt"
    content = hi.read_text().strip() if hi.exists() else "(文件不存在)"
    print(f"  磁盘取证: {hi} -> {content!r}")
    assert r["final"], "无最终回答"
    assert content == "ok", f"SUT 声称完成但磁盘不符: {content!r} —— 假完成被抓"
    print("  断言: final 非空 ✅ / hi.txt 内容=ok ✅ (测试台第一次抓住'真完成')")


def do_pytest():
    step("pytest", "冒烟套件(MOCK=1, 离线)")
    env = dict(os.environ, MOCK="1")
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(LAB_DIR.parent), env=env, capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0, "冒烟套件未全绿"


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    table = {"probe": do_probe, "mock": do_mock,
             "real": do_real, "pytest": do_pytest}
    if target in table:
        table[target]()
    elif target == "all":
        alive = do_probe()
        do_mock()
        do_real()
        do_pytest()
        print("\n=====> 项目 1 验收完成: "
              + ("含真实层 ✅" if alive else "离线层 ✅ (真实层因 Ollama 不在线跳过)"))
    else:
        print("可用: probe | mock | real | pytest | all", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
