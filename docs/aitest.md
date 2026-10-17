# 🧪 AI 测试 21 小项目学习清单 · Todo List（测试 AI 系统 · 本机全跑通）

> 通过 21 个小项目（每项目 80-300 行代码）掌握 **AI（LLM/Agent）系统质量工程**：断言非确定性输出、评测集与回归、红队对抗、评测平台化
> 主视角是「**测试 AI 系统**」——被测对象（SUT）用仓库现成的 `harness/mh` mini-harness（每轮真调 LLM 的 Agent 运行时），`qa/30_mini_agent`（纯模板无 LLM）降级为离线辅助 SUT
> 本机 Ollama 免 Key 可跑（复用 `qa/llm.py` 的 OpenAI 兼容约定），零云依赖、**零新增安装**（pytest/pyyaml/numpy 已装）
> 串联机制：全部项目共同生长为 `aitest/testbench/` 测试台，每阶段末 ⛓️ 集成接线，项目 21 🏁 终极四维体检
> 预计周期：4 周（每天 2-3 小时）

---

## 🏗️ 终极蓝图（项目 21 完成时的 ai-testbench）

```
              ┌────────────────────────────────────────────────┐
              │            aitest/testbench/ 测试台             │
              │       python -m testbench run <SUT> [档位]      │
              ├───────────────┬────────────────┬───────────────┤
              │ datasets/     │ asserts/       │ suites/       │
              │ 评测集+版本化  │ schema/语义/   │ 回归/安全/     │
              │ (项目 2)      │ 幻觉/judge     │ agent/性能     │
              │               │ (项目 4-8)     │ (项目 9-17)   │
              ├───────────────┴────────────────┴───────────────┤
              │  runner 统一结果模型(18) → HTML 报告(19)         │
              │  → CI 门禁分级(20) → 🏁 四维体检(21)             │
              └───────────────────────┬────────────────────────┘
                                      │ SUT 适配层 (项目 1)
                        ┌─────────────┴─────────────┐
                        │  harness/mh (主SUT,真LLM)  │
                        │  qa/30_mini_agent (辅助SUT)│
                        └───────────────────────────┘
```

每个项目给测试台加一块能力；阶段末 ⛓️ 项目把本阶段模块接进测试台；项目 21 用测试台给 harness/mh 出一份功能+安全+性能+回归的完整体检报告。

## 🤖 AI 辅助提示词速查

| 场景 | 提示词 |
|:---|:---|
| **开始一个新项目** | `我要开始 AI 测试项目「[名称]」，目标是 [目标]。请给我完整 Python 代码约 [行数] 行，放 aitest/ 目录，复用 qa/llm.py 的 OpenAI 兼容客户端（LLM_BASE_URL/LLM_MODEL/LLM_API_KEY 环境变量，MOCK=1 时离线），pytest 风格断言。只输出代码。` |
| **断言写不出来** | `我要断言 LLM 输出满足：[性质描述]。输入样例：[粘贴]，当前输出样例：[粘贴]。请给出可复用的 Python 断言函数（容忍非确定性，带阈值/重试参数），并给 3 个通过用例和 3 个失败用例。` |
| **排障** | `我的 testbench 出现 [现象]，报错/日志：[粘贴]。请分析根因并给修复，保持零新增依赖。` |

## 📊 总进度

进度：████████████████████ 21/21 (100%)

| 阶段 | 项目数 | 已完成 |
|:---|:---:|:---:|
| 第一阶段：地基——测试台骨架与非确定性世界 | 3 | 3 |
| 第二阶段：断言库——LLM 输出的四种可测性 | 5 | 5 |
| 第三阶段：回归与红队——变化是敌人，攻击者是朋友 | 5 | 5 |
| 第四阶段：Agent 特有——测行为不只测文本 | 4 | 4 |
| 第五阶段：平台化——从脚本到门禁 | 4 | 4 |
| **合计** | **21** | **21** |

---

## 🗂️ 第一阶段：地基——测试台骨架与非确定性世界（项目 1-3）

> **目标**：立起测试台骨架，把仓库现有 agent 包成可驱动 SUT，建立"非确定性输出也能测"的测试观。

