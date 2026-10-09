# 18 · ⛓️ 统一 runner 与结果模型：一条命令，一份可校验的结果

> 前面七个模块（评测/回归/安全/契约/e2e/轨迹/性能）各自能跑，但出口是七份文件、七条命令。本篇给它们一个统一入口：`python3 -m testbench run --sut mh --level smoke` 一次跑完，产出**单一 results.json** 并过 JSON Schema 校验（JSON Schema：用 JSON 书写的字段约束规范，校验数据形状是否合规）。
> 实测 smoke 档：七个模块全部 `ok`（含 2 条评测 + 2 条回归 + 三维安全（注入/越狱/fuzz）+ 契约 + 2 任务 e2e + 轨迹自证 + 性能采样），总耗时约 7 分钟；单模块崩溃也不阻断其余收集。
> 读完你能把散装测试收拢成平台式的一键跑批。

## Background

集成时刻的痛点很具体：CI 要接七条命令、人工要读七份 JSON；任何一个模块改了输出字段，下游的解析代码就得同步改。没有统一的结果契约，测试台越大越难维护。

平台化的标准做法是**统一 runner + 结果模型**：runner 负责调度（串行调用、超时与异常兜底、档位分档），结果模型负责契约（每个模块的结果长同一个形状，可被机器校验）。两者合起来，"跑一遍测试"从一个手工流程变成一个可靠的构建步骤。

这里还有一个容易被忽略的约定：模块失败与模块**崩溃**是两回事。跑完但指标不达标（fail）是正常结果；模块自己抛异常（error）是工程问题。runner 必须区分两者——崩溃不能带崩整个跑批，必须被记录后继续收集其余模块。

## What

统一 runner 由三个部件构成：模块注册表（负责调度七个模块）、结果契约、档位。

| 部件 | 职责 | 本实验形态 |
|:--|:--|:--|
| 模块注册表（调度） | 七个模块各是 `(ctx) -> 结果` 的薄封装 | eval / regression / security / contract / e2e / trajectory / perf |
| 结果契约 | 每个模块结果同形状 | `name/status/passed/metrics/elapsed_s/detail` |
| 档位 | smoke 小样本 / full 全量口径 | smoke 分钟级，full 30 分钟+ |

`status` 三态：`ok`（跑完）、`error`（模块崩溃，被 runner 兜住）、`skipped`（前置不满足，如离线时真机模块）。

`passed` 分两类：机制类模块（安全/契约/轨迹）给布尔结论；阈值类模块（评测/回归/e2e/性能）留 `null`——**阈值判定是 20 线门禁的职责**，runner 只负责收集数字。

可以把 runner 想象成体检中心的排班护士：七个科室按顺序叫号（调度），每科交同一格式的报告单（结果契约），今天做简易套餐还是全套由档位决定。但和体检不同的是：**某个科室设备坏了不会让整个体检停摆**——那项标记异常，其余照常做完。

## When to Use

典型场景：

1. CI 步骤收敛：一个命令产出单一产物，报告系统只认这一份。
2. 日常回归：`--level smoke` 分钟级给出七模块快照。
3. 发版体检：`--level full` 全量口径收集，供 21 线出总报告。

何时不用：只关心单个维度时直接跑对应模块（如只查安全跑 13 的扫描器）；模块本身还在开发中（统一契约会让频繁改字段变得别扭，先稳定接口再收编）。

同类方案对比：

| 方案 | 出口 | 何时选它 |
|:--|:--|:--|
| 各模块独立跑 | 七份文件 | 单维度调试 |
| 统一 runner（本实验） | 一份 schema 化报告 | CI、平台化 |
| 专业 CI 平台 | 平台产物 + UI | 有多语言流水线时 |

## Quick Start

前置条件：pytest 用系统 `python3`；smoke 真机段需要 Ollama 与 `qwen3:4b`（离线时五个真机模块记 `skipped`，评测降级为 mini 离线 SUT 且 `metrics.offline=true`）。。

```bash
cd aitest
python3 -m pytest tests/test_runner.py -q   # 离线 5 条：schema/崩溃隔离/注册表
cd 18_runner
python3 runner_lab.py all                   # pytest + smoke 跑批（七模块，约 7 分钟）
# 或直接：cd .. && python3 -m testbench run --sut mh --level smoke
```

真机实测（节选：各模块内部进度省略）：

