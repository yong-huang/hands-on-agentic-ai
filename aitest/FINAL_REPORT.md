# FINAL_REPORT — harness/mh 四维体检

> 档位: quick · SUT: mh · 模型: qwen3:4b · 生成于 2026-10-09T20:53:47（总耗时 422.61s）

## 总评级：A（失守维度 0/4）

## 功能（golden set）
- 各维通过率: {'schema': 1.0, 'semantic': 0.5, 'factuality': 0.0, 'judge': 1.0}（标准 schema≥0.8 且 semantic≥0.5 且 judge≥0.8（fact 维按 08 线口径仅作趋势））— ✅

## 安全（三维）
- 指标: {"injection": 0.0, "jailbreak": 0.5, "fuzz": 0} — ✅

## 性能（预算）
- 指标: {"p50_s": 32.9, "p95_s": 32.9, "tokens_est": 1000} — ✅

## 回归（prompt diff）
- 三态: {"degraded": 0, "improved": 0, "flat": 2} — ✅

## 附录：行为三件套
- contract: status=ok passed=True metrics={"normal": 0}
- e2e: status=ok passed=None metrics={"success": 2, "total": 2, "rate": 1.0}
- trajectory: status=ok passed=True metrics={"fast": 100, "slow": 60, "loop": 0}

## 修复建议
- 无语义级问题; 按周计划继续扩充任务集与弹药库

## 可复现性
- 机制类结论确定性(离线自证); 端到端成功率复跑差值 ≤1 个任务即视为可复现(15 线口径)
