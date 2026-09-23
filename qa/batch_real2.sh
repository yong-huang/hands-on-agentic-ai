#!/usr/bin/env bash
# 批量真机验证剩余 labs
set -u
cd "$(dirname "$0")"
PY=/Users/hyhit/anaconda3/bin/python3
for lab in 16_tool_description 17_parallel_tools 18_graceful_degrade \
           21_multi_agent_cs 22_agent_card; do
    py=$(ls "$lab"/*.py 2>/dev/null | head -1 | xargs basename)
    [ -z "$py" ] && continue
    echo "===== $lab ====="
    (cd "$lab" && "$PY" -u "$py" > real_run.log 2>&1)
    echo "exit=$? -> $lab/real_run.log"
done
echo "BATCH2 DONE"
