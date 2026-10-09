"""conftest — 测试台 pytest 公共夹具 (docs/aitest.md 项目 1)

pytest 从 aitest/ 目录启动时自动发现本文件; 这里负责:
  1. 把 aitest/ 与 harness/ 挂进 sys.path(testbench 与 mh 可导入);
  2. 提供 run_sut / ollama 两类夹具, 测试只声明依赖不关心路径。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))       # aitest/tests
AITEST_DIR = os.path.dirname(HERE)                      # aitest/
REPO_ROOT = os.path.dirname(AITEST_DIR)

for _p in (AITEST_DIR, os.path.join(REPO_ROOT, "harness")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from testbench import suts  # noqa: E402


@pytest.fixture(scope="session")
def ollama():
    """会话级探活结果: True = 真实模式可用。"""
    return suts.ollama_alive()


@pytest.fixture
def run_sut():
    """run_sut 工厂夹具: 测试函数签名里声明即可调用。"""
    return suts.run_sut


@pytest.fixture
def sandbox(tmp_path):
    """每用例独立的任务目录, 用例结束自动清理。"""
    return str(tmp_path)