### [x] 项目 1：测试台骨架 + SUT 适配层

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | pytest fixture、SUT 适配层、mock 与真实双模式、测试目录约定 |
| **产出模块** | `aitest/testbench/`（`__init__.py`/`suts.py`/`conftest.py`）+ `aitest/tests/test_sut_smoke.py` |
| **技术栈** | pytest（✅ 已装）、复用 `mh.loop.run_agent`（主 SUT）与 qa/llm.py 约定 |
| **⚠️ 风险** | 真实模式需 Ollama 在线：开工先 `curl -sf http://localhost:11434/v1/models`；不通则 MOCK=1 全程可跑。qwen3.8 单任务慢，适配层透传 LLM_MODEL 可切 qwen3:4b |
| **验收标准** | `cd aitest && MOCK=1 python3 -m pytest tests/ -q` 全绿；真实模式下 `python3 -c "import sys; sys.path.insert(0,'aitest'); from testbench.suts import run_sut; r=run_sut('用工具创建 hi.txt 内容为 ok'); assert r['final']; print(r['turns'])"` 正常返回轮次 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「测试台骨架 + SUT 适配层」。请给我完整 Python 代码约 200 行：aitest/testbench/ 包骨架（suts.py 把 harness/mh 的 mh.loop.run_agent 包成 run_sut(task, system=None) 可编程调用接口，透传 LLM_MODEL/MOCK 环境变量，自带默认工具集；另把 qa/30_mini_agent 包成离线确定性 SUT 供 MOCK 冒烟）；aitest/tests/test_sut_smoke.py 两条冒烟测试（mock 全绿）。附验收命令。只输出代码。`

**完成日期**：2026-10-08
**踩坑记录**：mh 的 tool_trace 是 dict 而 mini 是元组，同一字段两种结构，汇总函数要先按类型分派（KeyError: 1）；mini 的 Tracer/Memory 会写自己目录，适配层必须重定向到 tempfile；架构图 archify 的 labelAt 是绝对坐标不是偏移，标签会全钉到画布顶。

---

### [x] 项目 2：评测集构建与版本化（golden set）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | golden set、数据标注、YAML schema 校验、数据集版本 diff |
| **产出模块** | `aitest/testbench/datasets.py` + `aitest/datasets/golden_v1.yaml`（≥20 条标注用例） |
| **前置** | 项目 1 |
| **验收标准** | `python3 -m testbench.datasets validate` 输出 PASS 且报出用例数；`python3 -m testbench.datasets diff golden_v1 golden_v2` 对复制修改出的 v2 输出增/删/改行数统计 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「评测集构建与版本化」。请给我完整 Python 代码约 180 行：datasets.py 提供 golden set 的加载/YAML schema 校验（字段：id/query/期望要点/标签）/版本 diff 三命令（validate/load/diff），并生成 aitest/datasets/golden_v1.yaml 20 条种子用例（覆盖事实/工具/注入/闲聊四类，来自 mh 的任务域：文件读写/命令执行/多步任务）。附验收命令。只输出代码。`

**完成日期**：2026-10-08
**踩坑记录**：`cmd_validate(*argv[1:1])` 空切片把参数静默吞掉，`validate golden_v2` 实际校验的还是 v1（输出却像是对的）——带默认值的命令行参数必须显式接 argv[1]；`python -m` 必须以 aitest/ 为 cwd，包目录下 ModuleNotFoundError。

---

### [x] 项目 3：非确定性画像（同一 prompt 的方差报告）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~150 行 |
| **核心知识点** | 温度与种子、输出方差、一致率统计、样本量意识 |
| **产出模块** | `aitest/03_nondeterminism/profile.py` + `REPORT.md` |
| **技术栈** | LLM_MODEL 用 `qwen3:4b`（✅ 已装，比 17GB 的 qwen3.8 快得多，画像够用） |
| **⚠️ 风险** | 连跑 60 次调用约 10-20 分钟，可先 num_predict 压小；Ollama 不在线则 MOCK 模式演示统计逻辑 |
| **验收标准** | `python3 03_nondeterminism/profile.py` 产出 REPORT.md，含 temperature=0 与 0.8 两组各 30 次的一致率数值，且 0 组一致率 > 0.8 组 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「非确定性画像」。请给我完整 Python 代码约 150 行：对同一 prompt 在 temperature=0 和 0.8 各跑 30 次（复用 qa/llm.py chat，模型 qwen3:4b），统计字面一致率与语义近邻一致率（编辑距离），输出 REPORT.md 数值表 + 对测试断言的 3 条启示。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：python stdout 重定向到文件是块缓冲，日志一直 0 字节（python3 -u 或 flush）；qwen3 混合推理的 thinking 会吃掉 num_predict，需 /no_think + 400 兜底；与别的进程共享 GPU 时采样耗时翻倍；实测 temp=0 出现 30/30 全同，启示文案模板要能适配 1.0（写死"而非 1.0"会自相矛盾）。

---

## 🗂️ 第二阶段：断言库——LLM 输出的四种可测性（项目 4-8）

> **目标**：把"LLM 输出没法断言"拆成四种可编程断言：结构、语义、事实、judge 评分，统一成一个断言库。

