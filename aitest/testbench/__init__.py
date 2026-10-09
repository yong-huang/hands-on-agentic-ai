"""testbench — AI 测试台 (docs/aitest.md 21 项目共同生长的载体)

项目 1 立骨架: suts.py 把被测 Agent 包成统一的 run_sut() 接口。
后续项目按清单逐个加模块: datasets → asserts → judges → suites → runner。
"""

from . import suts  # noqa: F401

__all__ = ["suts"]
