#!/usr/bin/env bash
# interview 全量测试跑批器
#   ./run_all.sh mock   # 31 个 lab 离线回归 (MOCK=1)
#   ./run_all.sh real   # 全量真机 (Ollama qwen3.8)
# 结果: 每个lab的日志在 /tmp/iv_test/<mode>/<lab>.log, 汇总打印
set -u
cd "$(dirname "$0")"
PY=/Users/hyhit/anaconda3/bin/python3
MODE=${1:-mock}
OUT=/tmp/iv_test/$MODE
mkdir -p "$OUT"

declare -a ARGS19=(test)          # lab 19 需要子命令
pass=0; fail=0; failed=()

for dir in $(ls -d [0-9][0-9]_* | sort); do
    lab=${dir%%_*}
    py=$(ls "$dir"/*.py 2>/dev/null | head -1 | xargs basename)
    [ -z "$py" ] && continue
    log="$OUT/$dir.log"
    if [ "$MODE" = "mock" ]; then
        (cd "$dir" && MOCK=1 "$PY" -u "$py" ${ARGS19[@]+"${ARGS19[@]}"} > "$log" 2>&1)
    else
        (cd "$dir" && "$PY" -u "$py" ${ARGS19[@]+"${ARGS19[@]}"} > "$log" 2>&1)
    fi
    rc=$?
    if [ $rc -eq 0 ]; then
        pass=$((pass+1)); echo "PASS $dir"
    else
        fail=$((fail+1)); failed+=("$dir")
        echo "FAIL($rc) $dir  -> $log"
    fi
done

echo
echo "===== $MODE 汇总: PASS=$pass FAIL=$fail ====="
if [ ${#failed[@]} -gt 0 ]; then
    printf 'failed: %s\n' "${failed[@]}"
    exit 1
fi
