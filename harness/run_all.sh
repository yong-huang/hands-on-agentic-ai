#!/usr/bin/env bash
# harness 线全量回归跑批器
#   bash run_all.sh mock    # 离线: 编译检查 + 每实验管道自检 (快, 无 LLM)
#   bash run_all.sh real    # 真机: 逐实验按验收口径跑 (Ollama, 约 1-1.5 小时)
# 每个实验的输出写 /tmp/harness_test/<nn>.log, 失败时自动回显末尾。
set -uo pipefail
cd "$(dirname "$0")"
MODE="${1:-mock}"
OUT=/tmp/harness_test
mkdir -p "$OUT"
NAMES=(); RCS=()

lab() {  # lab <编号名> <工作目录> <命令...>
    local name="$1" dir="$2"; shift 2
    echo; echo "=====> [$name]"
    ( cd "$dir" && eval "$*" ) > "$OUT/$name.log" 2>&1
    local rc=$?
    NAMES+=("$name"); RCS+=($rc)
    if [ $rc -eq 0 ]; then echo "      ✅ PASS ($(tail -1 "$OUT/$name.log" | head -c 100))"
    else echo "      ❌ FAIL — 末尾输出:"; tail -6 "$OUT/$name.log" | sed 's/^/      | /'; fi
}

echo "========== harness 回归 · 模式: $MODE =========="

# ---------- 通用: 全部 Python 编译检查 ----------
lab compile . "python3 -m py_compile $(find . -name '*.py' -not -path './.*' | tr '\n' ' ')"

if [ "$MODE" = "mock" ]; then
    lab 01_baseline_mock   01_no_harness_baseline "MOCK=1 python3 no_harness_baseline.py --selftest && MOCK=1 python3 no_harness_baseline.py --trials 1"
    lab 02_anatomy_docs    02_harness_anatomy "test -f REPORT.md && grep -q 'Frameworks compose agents' README.md && test -f images/cli.architecture.svg -o -f images/harness_anatomy.architecture.svg"
    lab 03_abtest_mock     03_scaffold_ab_test "MOCK=1 python3 scaffold_ab_test.py --selftest && MOCK=1 python3 scaffold_ab_test.py --tasks 2"
    lab 04_min_loop_mock   04_min_loop "MOCK=1 python3 demo.py"
    lab 05_contract_mock   05_tool_contract "MOCK=1 python3 demo.py"
    lab 06_sandbox_det     06_sandbox "python3 demo.py"
    lab 07_permissions_det 07_permissions "python3 demo.py"
    lab 08_hooks_det       08_hooks "python3 demo.py"
    lab 09_budget_mock     09_budget "MOCK=1 python3 demo.py"
    lab 12_memory_mock     12_memory "MOCK=1 python3 demo.py"
    lab 13_subagent_mock   13_subagent "MOCK=1 python3 demo.py"
    lab 14_skills_mock     14_skills "MOCK=1 python3 demo.py"
    lab 15_mcp_proto       15_mcp_client "python3 ../../qa/19_mcp_server/mcp_server.py test | grep -q '协议握手'"
    lab 16_eval_mock       eval "MOCK=1 bash run.sh"
    lab 17_cli_compile     17_cli "python3 -m py_compile demo.py ../mh/cli.py"
    lab 18_compile         18_model_vs_harness "python3 -m py_compile run_2x2.py"
else
    lab 01_baseline_real   01_no_harness_baseline "python3 no_harness_baseline.py --trials 10"
    lab 03_abtest_real     03_scaffold_ab_test "python3 scaffold_ab_test.py"
    lab 04_min_loop_real   04_min_loop "python3 demo.py"
    lab 05_contract_real   05_tool_contract "python3 demo.py"
    lab 06_sandbox_agent   06_sandbox "python3 demo.py --agent"
    lab 07_permissions_agt 07_permissions "python3 demo.py --agent"
    lab 08_hooks_agent     08_hooks "python3 demo.py --agent"
    lab 09_budget_real     09_budget "python3 demo.py"
    lab 10_compaction_real 10_compaction "python3 demo.py --threshold 900"
    lab 11_session_real    11_session "python3 demo.py"
    lab 12_memory_real     12_memory "python3 demo.py"
    lab 13_subagent_real   13_subagent "python3 demo.py"
    lab 14_skills_real     14_skills "python3 demo.py"
    lab 15_mcp_real        15_mcp_client "python3 demo.py"
    lab 16_eval_real       eval "bash run.sh"
    lab 17_cli_e2e         17_cli "python3 demo.py"
    lab 18_2x2_quick       18_model_vs_harness "rm -f rows.json && python3 run_2x2.py --quick"
fi

echo; echo "========== 汇总 ($MODE) =========="
pass=0; fail=0
for i in "${!NAMES[@]}"; do
    if [ "${RCS[$i]}" -eq 0 ]; then echo "  ✅ ${NAMES[$i]}"; pass=$((pass+1))
    else echo "  ❌ ${NAMES[$i]} (日志: $OUT/${NAMES[$i]}.log)"; fail=$((fail+1)); fi
done
echo "  合计: $pass 通过 / $fail 失败 / 共 ${#NAMES[@]}"
find . -name __pycache__ -exec rm -rf {} + 2>/dev/null
[ $fail -eq 0 ]
