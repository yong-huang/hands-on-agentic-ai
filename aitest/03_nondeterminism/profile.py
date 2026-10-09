#!/usr/bin/env python3
"""03 · 非确定性画像 — 同一 prompt 的方差报告 (docs/aitest.md 项目 3)

回答一个问题: "同一个 prompt 问 30 遍, SUT 背后的 LLM 输出有多稳?"
这是后续一切断言阈值的标定依据 —— 阈值不能拍脑袋, 要按实测分布定。

做法:
  对同一 prompt 在 temperature=0 与 0.8 两组各采样 30 次(默认),
  统计两个指标 + 输出 REPORT.md:
    字面一致率     众数回答占样本比例(完全相同的输出占比)
    语义近邻一致率 两两相似度均值(difflib ratio, 容忍措辞差异)
  验收口径: temp=0 组的字面一致率 > temp=0.8 组, 脚本自断言, 否则 exit 1。

采样走 qa/llm.py 的 OpenAI 兼容约定(环境变量切换, 默认本机 Ollama);
默认模型 qwen3:4b(2.5GB, 提速画像够用); MOCK=1 用预置输出演示统计管道,
REPORT 会标注"MOCK 演示", 不冒充真机数据。

用法:
  python3 profile.py                 # 真机: 双温度各 30 次, qwen3:4b 约 3-5 分钟
  python3 profile.py --n 5           # 快速冒烟
  MOCK=1 python3 profile.py          # 离线演示统计逻辑
  python3 profile.py --prompt "..."  # 自选问题
"""

import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
AITEST_DIR = LAB_DIR.parent
REPO_ROOT = AITEST_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "qa"))

os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

import llm as qa_llm  # noqa: E402  复用 qa 线 OpenAI 兼容客户端

DEFAULT_PROMPT = "用一句话回答: 什么是回归测试? /no_think"
DEFAULT_MODEL = "qwen3:4b"


# ============================================================
# 指标: 纯函数, tests/test_profile.py 直接可测
# ============================================================

def exact_consistency(outputs):
    """字面一致率 = 众数回答出现次数 / 样本数。"""
    if not outputs:
        return 0.0
    return Counter(outputs).most_common(1)[0][1] / len(outputs)


def semantic_consistency(outputs):
    """语义近邻一致率 = 两两相似度(difflib ratio)均值, 空表/单元素按 1.0。"""
    n = len(outputs)
    if n <= 1:
        return 1.0
    total, pairs = 0.0, 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = outputs[i], outputs[j]
            if a == b:
                total += 1.0          # 众数场景占大头的快速通道
            else:
                total += SequenceMatcher(None, a, b).ratio()
            pairs += 1
    return total / pairs


def summarize(outputs):
    """一组采样的一行指标 dict。"""
    return {
        "exact": round(exact_consistency(outputs), 3),
        "semantic": round(semantic_consistency(outputs), 3),
        "distinct": len(set(outputs)),
        "modal": Counter(outputs).most_common(1)[0][0][:60],
    }


# ============================================================
# 采样
# ============================================================

def sample_group(temp, n, prompt, model):
    """真机采样: 复用 qa_llm.chat, 单次失败重试一次, 记录耗时。"""
    old = os.environ.get("LLM_MODEL")
    os.environ["LLM_MODEL"] = model
    outs, t0 = [], time.time()
    try:
        for i in range(n):
            text = None
            for attempt in (1, 2):
                try:
                    text = qa_llm.chat([{"role": "user", "content": prompt}],
                                       temperature=temp, num_predict=400)
                    break
                except Exception as e:  # noqa: BLE001 —— 网络抖动重试一次
                    if attempt == 2:
                        raise
                    print(f"  [temp={temp} #{i + 1}] 第 1 次失败({e}), 重试...")
            outs.append(text or "")
            print(f"  [temp={temp}] {i + 1}/{n} {len(outs[-1])} 字")
    finally:
        if old is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = old
    return outs, round(time.time() - t0, 1)


def mock_group(kind, n):
    """离线演示: 预置输出池按确定次序取, 模拟'稳/不稳'两种分布。"""
    stable = ["回归测试是在改动后重新执行既有测试，确认原有功能未被破坏。"] * n
    stable[-1] = "回归测试指改动后重跑旧用例，防止新修改引入问题。"
    stable[-2] = "回归测试指改动后重跑旧用例，防止新修改引入问题。"
    varied_pool = [
        "回归测试是改代码后再跑一遍旧用例的做法。",
        "回归测试用于确认新改动没有破坏既有功能。",
        "所谓回归测试，就是在软件修改后重新执行测试用例。",
        "回归测试：改动后对已有功能重新验证的过程。",
        "回归测试就是防退步的测试，改完代码跑一遍旧用例。",
        "回归测试检查被修改过的程序是否仍能正常工作。",
        "改动引发旧功能失效称为回归，回归测试就是防它的。",
        "回归测试指对系统进行变更后的重复测试。",
    ]
    varied = [varied_pool[i % len(varied_pool)] for i in range(n)]
    outs = stable if kind == 0 else varied
    return list(outs), 0.0


