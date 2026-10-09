#!/usr/bin/env python3
"""05 · 语义断言 — embedding 相似度阈值 (docs/aitest.md 项目 5)

验收: 一条命令演示"阈值不是拍的，是标出来的"——
  probe     embedding 端点探活(nomic-embed-text)
  calibrate 10 组等价改写 + 10 组同域无关, 扫阈值曲线取最优点
  selftest  选定阈值下输出两个 10 格矩阵, 双侧 ≥9/10(硬验收)
  live      真机三连: 等价改写 PASS / 同域无关 FAIL / 空串边界
  pytest    纯函数测试(cosine/阈值/标定集形状)
Ollama 不在线时 calibrate/selftest/live 诚实跳过。

用法:
  python3 semantic_assert.py            # 全流程
  python3 semantic_assert.py selftest   # 只跑标定+矩阵(真机)
"""

import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
sys.path.insert(0, str(AITEST_DIR))

import os as _os

_os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
_os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from testbench.asserts import semantic as SEM  # noqa: E402
from testbench.suts import ollama_alive  # noqa: E402


def step(name, msg):
    print(f"\n=====> [{name}] {msg}")


def do_probe():
    step("probe", "embedding 端点探活")
    if not ollama_alive():
        print("  ⚠️ Ollama 不在线 —— 真机段诚实跳过(启动: ollama serve)")
        return False
    vec = SEM.embed("探活")
    print(f"  {SEM.EMBED_MODEL} -> {len(vec)} 维 ✅")
    return True


def do_calibrate():
    step("calibrate", "扫描阈值曲线(10 改写 + 10 无关)")
    threshold, curve, _, _ = SEM.calibrate()
    print(f"  选定阈值: {threshold}")


def do_selftest():
    step("selftest", "双侧矩阵(验收口径: 通过 ≥9 且 拒绝 ≥9)")
    assert SEM.selftest(), "语义断言自检未达双侧 ≥9/10"


def do_live():
    step("live", "真机三连: 改写 PASS / 无关 FAIL / 阈值复用")
    threshold = SEM.calibrate(verbose=False)[0]
    r1 = SEM.check("回归就是改完代码再跑一遍旧用例防止改坏",
                   "回归测试是在软件修改后重新运行已有测试，确认原有功能未被破坏",
                   threshold)
    print(f"  等价改写: {r1}  -> {'✅' if r1.ok else '❌'}")
    r2 = SEM.check("HTTP 默认端口是 80",
                   "回归测试是在软件修改后重新运行已有测试，确认原有功能未被破坏",
                   threshold)
    print(f"  同域无关: {r2}  -> {'✅' if not r2.ok else '❌(漏拒)'}")
    assert r1.ok and not r2.ok
    print(f"  阈值 {threshold} 由标定曲线给出, 断言零拍脑袋 ✅")


def do_pytest():
    step("pytest", "纯函数测试(离线)")
    p = subprocess.run([sys.executable, "-m", "pytest",
                        "tests/test_semantic_assert.py", "-q"],
                       cwd=str(AITEST_DIR), capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
    print("  " + (tail[0] if tail else "(无输出)"))
    assert p.returncode == 0


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    table = {"probe": do_probe, "calibrate": do_calibrate,
             "selftest": do_selftest, "live": do_live, "pytest": do_pytest}
    online = None
    if target == "all":
        online = do_probe()
        if online:
            do_calibrate()
            do_selftest()
            do_live()
        do_pytest()
        print("\n=====> 项目 5 验收完成: 语义断言 "
              + ("✅ 真机标定" if online else "✅ 离线层(真机段跳过)"))
    elif target in table:
        table[target]()
    else:
        print("可用: probe | calibrate | selftest | live | pytest | all",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