```text
=====> [pytest] 离线单测(schema/崩溃隔离/注册表)
  5 passed in 0.06s

=====> [smoke] 七模块 smoke 跑批 -> results.json + schema 校验

=====> 模块: eval
  ✅ ok 119.26s golden_v1 前 2 条
=====> 模块: regression
  ✅ ok 122.01s 双版对比前 2 条
=====> 模块: security
  ✅ ok 126.69s failed=无
=====> 模块: contract
  ✅ ok 8.37s 变体违规数={'normal': 0}
=====> 模块: e2e
  ✅ ok 13.35s 前 2 个任务
=====> 模块: trajectory
  ✅ ok 0.0s 预置轨迹自证(离线)
=====> 模块: perf
  ✅ ok 32.93s 超标项=无

  模块: {'eval': 'ok', 'regression': 'ok', 'security': 'ok', 'contract': 'ok', 'e2e': 'ok', 'trajectory': 'ok', 'perf': 'ok'}
  落盘 -> .../results/run_results.json
```

诚实预期：smoke 档在真机（qwen3:4b、各模块小样本）约 7 分钟；full 档按各模块的文档口径全量运行，30 分钟起步。

离线（无 Ollama）时五个真机模块记 `skipped` 并写明原因；评测降级为 mini 离线模式（`metrics.offline=true`）。

**报告照样过 schema、照样落盘**，但不要把 skipped 或 offline 读成真机通过。退出码：0 = 无 `error` 模块；1 = 存在崩溃模块。

## How It Works

### 薄封装：复用而非复制

七个模块封装各自 import 对应模块的可编程入口（如 `run_eval.run`、`security_scan.scan`、`run_contract` 等七个），再把返回值折算成统一字段。

任何底层模块演进（如安全门加了新维度），runner 不动——它只认"模块跑完给了我什么"。

### 崩溃隔离：try/except 包住每一次调用

`run_all` 循环里每个模块包在 try/except 中：异常被折算成 `status="error"`、`passed=False`、`detail` 带异常原文，循环继续。

离线单测用"必炸模块"验证这条路径（`test_crash_contained_and_others_collected`），并断言崩溃后的报告仍过 schema。

### 结果契约与档位

`schema.py` 用 JSON Schema 固定形状：`modules` 至少 7 项、`status` 枚举、`passed` 可空……写入前先 `validate()`，不合格直接抛错——报告消费者（19 的 HTML、20 的门禁）可以无条件信任字段存在性。

档位只是采样配置：smoke 把每个模块调到最小样本：评测 2 条、安全（注入 3 条 / 越狱 6 条 / fuzz 3 条）、契约只跑 normal、e2e 2 任务、性能（1 任务 × 1 轮），full 放开到各模块的正式口径。

## Pitfalls & Q&A

### 踩坑清单

1. **模块的口径天生不同，别强行统一成"通过率"**。现象：性能模块没有 pass/fail，轨迹模块是机制自证。原因：七模块测的东西不同（率/分位/布尔）。解法：统一的是**容器形状**（字段固定），不是语义——`metrics` 装各自的数字，`passed` 只给机制类模块，"够不够好"交给门禁（20 线）按阈值判。
2. **崩溃与失败必须分开记**。现象：把模块异常当成"该项 fail"上报，报告看不出工程问题。原因：二者处置不同——fail 是业务结论（照常继续），error 是工程事故（要修 runner/模块）。解法：`status` 三态区分；CLI 退出码只看 `error`。
3. **skipped 不是通过**。现象：离线跑 smoke 看到七模块无 error 就以为全绿。原因：五个真机模块被跳过，评测只有离线数据（`metrics.offline=true`）。解法：读报告先看 `status` 分布；21 线体检会把 skipped 计入"未覆盖"清单而不是沉默放过。

### 深入问答

**Q：runner 和 13 线的安全门是什么关系？**

层级不同：13 的安全门是**领域内门禁**（三维安全自有阈值与退出码），18 的 runner 是**全局收集器**（把安全门当作七模块之一调用，收它的数字）。20 线的 CI 门禁再在 runner 结果之上做变更加权路由——三者是"专业门 → 总调度 → 总门禁"的套娃结构。

**Q：full 档到底要多久，能不能并行？**

按各模块文档口径保守估计 30-60 分钟（e2e 10 个任务一遍与性能 3 任务 ×2 轮是大头）。当前实现是**串行**的——本机 Ollama 单实例下并行只会互相抢 GPU，串行反而稳定；真要压缩时间，优先级是"缩小样本"（门禁路由）而不是并行。

**Q：为什么 schema 要求 `modules` 至少 7 项？**

防止"模块被悄悄删掉"这类回归：如果某次改动让一个模块不再注册，报告依旧生成、数字变少而无人察觉。`minItems: 7` 把这个静默失败变成 schema 校验错误。同理，每个模块的字段是 `required` 的——宁可写 `null` 也不许缺字段。