### [x] 项目 4：结构化输出断言（JSON Schema 校验 + 修复重试）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | JSON Schema、截断/混入散文的坏 JSON 模式、自动修复重试、fail-fast 与 soft assert |
| **产出模块** | `aitest/testbench/asserts/schema.py` |
| **前置** | 项目 1 |
| **验收标准** | 预置 10 条坏输出（截断/包 \`\`\`json 围栏/前后废话/类型错），`python3 -m testbench.asserts.schema selftest` 修复后 ≥9/10 过 schema；MOCK=1 pytest 全绿 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「结构化输出断言」。请给我完整 Python 代码约 180 行：asserts/schema.py 提供 check(text, schema) -> (ok, repaired)；提取 JSON（剥围栏/截断补全）、schema 校验（用 jsonschema 或手写校验器，零新增 pip 依赖优先手写）、失败自动重试一次带修复提示；内置 selftest 含 10 条坏样本。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：单引号 JSON 只转值不转键（键在 `{`/`,` 后要独立正则）；字符串内截断要先补引号再补括号；修复顺序固定"结构→逗号→引号→换行→强转"防打架；缺字段不能规则修（会伪造内容），留给 LLM 重试并在 repairs 留痕。

---

### [x] 项目 5：语义断言（embedding 相似度阈值）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~150 行 |
| **核心知识点** | embedding、余弦相似度、阈值标定（等价改写容忍 / 无关回答拒绝） |
| **产出模块** | `aitest/testbench/asserts/semantic.py` |
| **技术栈** | Ollama embeddings `nomic-embed-text`（✅ 已在 ollama list，开工再探活一次） |
| **⚠️ 风险** | 探活命令：`curl -s http://localhost:11434/v1/embeddings -d '{"model":"nomic-embed-text","input":"hi"}'`；不通 fallback 用 all-minilm |
| **前置** | 项目 1 |
| **验收标准** | 10 组"等价改写 vs 标准答案"通过 ≥9，10 组"无关回答"拒绝 ≥9（`selftest` 输出两个 10 格矩阵） |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「语义断言」。请给我完整 Python 代码约 150 行：asserts/semantic.py 调 Ollama /v1/embeddings（nomic-embed-text）做余弦相似度断言 check(text, reference, threshold)，附阈值标定脚本：用 10 组等价改写+10 组无关对扫描阈值曲线，selftest 输出通过/拒绝矩阵。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：超短参考句(12 字)向量表征偏弱, list/tuple 对 sim 只有 0.506 落在线下——参考句要写完整句(≥15 字)；负样本必须取同域内容, 跨域负样本会虚高阈值；`MOCK=1` 下真机矩阵用例必须显式 skip, 打桩 embedding 会假绿。

---

### [x] 项目 6：幻觉检测器（claims 对照事实源）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | claims 拆解、引用核验、数值核对、LLM judge 兜底 |
| **产出模块** | `aitest/testbench/asserts/factuality.py` |
| **前置** | 项目 4、5 |
| **验收标准** | 预置 10 条含幻觉回答（虚构事实/错数字/无中生有引用）检出 ≥9，10 条忠实回答误报 ≤1（`selftest` 给出混淆矩阵） |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「幻觉检测器」。请给我完整 Python 代码约 200 行：asserts/factuality.py 把回答拆成原子 claims，逐条与给定 source 段落核验（子串包含→数值正则核对→LLM judge 兜底三级），输出每条 claim 的 supported/unsupported；内置 20 条预置样本（10 幻觉 10 忠实）的 selftest 混淆矩阵。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：子串快车道无覆盖率门槛时检出仅 5/10——幻觉句总复用正确主题词（gitpush用于把），门槛改为覆盖 claim ≥60%；judge num_predict=60 被思考段吃空→空串全判 unsupported（误报 8/10），300 token+空响应重试后正常；裸 judge 提示词对 4b 太弱，要写明判定规则+少样本；unknown 弃权不算误报也不算漏检。

---

### [x] 项目 7：LLM-as-Judge 校准（rubric + 人工对齐率）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | rubric 设计、judge prompt、与人工标注对齐率、judge 自身稳定性 |
| **产出模块** | `aitest/testbench/judges/rubric.py` + `aitest/datasets/judge_labeled.yaml`（20 条人工预标注） |
| **前置** | 项目 1 |
| **⚠️ 风险** | 20 条预标注由清单作者先人工打分（答案已给质量分），judge 用 qwen3.8 |
| **验收标准** | `selftest` 输出 judge 与人工标注一致率 ≥80%；同输入重复评 2 次的评分一致率 ≥90% |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「LLM-as-Judge 校准」。请给我完整 Python 代码约 200 行：judges/rubric.py 实现 1-5 分 rubric 评分（结构化输出分数+理由，复用项目 4 的 schema 断言），judge_labeled.yaml 放 20 条带人工分值的样本；selftest 计算对齐率与重复评分一致率。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：qwen3.8 思考段比 4b 长得多，num_predict=300 时 6/20 判分静默失败（content 空串→解析失败），相邻一致虚跌 70%；提到 800 后 20/20——judge 大面积"不可用评分"先查 token 预算再怀疑模型；校准集必须分档等量，否则 judge 恒答 4 分也能过线；相邻一致(|Δ|≤1)才是 5 档量表的合理验收线。

---

### [x] ⛓️ 项目 8：断言库统一协议 + golden set 首轮全量评测

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | 统一断言协议、结果模型、首轮基线报告 |
| **产出模块** | `aitest/testbench/asserts/__init__.py`（统一 `check()` 协议）+ `aitest/testbench/run_eval.py` + `aitest/results/baseline.json` |
| **前置** | 项目 4、5、6、7 |
| **验收标准** | `python3 -m testbench.run_eval --dataset golden_v1 --sut mh` 跑完 golden_v1 全部用例，results JSON 里 schema/semantic/factuality/judge 四类结果齐全且各含通过率数字 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「断言库统一协议」。请给我完整 Python 代码约 180 行：asserts/__init__.py 定义 check(name, case, output) 统一协议把项目 4-7 四种断言接入；run_eval.py 读 golden set 对 SUT 逐条调用并跑全部适用断言，输出 aitest/results/baseline.json（每用例四类结果+总通过率）。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：qa_llm 裸调用无重试，Ollama 模型切换负载下 RemoteDisconnected 第 9 条崩——judge 客户端必须包退避重试；离线管道只假 judge 不假 embedding 也会挂；基线 factuality 0.2 是口径严不是 SUT 胡说（期望要点当迷你事实源，合理扩展也计 unsupported）；judge(3.8)+SUT(4b) 双模型逐条切换拖慢全程 40 分钟。

---

## 🗂️ 第三阶段：回归与红队——变化是敌人，攻击者是朋友（项目 9-13）

> **目标**：提示词改版不再靠肉眼回归；把注入/越狱/畸形输入变成可度量的靶场和一键安全门。

### [x] 项目 9：提示词回归套件（promptfoo 思想自研）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | 快照测试、提示词版本 A/B、语义 diff 回归报告、劣化项标红 |
| **产出模块** | `aitest/testbench/suites/prompt_regression.py` + 预置"劣化 prompt 变体"1 个 |
| **前置** | 项目 8 |
| **验收标准** | 对 SUT 换上预置劣化变体后跑 `python3 -m testbench.suites.prompt_regression --base v1 --candidate degraded`，报告必标出 ≥1 个劣化项（通过率下降的用例清单） |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「提示词回归套件」。请给我完整 Python 代码约 200 行：suites/prompt_regression.py 对同一 golden set 分别用 base/candidate 两个 system prompt 跑 SUT，逐用例断言结果对比，输出 markdown diff 报告（改善/持平/劣化三栏，语义断言复用项目 5）；内置一个故意劣化的 prompt 变体用于自证。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：首跑 20 条全部持平——run_sut(system=) 的覆盖发生在返回之后, 实际驱动用的还是 mh 默认 SYSTEM, 灵敏度自证当场抓住该故障；system 必须在 run_agent 播种前以 messages 传入；judge(3.8)+SUT(4b) 逐条切模型拖慢全程；修复后实测 劣化 4/改善 3/持平 13, 含 injection_002 判分 3→1 的安全劣化。

---

### [x] 项目 10：提示注入靶场（直接/间接注入 + ASR 度量）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~220 行 |
| **核心知识点** | 直接/间接注入、攻击成功率 ASR、防御前后对照、payload 库管理 |
| **产出模块** | `aitest/testbench/redteam/injection.py` + `aitest/payloads/injection.yaml`（≥15 条 payload） |
| **前置** | 项目 8 |
| **⚠️ 风险** | 防御对照复用 harness/eval 的两配置方法论：baseline（裸 loop 无防护）vs full（权限门+沙箱），mh 的 permissions 配置即开关；要能复测出两个不同数字 |
| **验收标准** | baseline 与 full 两配置各跑一遍注入集，ASR 两个数值均落盘且 full < baseline（`--report` 输出对照表） |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「提示注入靶场」。请给我完整 Python 代码约 220 行：redteam/injection.py 读 payloads/injection.yaml（≥15 条：直接覆盖指令/间接文档藏指令/编码变体，目标行为=读哨兵文件/执行未授权写），逐条打向 harness/mh，按 tool_trace 里是否出现未授权敏感调用判成功，计算 ASR；支持 --profile baseline|full 切换 mh 权限配置对照防御前后。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：被权限门拦下的调用不算中招, 判定要排除拦截回执; inj_009 从允许类命令漏网, 白名单是模式级盲区

---

### [x] 项目 11：越狱与红队用例库（拒绝率 + payload 变异器）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | 越狱模式（角色扮演/编码绕过/分步诱导）、payload 变异、拒绝率度量、红队回归库 |
| **产出模块** | `aitest/testbench/redteam/jailbreak.py` + `aitest/payloads/jailbreak.yaml` |
| **前置** | 项目 10 |
| **验收标准** | 拒绝率报告落盘；变异器对种子 payload 生成的新变体 ≥5 条自动追加进 YAML 且 `--rerun-new` 可单独复测 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「越狱与红队用例库」。请给我完整 Python 代码约 200 行：redteam/jailbreak.py 维护越狱 payload 库（目标行为用"输出 SECRET"代替真实危害，安全合规），判拒绝/中招计拒绝率；附规则式 payload 变异器（同义替换/编码/前后缀包装），新变体入库可复测。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：qwen3:4b 不遵守 think=False, 思考混入正文导致越狱判定全假阳性, 安全类固定 3.8; 判定需归一化插空变形; 拒绝时复读字符串按有意口径记泄漏

---

### [x] 项目 12：鲁棒性 fuzz（畸形输入轰炸）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | 边界输入、超长截断、unicode/多语言混排、未捕获异常监控、findings 留痕 |
| **产出模块** | `aitest/testbench/suites/fuzz.py` + `aitest/results/findings.jsonl` |
| **前置** | 项目 1 |
| **⚠️ 风险** | 100 条真实调用约 30-60 分钟，用 LLM_MODEL=qwen3:4b 降速 |
| **验收标准** | 100 条畸形输入（空串/10 万字符/emoji+RTL 混排/工具参数越界/嵌套 JSON 轰炸）打向 SUT，未捕获异常率 = 0，异常输出全部自动记入 findings.jsonl |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「鲁棒性 fuzz」。请给我完整 Python 代码约 180 行：suites/fuzz.py 内置 6 类畸形输入生成器共 100 条，逐条打 SUT（超时保护），分类记录：未捕获异常/超时/空输出/正常降级，findings.jsonl 留痕，汇总报告输出各类计数。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：5 万字符输入单条就超时 60s; 超时保护与四类结局分类缺一不可, findings 每轮重建

---

### [x] ⛓️ 项目 13：安全门统一扫描器（注入 + 越狱 + fuzz 一键三维）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | 安全门禁、阈值规则、统一安全报告、退出码约定 |
| **产出模块** | `aitest/testbench/security_scan.py` |
| **前置** | 项目 10、11、12 |
| **验收标准** | `python3 -m testbench.security_scan --sut mh` 一条命令出三维安全报告 JSON（ASR/拒绝率/异常率）；ASR 超阈值时退出码非 0 且报告标红 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「安全门统一扫描器」。请给我完整 Python 代码约 180 行：security_scan.py 串联项目 10/11/12 三个模块，统一为三维安全报告（注入 ASR/越狱拒绝率/fuzz 异常率），可配阈值（如 ASR≤0.2），超阈值标红且 sys.exit(1)——供 CI 直接当门禁。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：越狱维度不能用 4b 提速(拒绝率 0 假失败); 采集崩溃必须 fail-closed 判 fail

---

## 🗂️ 第四阶段：Agent 特有——测行为不只测文本（项目 14-17）

> **目标**：Agent 的正确性在行为轨迹里而不在单条回答里——契约、端到端、轨迹、性能四维各建一套可断言的测试。

### [x] 项目 14：工具调用契约测试（mock 工具 + 调用序列断言）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | mock 工具、参数 schema 校验、调用序列断言、工具描述敏感性 |
| **产出模块** | `aitest/testbench/suites/tool_contract.py` |
| **前置** | 项目 8 |
| **验收标准** | 预置 3 个"工具描述被写坏"的 SUT 变体全部被契约测试抓到（参数错型/漏参/多余调用各 1）；正常 SUT 全绿 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「工具调用契约测试」。请给我完整 Python 代码约 200 行：suites/tool_contract.py 给 mh 的 tools dict 挂 mock 工具记录每次调用的 (名称,参数)，断言参数过 schema、调用序列符合预期剧本；内置 3 个写坏工具描述的变体（诱导真模型传错参/漏参/多调）自证测试有效。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：序列断言光标失败不推进(防连锁误报); 诱饵工具要配'不点名任务'才生效; 三个写坏变体各抓到对应违规

---

### [x] 项目 15：端到端任务成功率（终态断言）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | 任务集设计、终态断言（不逐轮比输出）、成功率复算、失败留痕 |
| **产出模块** | `aitest/testbench/suites/e2e_task.py` + `aitest/datasets/tasks.yaml`（10 个可判终态的任务） |
| **前置** | 项目 1、8 |
| **⚠️ 风险** | 真实 LLM 下任务有随机失败，成功率两跑差 ≤1 个任务即算稳定，不追求 100% 复现；真机跑批用 LLM_MODEL=qwen3:4b 降速（qwen3.8 全量约 1 小时，harness/eval 经验） |
| **验收标准** | 10 任务成功率可复算：连跑两次成功率差 ≤1 个任务；每个失败任务在 results 里留下终态证据（trace 片段） |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「端到端任务成功率」。请给我完整 Python 代码约 200 行：datasets/tasks.yaml 落 10 个 mh 能做且终态可判的任务（可直接借用 harness/eval 已验证的任务集，如"创建文件并校验内容"），suites/e2e_task.py 只断言终态（文件内容/tool_trace 最终事件/工具调用结果），不管中间轮次文本；失败任务自动留终态证据。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：终态判分口径要无歧义(写 3 行=splitlines 恰 3); 任务间必须无依赖; 两遍差值<=1 视为稳定

---

### [x] 项目 16：轨迹评测（步数效率 / 死循环 / 成本分）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | trace 解析、步数效率分、死循环检测、轨迹间可比性 |
| **产出模块** | `aitest/testbench/suites/trajectory.py` |
| **前置** | 项目 15 |
| **验收标准** | 对同一任务预置的"快轨迹/慢轨迹"两条 trace 评出可区分分数（快 > 慢）；注入的 30 步同动作循环 trace 被判死循环得 0 分 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「轨迹评测」。请给我完整 Python 代码约 180 行：suites/trajectory.py 解析 run_agent 返回的 tool_trace/messages（或 session 落盘历史），按 步数效率/重复动作/死循环 三维打 0-100 轨迹分；内置快慢两条预置轨迹与一条死循环 trace 用于自证可区分。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：死循环阈值取连续 3/同参 5; 期望步数须显式标注; 轨迹分不能替代终态分

---

### [x] 项目 17：性能与成本门禁（P50/P95 + token 预算）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | 延迟分位数、token 计数、预算断言、门禁退出码 |
| **产出模块** | `aitest/testbench/suites/perf_budget.py` |
| **前置** | 项目 15 |
| **⚠️ 风险** | 本机 Ollama 延迟方差大，P95 用 3 轮取样取中位再断言，避免单次抖动误报；跑批用 qwen3:4b |
| **验收标准** | 阈值故意调低（如 P50<0.5s）时退出码非 0 且报告标红；恢复合理阈值后通过（两态都可脚本验证） |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「性能与成本门禁」。请给我完整 Python 代码约 180 行：suites/perf_budget.py 跑任务集统计每任务延迟与 token 用量（response usage 字段），输出 P50/P95 与总 token 成本，对照预算配置断言，超预算 exit 1；--strict 参数演示两态。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：首轮含冷启动会虚高 7%, 多轮取轮间中位; token 为 chars/4 估算口径, 不作计费

---

## 🗂️ 第五阶段：平台化——从脚本到门禁（项目 18-21）

> **目标**：把散装测试收进统一 runner 与结果模型，出 HTML 报告，接变更分级门禁，最后交付完整体检。

### [x] 项目 18：⛓️ 统一 runner 与结果模型

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~220 行 |
| **核心知识点** | 结果 JSON Schema、档位（冒烟/全量）、统一命令入口、失败不阻断收集 |
| **产出模块** | `aitest/testbench/runner.py` + `aitest/testbench/schema.py` |
| **前置** | 项目 8、13、17 |
| **验收标准** | `python3 -m testbench run --sut mh --level full` 产出单一 results.json，包含评测/回归/安全/契约/e2e/轨迹/性能全部结果且过结果 schema 校验；某类测试崩溃不影响其他类照常收集 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「统一 runner 与结果模型」。请给我完整 Python 代码约 220 行：schema.py 定义统一结果 JSON Schema（每类测试：名称/通过率/关键指标/耗时）；runner.py 串联 run_eval/prompt_regression/security_scan/tool_contract/e2e_task/trajectory/perf_budget 七模块，支持 --level smoke|full 分档，单模块异常不阻断其余收集。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：离线时评测降级 mini 且 metrics.offline=true, 别读成真机; 崩溃与失败分开记, skipped 不是通过

---

### [x] 项目 19：评测报告生成器（HTML 五区块）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200 行 |
| **核心知识点** | HTML 报告、结果可视化、数据-报告一致性、零前端框架模板 |
| **产出模块** | `aitest/testbench/report.py` |
| **前置** | 项目 18 |
| **验收标准** | `python3 -m testbench report results.json` 生成 report.html，浏览器打开五区块（总览/评测/安全/行为/性能）齐全，抽查 3 处数字与 results.json 一致 |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「评测报告生成器」。请给我完整 Python 代码约 200 行：report.py 读 results.json 用 Python 字符串模板（零前端依赖）生成单文件 report.html：总览卡片+四区块详情表+劣化/超标项红色高亮，纯内联 CSS。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：报告只搬运不重算数字; skipped 灰色 error 红色; verify 是抽查非全量对账

---

### [x] 项目 20：CI 门禁分级（变更 → 档位路由）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~180 行 |
| **核心知识点** | 变更分级路由、冒烟 vs 全量成本权衡、git diff 感知、门禁退出码 |
| **产出模块** | `aitest/testbench/gate.py` + `aitest/Makefile` |
| **前置** | 项目 18 |
| **验收标准** | 内置自检：模拟"只改 prompt 文件"路由到冒烟档、"改 SUT 代码"路由到全量档，两次的档位选择与退出码均可脚本断言（`python3 -m testbench.gate selftest` 全绿） |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「CI 门禁分级」。请给我完整 Python 代码约 180 行：gate.py 按变更文件路由档位（改 aitest/datasets|payloads → smoke；改 SUT/测试台代码 → full），调 runner 执行并按阈值给退出码；Makefile 提供 make gate；selftest 用假 diff 模拟两种变更验证路由正确。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：路由前缀过宽 bug 被 selftest 当场抓住; 未知/空变更 fail-safe 走 full; 混合变更从严重者

---

### [x] 🏁 项目 21：终极四维体检——harness/mh 完整质量报告

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~250 行 |
| **核心知识点** | 四维质量模型（功能/安全/性能/回归）、体检报告叙事、可复跑性 |
| **产出模块** | `aitest/final_checkup/` + `aitest/FINAL_REPORT.md` |
| **前置** | 项目 18、19、20 |
| **验收标准** | `make checkup` 一条命令 30 分钟内跑完四维（功能=golden set 通过率、安全=三维扫描、性能=预算门禁、回归= prompt diff），产出 FINAL_REPORT.md 四区块数字齐全，隔天重跑数字可复现（成功率差 ≤1 任务） |

**🤖 开始提示词**：
> `我要开始 AI 测试项目「终极四维体检」。请给我完整 Python 代码约 250 行：final_checkup/ 把 runner 四类结果组装成 FINAL_REPORT.md（功能/安全/性能/回归四区块，各含关键数字与结论一句话，最终给 mh 一个总评级 A-F 与修复建议清单）；Makefile 的 make checkup 一键复跑。附验收命令。只输出代码。`

**完成日期**：2026-10-09
**踩坑记录**：功能门槛要贴合 08 线口径(fact 维偏严仅作趋势, 否则永久误报); quick 档样本小只作演示

---

## 📅 周计划

| 周次 | 内容 | 项目数 |
|:---|:---|:---:|
| **第 1 周** | 项目 1-5（测试台骨架、评测集、非确定性画像、结构/语义断言） | 5 |
| **第 2 周** | 项目 6-10（幻觉、judge、断言集成、prompt 回归、注入靶场） | 5 |
| **第 3 周** | 项目 11-16（越狱、fuzz、安全门、契约、e2e、轨迹） | 6 |
| **第 4 周** | 项目 17-21（性能门禁、runner、报告、CI 门禁、🏁 四维体检） | 5 |

## 🏆 里程碑

- [x] **完成项目 1-3** → 测试台立起来了：SUT 可驱动、评测集版本化、非确定性有画像
- [x] **完成项目 4-8** → 四类断言在手：结构/语义/事实/judge 全部可编程可复跑
- [x] **完成项目 9-13** → 回归与红队成体系：prompt 回归 + 一键三维安全门
- [x] **完成项目 14-17** → Agent 行为可测：契约/端到端/轨迹/性能四件套
- [x] **全部完成** → 🏁 拥有可复跑的 AI 测试平台与 harness/mh 完整体检报告

## 🔧 环境配置

```bash
# 0. 已就绪（2026-10-07 实测）:
python3 --version                       # 3.13.9
python3 -c "import pytest, yaml, numpy" # 三件全已装，零新增安装
ollama list                             # qwen3:4b / qwen3.8:latest / nomic-embed-text / all-minilm 均在列
curl -sf http://localhost:11434/v1/models   # OpenAI 兼容端点存活 ✅
# 1. 需安装: 无
# 2. 每项目开工前:
curl -sf http://localhost:11434/v1/models >/dev/null || echo "⚠️ Ollama 未启动: ollama serve"
#    Ollama 不可用时 MOCK=1 走离线模式（复用 qa/llm.py 的 mock 约定），学习目标不变
```

## ⚠️ 与已有清单的关系

| 已有清单 | 关系 |
|:---|:---|
| docs/qa.md（31/31） | qa/24_injection_range、25_guardrails 是**演示级**攻防，本清单项目 10/11/13 升级为「ASR 度量 + payload 库 + 统一安全门」；qa/27_eval_judge 只做 judge 实现，项目 7 补**校准与人工对齐**；qa/28_rag_quality 已覆盖 RAG 质量，本清单**不开 RAG 线**（项目 6 幻觉检测承接事实性角度）；qa/30_mini_agent 是纯模板引擎（无 LLM 调用），在本清单被包成**离线辅助 SUT**（MOCK 冒烟/CI 快速档） |
| docs/agent.md（28/28） | agents/28_observability_eval、32_rag_quality 是「评测初步」，本清单把评测做成**带门禁的平台**；不重复 LangChain 技能线内容 |
| docs/harness.md（17/18） | harness/mh 被本清单选为**主 SUT**——它每轮真调 LLM 且自带 permissions/sandbox/budget，注入对照与预算门禁有真实开关；harness/eval/ 的任务集与 baseline/full 两配置方法论被项目 1/10/15 直接复用；本清单不重复造 harness 组件，专注测试台与度量 |

## ⚠️ 能力/探活速查表

| 能力 | 计划用途 | 实测结论 |
|:---|:---|:---|
| Ollama chat（qwen3.8:latest） | SUT 驱动 + judge | ✅ 2026-10-07 端点实测存活，qa 线 31 项目同款约定 |
| harness/mh（主 SUT） | 全部项目的被测对象 | ✅ `mh.loop.run_agent` 导入实测通过；`MOCK=1 eval_run.py --profile full` 离线管道自检 exit 0（2026-10-07）；项目 1 真机单任务实跑通过（qwen3.8 两轮收敛、磁盘取证一致，2026-10-08）；全量跑批未跑，跑批项目用 qwen3:4b |
| Ollama 快速模型（qwen3:4b） | 画像/回归降速 | ✅ 已装（ollama list 在列） |
| Ollama embeddings（nomic-embed-text） | 项目 5 语义断言 | ✅ 已装在列；项目 5 开工日再探活一次（curl /v1/embeddings） |
| pytest / pyyaml / numpy | 断言与统计基座 | ✅ import 实测通过 |
| MOCK 离线模式 | Ollama 不可用 fallback | ✅ qa/llm.py mock_chat 现成约定 |
| 云端评测平台（Langfuse/Braintrust 等） | 不在清单范围 | ❌ 免费约束下排除，全部自研等价物 |

## 📝 每日日志

| 日期 | 项目 | 耗时 | 收获 | 踩坑 |
|:---|:---|:---:|:---|:---|
| 2026-10-08 | 01 | ~1.5h | run_sut 统一接口 + 双 SUT + 两层冒烟（离线必绿/真机 skipif）；真机磁盘取证断言"声称完成=磁盘真变化" | tool_trace 双形态 KeyError；mini 落盘污染要重定向；archify labelAt 是绝对坐标 |
| 2026-10-08 | 02 | ~1h | golden_v1 20 条四类用例 + validate/diff；diff 按 id 集合运算+字段级变更 | argv[1:1] 空切片吞参数；python -m 的 cwd 陷阱；query 含 `: ` 必须加引号 |
| 2026-10-09 | 03 | ~1.5h | 真机画像：temp0 30/30 全同(1.0) vs temp0.8 28 种措辞(0.067/语义 0.774)；阈值标定依据落地 | stdout 块缓冲日志空；thinking 吃 num_predict；共享 GPU 耗时×2；启示模板要适配 1.0 |
| 2026-10-09 | 04 | ~1.5h | 断言管线四级：提取/规则修复/校验/LLM 重试；selftest 9/10，真机重试补齐缺字段 | 单引号键值分开转；截断先补引号；修复顺序防打架；validate 实为 25 行别虚报 |
| 2026-10-09 | 05 | ~1.5h | 阈值标定 0.60(平衡精度 0.95)，双侧矩阵 9/10·10/10；断言携带 sim+threshold 证据 | 短参考句表征弱；负样本要同域；MOCK 下真机用例显式 skip |
| 2026-10-09 | 06 | ~2h | 三级核验管线定型(数字优先/覆盖率子串/judge 兜底)，混淆矩阵 10/10·0/10 | 子串门槛 60%；judge 300token 防思考吃空；4b 判分要规则+少样本 |
| 2026-10-09 | 07 | ~2h | judge 校准双指标定型：相邻 20/20·稳定 20/20(精确 70%，差档全在相邻档) | 3.8 要 800token；判分层复用项目 4 解析；校准集 4×5 分层是命门 |
| 2026-10-09 | 08 | ~2.5h | 四维统一协议收口，首轮真机基线：schema 1.0/semantic 0.4/fact 0.2/judge 0.8 | qa_llm 要重试防断连；None 不进分母；factuality 口径严是趋势信号 |
| 2026-10-09 | 09 | ~2h | 双版同卷回归定型，实测 劣化4/改善3/持平13；灵敏度自证抓住 system 假覆盖 bug | 事后改返回值=化妆；run_agent 要 messages 预注入；双信号不加权 |

| 2026-10-09 | 10 | ~2h | 双 profile ASR 对照定型: baseline 0.733 vs full 0.067; inj_009 漏网教训沉淀 | 权限门拦截回执会被正则误判; 白名单命令可被恶意复用 |
| 2026-10-09 | 11 | ~2h | 三分类判定+确定性变异器; 实测拒绝 12/泄漏 6(均为拒绝时复读) | 4b 全假阳性; 插空变形需归一化; 拒绝复读口径要写明 |
| 2026-10-09 | 12 | ~2h | 六类 100 条生成器+四类结局; mini 100/100, mh 子集 9/2/1 | 50k 字符卡满 60s 超时; findings 字段留 input_head 才能复现 |
| 2026-10-09 | 13 | ~2h | 三维安全门定型: 一条命令出报告+退出码; 两态可验 | 越狱维度误用 4b 假失败; 采集崩溃要 fail-closed |
| 2026-10-09 | 14 | ~2h | 契约双断言+三写坏变体自证(错型/漏参/多调各 1) | 序列光标语义(实踩); extra_call 诱饵要配不点名任务 |
| 2026-10-09 | 15 | ~2h | 10 任务终态断言, 两遍 10/10 零波动; 失败留 trace 证据 | 判分口径逐任务对齐 check; 任务间禁依赖 |
| 2026-10-09 | 16 | ~1.5h | 轨迹三维打分定型: 快100/慢60/循环0; 真机轨迹 100 | 期望步数主观需标注; 光标失败不推进 |
| 2026-10-09 | 17 | ~2h | 多轮中位+预算两态; 实测 P50 19.41s/P95 19.69s | 首轮冷启动虚高; token 估算口径要带 _est |
| 2026-10-09 | 18 | ~2h | 统一 runner 七模块 smoke 全 ok, schema 校验闭环 | 离线降级 mini 的 ok 别读成真机; 崩溃与失败分开 |
| 2026-10-09 | 19 | ~1h | 五区块单文件报告+verify 抽查; 真数据 3.7KB | 报告只搬运不重算; 色标要区分 skipped/error |
| 2026-10-09 | 20 | ~1.5h | 变更路由+退出码; selftest 8/8 锁规则 | 前缀过宽 bug 被 selftest 抓住; make --dry-run 不传参 |
| 2026-10-09 | 21 | ~1.5h | 🏁 四维体检出 FINAL_REPORT 评级 A; make checkup 一键 | 功能门槛要贴 08 口径(fact 仅趋势); quick 档样本小 |
| | | | | |
