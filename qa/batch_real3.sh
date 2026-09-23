#!/usr/bin/env bash
# 批量真机验证 labs 23-28
set -u
cd "$(dirname "$0")"
PY=/Users/hyhit/anaconda3/bin/python3
for lab in 23_generator_critic 24_injection_range 25_guardrails \
           26_goal_drift 27_eval_judge 28_rag_quality; do
    py=$(ls "$lab"/*.py 2>/dev/null | head -1 | xargs basename)
    [ -z "$py" ] && continue
    echo "===== $lab ====="
    (cd "$lab" && "$PY" -u "$py" > real_run.log 2>&1)
    echo "exit=$? -> $lab/real_run.log"
done
echo "BATCH3 DONE"