# ============================================================
# 报告
# ============================================================

def write_report(prompt, model, n, s0, s8, elapsed0, elapsed8, mock, path):
    """生成 REPORT.md, 返回两组字面一致率(供自断言)。"""
    mode = "MOCK 演示(非真机数据)" if mock else f"真机实测({model})"
    lines = [
        "# 03 · 非确定性画像 REPORT",
        "",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 模式: {mode} · 每组样本 n={n}",
        f"- prompt: `{prompt}`",
        "",
        "| 指标 | temperature=0 | temperature=0.8 |",
        "|:--|:--:|:--:|",
        f"| 字面一致率(众数占比) | {s0['exact']} | {s8['exact']} |",
        f"| 语义近邻一致率(两两相似均值) | {s0['semantic']} | {s8['semantic']} |",
        f"| 不同输出数 | {s0['distinct']} | {s8['distinct']} |",
        f"| 采样耗时(秒) | {elapsed0} | {elapsed8} |",
        "",
        f"众数输出(temp=0): {s0['modal']}...",
        "",
        "## 对测试断言的 3 条启示",
        "",
    ]
    if s0["exact"] >= 1.0:
        lines.append(
            f"1. temperature=0 本轮 {n}/{n} 输出全同——但这不是契约: 换模型/版本/负载后"
            " temp=0 仍可能有方差, 断言永远不要对 LLM 输出做精确全文匹配, 除非走 MOCK。")
    else:
        lines.append(
            f"1. temperature=0 不等于确定性: 字面一致率 {s0['exact']} 而非 1.0,"
            " 断言永远不要对 LLM 输出做精确全文匹配, 除非走 MOCK。")
    lines += [
        f"2. 断言阈值用实测分布定, 不拍脑袋: 0.8 组的语义近邻一致率 {s8['semantic']}"
        f" 就是'正常发挥'的下界参考, 低于它的改版才算劣化信号(项目 9 直接复用此数)。",
        f"3. 样本量决定结论可信度: n={n} 下众数占比天然有波动, 单次跑批的通过率"
        " 小幅起伏(±1 个用例)不算回归 —— 与项目 15 的'两跑差 ≤1 任务'口径同源。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return s0["exact"], s8["exact"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()
    mock = os.environ.get("MOCK") == "1"
    report = LAB_DIR / "REPORT.md"

    print(f"非确定性画像: n={args.n} per temp, model={args.model}, mock={mock}")
    print(f"prompt: {args.prompt}")
    if mock:
        s0_raw, e0 = mock_group(0, args.n)
        s8_raw, e8 = mock_group(8, args.n)
    else:
        if not (qa_llm and _probe()):
            print("⚠️ LLM 服务不可达: 用 MOCK=1 演示统计管道, 或启动 ollama serve")
            return 1
        print("==> 采样 temperature=0")
        s0_raw, e0 = sample_group(0.0, args.n, args.prompt, args.model)
        print("==> 采样 temperature=0.8")
        s8_raw, e8 = sample_group(0.8, args.n, args.prompt, args.model)

    s0, s8 = summarize(s0_raw), summarize(s8_raw)
    exact0, exact8 = write_report(args.prompt, args.model, args.n,
                                  s0, s8, e0, e8, mock, report)
    print(f"\nREPORT.md -> {report}")
    print(f"  字面一致率: temp0={exact0} temp0.8={exact8}")
    print(f"  语义一致率: temp0={s0['semantic']} temp0.8={s8['semantic']}")
    if mock:
        print("(MOCK 演示: 分布是预置的, 数字只证明统计管道可用)")
        return 0
    assert exact0 > exact8, f"验收失败: temp0 一致率 {exact0} 未高于 temp0.8 {exact8}"
    print("  断言: temp=0 字面一致率 > temp=0.8 ✅ (验收口径)")
    return 0


def _probe():
    import urllib.request
    base = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    try:
        with urllib.request.urlopen(f"{base}/models", timeout=3):
            return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    sys.exit(main())
