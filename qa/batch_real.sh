#!/usr/bin/env bash
# 批量真机验证 qa labs 7-22 (串行, 每个 lab 输出到各自 real_run.log)
set -u
cd "$(dirname "$0")"
for lab in 07_short_memory 08_long_memory 09_memory_poison 10_hybrid_retrieval \
           11_reflection 12_plan_execute 13_replan 14_hitl_gate \
           15_tool_registry 16_tool_description 17_parallel_tools \
           18_graceful_degrade 21_multi_agent_cs 22_agent_card; do
    py=$(ls "$lab"/*.py 2>/dev/null | head -1 | xargs basename)
    [ -z "$py" ] && continue
    echo "===== $lab ====="
    (cd "$lab" && python3 -u "$py" > real_run.log 2>&1)
    echo "exit=$? -> $lab/real_run.log"
done
echo "ALL DONE"
