# aitest · AI 测试（LLM/Agent 质量工程）21 项渐进实验

> 第四条学习线：**测试 AI 系统**。被测对象（SUT，System Under Test）用仓库现成的
> `harness/mh`（每轮真调 LLM 的 Agent 运行时），`qa/30_mini_agent`（零 LLM 的
> 确定性模板引擎）作离线辅助 SUT。
> 全部项目共同生长为 `testbench/` 测试台：评测集 → 四类断言 → 回归与红队 →
> Agent 行为测试 → 统一 runner 与门禁，🏁 终极给 mh 出四维体检报告。
> 每个实验四件套：**README 教程 + 主脚本 + 真实可跑 + 架构图三件套**。
> 当前进度：**21/21 全部完成**（2026-10-09）；pytest 套件离线全绿，图三件套 21 张。
> 完整学习清单（含与 qa/agent/harness 三线的关系表）见
> [../docs/aitest.md](../docs/aitest.md)。
> 另四条线：[agents/](../agents/README.md)（framework 视角）·
> [qa/](../qa/README.md)（问题实证视角）· [harness/](../harness/README.md)（运行时视角）·
> [langchain/](../langchain/README.md)（LangChain 框架内核视角）。

## 环境要求

与其他三条线完全共用，零新增安装（pytest/pyyaml/numpy 均已在 Python 3.13 环境）：

```bash
# Ollama + 本地模型（免 Key）
ollama list                           # qwen3.8:latest（默认）/ qwen3:4b（提速）
ollama serve                          # http://localhost:11434
# 真实模式开工前探活
curl -sf http://localhost:11434/v1/models >/dev/null && echo OK
```

- `MOCK=1` 离线模式：被测对象走预置剧本，任何环境全绿（复用 qa/llm.py 约定）。
- 提速跑法：`LLM_MODEL=qwen3:4b`（2.5GB），跑批/fuzz 类项目必用。
- 项目 5 语义断言额外依赖 embedding 模型 `nomic-embed-text`（已装，开工再探活）。

## 实验列表

编号即学习顺序，与 [../docs/aitest.md](../docs/aitest.md) 项目一一对应。

### 第一阶段 · 地基：测试台骨架与非确定性世界

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 01 | [testbench_sut](01_testbench_sut/README.md) | 测试台骨架 + SUT 适配层：一个 run_sut() 接口接两个被测对象 |
| ✅ 02 | [datasets](02_datasets/README.md) | 评测集构建与版本化：golden set + YAML schema + 版本 diff |
| ✅ 03 | [nondeterminism](03_nondeterminism/README.md) | 非确定性画像：同一 prompt 双温度各 30 次，一致率数值报告 |

### 第二阶段 · 断言库：LLM 输出的四种可测性

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 04 | [schema_assert](04_schema_assert/README.md) | 结构化输出断言：提取+规则修复+校验器+LLM 重试，10 坏例修 9 |
| ✅ 05 | [semantic_assert](05_semantic_assert/README.md) | 语义断言：embedding 阈值实测标定 0.60，双侧矩阵 9/10·10/10 |
| ✅ 06 | [factuality](06_factuality/README.md) | 幻觉检测器：三级核验，混淆矩阵 检出 10/10·误报 0/10 |
| ✅ 07 | [judge_rubric](07_judge_rubric/README.md) | LLM-as-Judge 校准：相邻一致 20/20 · 重复一致 20/20 |
| ✅ 08 | [assert_protocol](08_assert_protocol/README.md) | ⛓️ 统一协议四维断言，首轮基线 schema 1.0/semantic 0.4/fact 0.2/judge 0.8 |

### 第三阶段 · 回归与红队：变化是敌人，攻击者是朋友

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 09 | [prompt_regression](09_prompt_regression/README.md) | 提示词回归：双版同卷对比，实测抓出 4 个劣化项 |
| ✅ 10 | [injection_range](10_injection_range/README.md) | 提示注入靶场：baseline 0.733 vs full 0.067 ASR 对照 |
| ✅ 11 | [jailbreak](11_jailbreak/README.md) | 越狱用例库：三分类判定 + 变异器，拒绝率 0.667 |
| ✅ 12 | [fuzz](12_fuzz/README.md) | 鲁棒性 fuzz：100 条畸形输入，mini 全活 / mh 抓 3 findings |
| ✅ 13 | [security_scan](13_security_scan/README.md) | ⛓️ 安全门：三维一键报告 + 阈值退出码，两态可验 |

### 第四阶段 · Agent 特有：测行为不只测文本

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 14 | [tool_contract](14_tool_contract/README.md) | 工具契约：双断言 + 三写坏变体自证全抓 |
| ✅ 15 | [e2e_task](15_e2e_task/README.md) | 端到端终态断言：10 任务两遍 10/10 零波动 |
| ✅ 16 | [trajectory](16_trajectory/README.md) | 轨迹评测：快100/慢60/死循环0，真机轨迹 100 |
| ✅ 17 | [perf_budget](17_perf_budget/README.md) | 性能门禁：P50 19.4s 达标 / 收紧阈值 exit 1 |

### 第五阶段 · 平台化：从脚本到门禁

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 18 | [runner](18_runner/README.md) | ⛓️ 统一 runner：七模块 smoke 全 ok，schema 校验 |
| ✅ 19 | [report](19_report/README.md) | 报告生成器：五区块 HTML + 数字抽查对账 |
| ✅ 20 | [gate](20_gate/README.md) | CI 门禁分级：变更路由 + selftest 8/8 |
| ✅ 21 | [final_checkup](21_final_checkup/README.md) | 🏁 四维体检：评级 A + 修复建议 + FINAL_REPORT |

## 与 harness 线的分工

`harness/` 造被管控的运行时（被测方），`aitest/` 造测它的测试台（测的一方）；
`harness/eval/` 是 mh 专属评测台，`aitest/testbench/` 是通用测试台。

任务集与 baseline/full 方法论两边复用，测试台代码不依赖 mh 内部实现，
只经 `testbench/suts.py` 适配层接入。
