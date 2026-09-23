"""
面试项目 31 — 长任务断点续跑 (Checkpoint/Resume)

覆盖面试题: 长任务中途挂了怎么恢复？检查点应该存什么？如何保证步骤幂等？

设计要点 (面试答题主线):
1. 检查点存什么: 已完成步骤 id + 每步输出 + 共享上下文 (任务级一次性恢复)
2. 原子写: 先写临时文件再 os.replace, 崩溃不会留下半截检查点
3. 幂等: 步骤可重入——重启后"未完成"的步骤会重做, 但已完成的直接复用
   (at-least-once 执行 + 结果按步骤 id 去重 = 业务上 exactly-once)
4. LLM 上下文恢复: 重启后把已完成步骤的摘要喂回, 模型不"失忆重做"

演示流程 (三次真实运行):
  run1: --crash-at 4   步骤 1-3 完成并落盘, 步骤 4 模拟进程崩溃 (exit 137)
  run2: 直接重启       检查点恢复: 1-3 复用跳过, 4-10 续跑
  run3: 再跑一遍       全部复用, 零 LLM 调用 (纯幂等重放)
每轮打印 恢复成本 (实际执行的步骤数) vs 从头重跑 (10 步) 的对比。
"""

import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT = os.path.join(SCRIPT_DIR, "checkpoint.json")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import chat as _chat                               # noqa: E402  统一客户端

DEMO = "--demo" in sys.argv
MAX_STEPS = 10

# 10 步长任务: 制定一份"Agent 学习计划"的研究管线, 每步一个子问题
STEPS = [
    "列出掌握 Agent 开发需要的 5 个核心主题",
    "为每个主题说明一句话学习目标",
    "指出每个主题最常见的面试考点",
    "给出主题之间的推荐学习顺序及理由",
    "每个主题配一个可动手的小实验建议",
    "总结初学者最常犯的 3 个错误",
    "给出每一步的时间预算 (小时)",
    "指出哪些主题依赖哪些前置主题",
    "给出衡量'已掌握'的标准",
    "把以上内容整理成一份完整学习计划",
]


# ============================================================
# LLM (demo 模式用确定性 canned 生成)
# ============================================================

def llm(prompt):
    if DEMO:
        return "〔demo 产出〕针对该子任务的要点整理（离线预置）。"
    return _chat([{"role": "user", "content": prompt}], temperature=0.3, num_predict=200)


# ============================================================
# 检查点: 原子读写
# ============================================================

def load_checkpoint():
    if not os.path.exists(CHECKPOINT):
        return {"completed": {}, "order": []}
    with open(CHECKPOINT, encoding="utf-8") as f:
        return json.load(f)


def save_checkpoint(cp):
    """原子写: tmp + os.replace, 崩溃不会留下半截 JSON。"""
    tmp = CHECKPOINT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CHECKPOINT)


# ============================================================
# 管线执行 (可恢复)
# ============================================================

def run_pipeline(crash_at=None):
    cp = load_checkpoint()
    done = cp.get("completed", {})
    resumed = len(done)
    print("=" * 64)
    print(f"断点续跑 -- {'DEMO' if DEMO else '真实模式'}   检查点: "
          f"{len(done)}/{MAX_STEPS} 步已完成")
    print("=" * 60)

    if resumed:
        print(f"发现检查点, 复用步骤: {sorted(done)}")
        print(f"只需执行: 步骤 {resumed + 1}..{MAX_STEPS}\n")
    else:
        print("无检查点, 从头执行\n")

    executed = 0
    context_summary = " | ".join(
        f"步骤{k}: {v[:40]}…" for k, v in sorted(done.items())) if done else ""

    for i, step_desc in enumerate(STEPS, 1):
        sid = f"step{i}"
        if sid in done:
            print(f"  [skip] {sid} 已完成, 复用缓存结果")
            continue
        if crash_at is not None and i == crash_at:
            print(f"  💥 步骤 {i} 执行中模拟进程崩溃 (此步未完成, 无检查点)!")
            print(f"     检查点保留: 步骤 1-{i-1}。重新运行本脚本即从断点恢复。")
            sys.exit(137)

        prompt = (f"长任务第 {i}/{MAX_STEPS} 步: {step_desc}。\n"
                  + (f"已完成的前序工作: {context_summary}\n" if context_summary else "")
                  + "给出这一步的产出（120 字内）。")
        result = llm(prompt)
        done[sid] = result
        context_summary = " | ".join(
            f"步骤{k}: {v[:40]}…" for k, v in sorted(done.items()))
        save_checkpoint(cp)
        executed += 1
        print(f"  [done] {sid}: {step_desc} -> {result[:40]}…")

    print(f"\n本次实际执行 {executed} 步, 复用 {len(done) - executed} 步。")
    print(f"{'=' * 64}")
    if executed == 0:
        print("任务此前已完成: 全部步骤幂等复用, 零重算 (重放语义正确)。")
    return cp


def main():
    crash_at = None
    if "--crash-at" in sys.argv:
        crash_at = int(sys.argv[sys.argv.index("--crash-at") + 1])
    fresh = "--fresh" in sys.argv
    if fresh and os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)
        print("已清除旧检查点\n")
    run_pipeline(crash_at=crash_at)


if __name__ == "__main__":
    main()
