#!/usr/bin/env bash
# 16 · Harness 评测台: 同一任务集对比 baseline(v0.1) / full(v1.0) 两套配置
# 真机全量约 1 小时; MOCK=1 bash run.sh 离线自检管道
set -uo pipefail
cd "$(dirname "$0")"
python3 eval_run.py "$@"    # 不带 --profile 时跑两套配置并自动对比
exit $?
