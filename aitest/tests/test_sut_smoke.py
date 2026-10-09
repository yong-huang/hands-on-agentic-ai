"""test_sut_smoke — 测试台冒烟 (docs/aitest.md 项目 1 验收)

跑法:
  cd aitest && MOCK=1 python3 -m pytest tests/ -q   # 离线全绿(硬验收)
  cd aitest && python3 -m pytest tests/ -q          # Ollama 在线时真机用例不跳过
"""

import os

import pytest

from testbench import suts

TASK = "用工具创建 hi.txt, 内容为 ok, 然后汇报文件内容。"


# ------------------------------------------------------------
# 离线层: 任何环境全绿
# ------------------------------------------------------------

def test_mock_mh_loop_reaches_final():
    """MOCK=1: 脚本化 chat_fn 驱动 mh.loop 走完 协议, 断言收敛与轨迹。"""
    r = suts.run_sut(TASK, chat_fn=suts.mock_chat_fn(), sandbox=None)
    assert r["sut"] == "mh"
    assert r["final"], "mock 剧本走完后必须有最终回答"
    assert r["turns"] == 2, "剧本两步(工具轮+收敛轮), 实际 %s" % r["turns"]
    assert any("run_bash" in str(t) for t in r["tool_trace"]), "tool_trace 缺工具轮"


def test_mini_sut_deterministic():
    """辅 SUT 零 LLM: 同任务连跑两次, final 与 tool_trace 完全一致。"""
    r1 = suts.run_sut(TASK, sut="mini")
    r2 = suts.run_sut(TASK, sut="mini")
    assert r1["all_ok"] and r2["all_ok"], "mini 模板链路应自评测通过"
    assert r1["final"] == r2["final"]
    assert r1["tool_trace"] == r2["tool_trace"], "确定性 SUT 不应有轨迹差异"


def test_result_model_keys():
    """统一结果模型 v0 的字段契约 —— 后续所有断言项目都依赖这些键。"""
    keys = set(suts.run_sut(TASK, sut="mini"))
    assert {"sut", "task", "final", "turns", "tool_trace", "elapsed_s"} <= keys


def test_unknown_sut_rejected():
    with pytest.raises(ValueError):
        suts.run_sut(TASK, sut="nope")


# ------------------------------------------------------------
# 真机层: Ollama 在线才跑(真实模式的硬验收)
# ------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("MOCK") == "1" or not suts.ollama_alive(),
    reason="MOCK=1 或 Ollama 不在线 —— 真机用例诚实跳过")
def test_real_mh_creates_file_and_reports(sandbox):
    r = suts.run_sut(TASK, sandbox=sandbox)
    assert r["final"], "真实模式必须有最终回答"
    assert r["turns"] >= 2, "写文件+汇报至少两轮"
    written = os.path.join(sandbox, "hi.txt")
    assert os.path.exists(written), "SUT 声称完成但文件不存在 —— 假完成"
    assert open(written).read().strip() == "ok", "文件内容与任务要求不符"
