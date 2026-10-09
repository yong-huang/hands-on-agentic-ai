"""run_eval — golden set 全量评测驱动 (docs/aitest.md 项目 8)

把断言库接到 SUT 上: 逐条驱动被测对象, 收集四维断言结果, 聚合成基线报告。

    python3 -m testbench.run_eval --dataset golden_v1 --sut mh
        [--model qwen3:4b] [--limit N] [--offline-chat]

流程(每条用例):
  1. run_sut(query) 驱动主 SUT, 拿 final 回答;
  2. 非 tool 类再用 JSON 化变体 query 二次驱动, 采 schema 维度样本;
  3. asserts.evaluate_case 跑 semantic/factuality/judge/schema 四维;
  4. 聚合: 各维通过率 + 总通过率, 写 aitest/results/baseline.json。

真机跑批默认 LLM_MODEL=qwen3:4b(20 案例约 6-10 分钟); --sut mini 走离线
确定性 SUT, 配 --offline-chat(脚本化 judge)可全离线验证管道。
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
AITEST_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(AITEST_DIR)
sys.path.insert(0, AITEST_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, "qa"))

from testbench import suts                                    # noqa: E402
from testbench.asserts import evaluate_case                   # noqa: E402
from testbench.datasets import load as load_dataset           # noqa: E402

JSON_INSTRUCTION = ('只输出一个 JSON 对象, 不要解释: {{"answer": "<回答>", '
                    '"confidence": <0 到 1 的数字>}}。')


def _offline_chat_factory():
    """离线 judge: 按 prompt 关键词给固定分, 只为验证管道。"""
    def chat(messages, **kw):
        content = messages[0]["content"]
        if "SUPPORTED" in content:
            return "SUPPORTED"
        if "评分" in content or "score" in content:
            return '{"score": 4, "reason": "离线管道"}'
        return "好的"
    return chat


def _stub_embeddings():
    """离线 embedding 打桩: 64 桶字符袋向量, 确定性无网络。
    相似度数值不再有语义 —— 离线模式只验证管道, 数字不代表质量。
    返回原函数以便调用方在结束后恢复(防跨用例污染真机断言)。"""
    from testbench.asserts import semantic

    original = semantic.embed

    def fake_embed(text, model=None, timeout=30):
        vec = [0.0] * 64
        for ch in text:
            vec[hash(ch) % 64] += 1.0
        return vec

    semantic.embed = fake_embed
    return original


def run(dataset="golden_v1", sut="mh", model=None, limit=None,
        offline_chat=False, verbose=True):
    """跑全量评测, 返回 results dict(同时落盘 aitest/results/baseline.json)。"""
    cases = load_dataset(dataset)["cases"]
    if limit:
        cases = cases[:limit]
    original_embed = _stub_embeddings() if offline_chat else None
    chat_fn = _offline_chat_factory() if offline_chat else _real_chat()
    results = {"meta": {
        "dataset": dataset, "sut": sut, "model": model or "default",
        "offline": bool(offline_chat),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }, "cases": []}
    for i, case in enumerate(cases, 1):
        r = suts.run_sut(case["query"], sut=sut, model=model)
        answer = r["final"]
        schema_answer = None
        if case.get("category") != "tool":
            r2 = suts.run_sut(JSON_INSTRUCTION + " " + case["query"],
                              sut=sut, model=model)
            schema_answer = r2["final"]
        row = evaluate_case(case, str(answer), chat_fn=chat_fn,
                            schema_answer=schema_answer)
        row["answer_preview"] = str(answer)[:60]
        results["cases"].append(row)
        if verbose:
            marks = "".join("✅" if (d or {}).get("pass") else "❌"
                            for d in (row.get("schema"), row["semantic"],
                                      row["factuality"], row["judge"]) if d)
            print(f"  [{i:02d}/{len(cases)}] {case['id']} {marks}")

    if original_embed is not None:               # 恢复真机 embedding
        from testbench.asserts import semantic
        semantic.embed = original_embed

    summary = _aggregate(results["cases"])
    results["summary"] = summary
    out_dir = Path(AITEST_DIR) / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "baseline.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\n各维通过率: {json.dumps(summary['rates'], ensure_ascii=False)}")
    print(f"总通过率: {summary['overall_pass_rate']} -> {out_path}")
    return results


def _real_chat():
    """judge 客户端: qa_llm.chat 包一层退避重试 —— Ollama 在模型切换
    负载下会断连(RemoteDisconnected), 裸调用跑不完 20 条(实测第 9 条崩)。"""
    import functools
    import time
    import llm as qa_llm

    @functools.wraps(qa_llm.chat)
    def retrying(messages, **kw):
        last = None
        for attempt in range(1, 4):
            try:
                return qa_llm.chat(messages, **kw)
            except Exception as e:  # noqa: BLE001 —— 网络类故障退避重试
                last = e
                time.sleep(2 * attempt)
        raise last

    return functools.partial(retrying, num_predict=800, temperature=0)


def _aggregate(rows):
    """四维通过率 + 总通过率。None 维不计入该维分母。"""

    def rate(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return None
        return round(sum(1 for v in vals if v["pass"]) / len(vals), 3)

    rates = {k: rate(k) for k in ("schema", "semantic", "factuality", "judge")}
    overall = round(sum(1 for r in rows if r["pass"]) / len(rows), 3) if rows else 0.0
    by_cat = Counter(r["category"] for r in rows if r["pass"])
    totals = Counter(r["category"] for r in rows)
    return {"rates": rates, "overall_pass_rate": overall,
            "pass_by_category": dict(by_cat), "total_by_category": dict(totals)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="golden_v1")
    ap.add_argument("--sut", default="mh")
    ap.add_argument("--model", default="qwen3:4b")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--offline-chat", action="store_true")
    args = ap.parse_args(argv)
    run(dataset=args.dataset, sut=args.sut, model=args.model,
        limit=args.limit, offline_chat=args.offline_chat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
