"""
11 · 回调系统与本地追踪 / 轻评测

真机实验（需要本机 Ollama + qwen3.8:latest），零云依赖：
  A. 回调追踪 — 自定义 BaseCallbackHandler 记录一次 Agent 运行的 run tree：
     chain / llm / tool 三类 span，含父子关系、耗时与 token，落盘 trace.json
  B. 轻评测 — 10 条分类用例 × 两版提示词（v1 裸指令 / v2 加规则与示例），
     输出各自通过率与"改善 / 劣化 / 持平"对比

用法:
  python langchain/11_callbacks_trace/callbacks_trace.py
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Literal, Optional
from urllib.request import urlopen

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

MODEL = os.environ.get("LLM_MODEL", "qwen3.8:latest")
OLLAMA = "http://localhost:11434"
HERE = Path(__file__).resolve().parent

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def ollama_alive():
    try:
        with urlopen(f"{OLLAMA}/v1/models", timeout=3):
            return True
    except Exception:
        return False


def _text(msg):
    content = getattr(msg, "content", msg)
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)


# ============================================================
# A. 回调追踪
# ============================================================

class TraceHandler(BaseCallbackHandler):
    """把 chain / llm / tool 的起止记录成带父子关系的 span。"""

    def __init__(self):
        super().__init__()
        self.spans = {}
        self.order = []

    def _start(self, run_id, parent_run_id, name, run_type):
        rid = str(run_id)
        self.spans[rid] = {
            "id": rid,
            "parent": str(parent_run_id) if parent_run_id else None,
            "name": name,
            "type": run_type,
            "start": time.time(),
            "end": None,
            "duration_ms": None,
            "input_tokens": None,
            "output_tokens": None,
        }
        self.order.append(rid)

    def _end(self, run_id):
        span = self.spans.get(str(run_id))
        if span and span["end"] is None:
            span["end"] = time.time()
            span["duration_ms"] = round((span["end"] - span["start"]) * 1000, 1)

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kw):
        name = (serialized or {}).get("name") or kw.get("name") or "chain"
        self._start(run_id, parent_run_id, name, "chain")

    def on_chain_end(self, outputs, *, run_id, **kw):
        self._end(run_id)

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kw):
        name = (serialized or {}).get("name") or kw.get("name") or "llm"
        self._start(run_id, parent_run_id, name, "llm")

    def on_llm_end(self, response, *, run_id, **kw):
        span = self.spans.get(str(run_id))
        if span is not None:
            try:
                msg = response.generations[0][0].message
                usage = getattr(msg, "usage_metadata", None) or {}
                span["input_tokens"] = usage.get("input_tokens")
                span["output_tokens"] = usage.get("output_tokens")
            except Exception:
                pass
        self._end(run_id)

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kw):
        name = (serialized or {}).get("name") or kw.get("name") or "tool"
        self._start(run_id, parent_run_id, name, "tool")

    def on_tool_end(self, output, *, run_id, **kw):
        self._end(run_id)

    def dump(self, path):
        spans = [self.spans[rid] for rid in self.order]
        payload = {"spans": spans, "span_count": len(spans)}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        return payload


class TokenCounter(BaseCallbackHandler):
    """轻量统计：只累计 token。"""

    def __init__(self):
        super().__init__()
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def on_llm_end(self, response, *, run_id, **kw):
        self.calls += 1
        try:
            usage = response.generations[0][0].message.usage_metadata or {}
            self.input_tokens += usage.get("input_tokens", 0)
            self.output_tokens += usage.get("output_tokens", 0)
        except Exception:
            pass


def part_a_trace(llm):
    from langchain.agents import create_agent
    from langchain_core.tools import tool

    section("[A] 回调追踪：run tree 落盘（真机）")

    @tool
    def calculator(expression: str) -> str:
        """计算数学表达式。"""
        return str(eval(expression, {"__builtins__": {}}))

    tracer = TraceHandler()
    agent = create_agent(model=llm, tools=[calculator],
                         system_prompt="You are a calculator. ALWAYS use the tool.")
    agent.invoke({"messages": [HumanMessage("请用工具计算 21 + 21。")]},
                 {"callbacks": [tracer]})

    payload = tracer.dump(HERE / "trace.json")
    kinds = {s["type"] for s in payload["spans"]}
    print(f"  span 总数: {payload['span_count']}，类型: {sorted(kinds)}")
    llm_spans = [s for s in payload["spans"] if s["type"] == "llm"]
    tool_spans = [s for s in payload["spans"] if s["type"] == "tool"]
    check("trace 同时含 chain / llm / tool 三类 span",
          {"chain", "llm", "tool"} <= kinds
          and len(llm_spans) >= 2 and len(tool_spans) >= 1)

    ok_duration = all(s["duration_ms"] is not None for s in payload["spans"])
    ok_token = all(s["input_tokens"] and s["output_tokens"] for s in llm_spans)
    ok_parent = all(s["parent"] is None or s["parent"] in tracer.spans
                    for s in payload["spans"])
    print(f"  首个 llm span: {llm_spans[0]['name']} "
          f"{llm_spans[0]['duration_ms']}ms "
          f"in={llm_spans[0]['input_tokens']} out={llm_spans[0]['output_tokens']}")
    check("每个 span 都有耗时与父子关系，llm span 含 token",
          ok_duration and ok_token and ok_parent)

    loaded = json.loads((HERE / "trace.json").read_text(encoding="utf-8"))
    check("trace.json 落盘且可重新解析",
          loaded["span_count"] == payload["span_count"] and loaded["span_count"] >= 6,
          f"路径: {HERE / 'trace.json'}")


# ============================================================
# B. 轻评测：两版提示词对比
# ============================================================

class Category(BaseModel):
    label: Literal["代码", "数学", "通用"]


CASES = [
    ("这段 for 循环为什么慢？", "代码"),
    ("3 的阶乘是多少？", "数学"),
    ("推荐一部适合周末看的电影", "通用"),
    ("怎么用 pandas 给数据去重？", "代码"),
    ("帮我算一下 100 万房贷 30 年的月供", "数学"),
    ("明天会下雨吗？", "通用"),
    ("解释这个报错：IndexError: list index out of range", "代码"),
    ("100 美元换算成人民币是多少？", "数学"),
    ("写一首关于秋天的短诗", "通用"),
    ("这条 SQL 应该怎么加索引？", "代码"),
]

V1_SYSTEM = "把用户问题分类为 代码/数学/通用 之一。"

V2_SYSTEM = """把用户问题分类为 代码/数学/通用 之一。规则：
- 涉及编程、报错、数据库、依赖库的问题 → 代码
- 需要计算、换算数字的问题 → 数学
- 其他 → 通用
示例：
问题：帮我算一下 100 万房贷月供 → 数学
问题：解释这个报错是什么意思 → 代码
问题：今天有什么新闻 → 通用"""


def part_b_eval(llm):
    from langchain_core.prompts import ChatPromptTemplate

    section("[B] 轻评测：10 用例 × 两版提示词（真机）")

    def make_chain(system):
        prompt = ChatPromptTemplate.from_messages(
            [("system", system), ("human", "{q}")])
        return prompt | llm.with_structured_output(Category)

    versions = {
        "v1 裸指令": (make_chain(V1_SYSTEM), TokenCounter()),
        "v2 规则+示例": (make_chain(V2_SYSTEM), TokenCounter()),
    }

    results = {name: [] for name in versions}
    for q, expected in CASES:
        for name, (chain, counter) in versions.items():
            cat = chain.invoke({"q": q}, {"callbacks": [counter]})
            results[name].append(cat.label == expected)

    lines = []
    for name, oks in results.items():
        rate = sum(oks) / len(oks) * 100
        counter = versions[name][1]
        lines.append(f"  {name}: 通过率 {rate:.0f}% "
                     f"({sum(oks)}/{len(oks)}) | "
                     f"tokens in={counter.input_tokens} out={counter.output_tokens}")
    print("\n".join(lines))
    check("跑批 ≥10 用例并输出两版通过率",
          len(CASES) >= 10 and all(len(oks) == len(CASES)
                                   for oks in results.values()))

    v1, v2 = results["v1 裸指令"], results["v2 规则+示例"]
    improve = sum(1 for a, b in zip(v1, v2) if not a and b)
    degrade = sum(1 for a, b in zip(v1, v2) if a and not b)
    same = sum(1 for a, b in zip(v1, v2) if a == b)
    print(f"  对比: 改善 {improve} / 劣化 {degrade} / 持平 {same}")
    check("改善/劣化/持平计数完整", improve + degrade + same == len(CASES))
    check("v2（规则+示例）通过率不低于 v1",
          sum(v2) >= sum(v1), f"v1={sum(v1)}/{len(CASES)} v2={sum(v2)}/{len(CASES)}")


def main():
    print("=" * 64)
    print("[11] 回调系统与本地追踪 / 轻评测（真机）")
    print(f"模型: {MODEL}")
    print("=" * 64)

    if not ollama_alive():
        print("\n⏭️ Ollama 未启动，本实验需要对话模型：先 `ollama serve`")
        return 2

    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_predict=256)
    part_a_trace(llm)
    part_b_eval(llm)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
