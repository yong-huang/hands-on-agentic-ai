# 01 · 测试台骨架：把被测 Agent 包成一个 run_sut() 接口

> aitest 线的第一个项目不写任何业务断言，先回答三个问题：测谁、怎么调、拿到什么。
> 产出测试台包 `aitest/testbench/`：一个 `run_sut()` 统一接口接两个被测对象——每轮真调 LLM 的 `harness/mh`，与零 LLM 的 `qa/30_mini_agent`。
> 读完你能把一个 Agent 包成可编程调用的 SUT，并用 pytest（Python 生态标准的测试框架）把快速自检分成"离线必绿"与"真机诚实跳过"两层。

## Background

拿到一个 Agent，想确认它的行为是否正确，最常见的做法是在被测对象目录里写个临时脚本：import 它、拼好参数、把输出 print 出来靠肉眼判断。

这种做法在三个地方撞墙。换一个被测对象，import 路径、调用方式、返回值结构全部重写；print 没有断言，"看着像对"无法机器判定；临时脚本用完即弃，同一个验证下周再做还是从零开始。

软件测试的成熟解法是为被测系统做一个稳定的调用层：测试代码只面向调用层写断言，被测对象怎么启动、怎么响应全部封在层内。被测对象在测试领域有固定名字——SUT（System Under Test，被测系统）；这层包装叫适配层（把被测对象的专属调用细节隔离进单一模块，上层代码不感知细节）。

本实验把这套结构落进本仓库：aitest 线后续 20 个项目的断言，全部长在 `run_sut()` 这一个接口上。

## What

SUT 适配层是一种"把被测对象包成统一函数调用"的测试设施：输入任务文本，输出结构化结果；被测对象可以整体替换，上层断言代码一行不改。

可以把适配层想象成电源转换插头——电器（测试断言）只认插座标准（统一接口），转换插头负责对接各国插座（不同 Agent）。但和转换插头不同的是：适配层还要把不同形状的"输出电压"整形成统一的结果结构，这是插头不需要做的部分。

统一结果模型 v0 一共 7 个字段：

| 字段 | 含义 | 来源 |
|:--|:--|:--|
| `sut` | 被测对象标识 | `"mh"` / `"mini"` |
| `task` | 原始任务文本 | 原样透传 |
| `final` | 最终回答文本 | mh 收敛轮 / mini 自评结论 |
| `turns` | 实际轮次 | mh 循环轮数 / mini 计划步数 |
| `tool_trace` | 工具调用轨迹 | 逐轮记录 |
| `cwd` | 任务工作目录 | 缺省临时目录 |
| `elapsed_s` | 耗时秒 | 性能门禁的原料（项目 17） |

## When to Use

典型场景：

1. 给 Agent 写回归断言（回归：改动后重测既有行为，防止劣化）：断言只认 `run_sut()` 的返回结构，不关心被测对象内部。
2. 同一套用例换模型对比：`LLM_MODEL` 环境变量切换，断言零修改。
3. CI（持续集成，代码提交后自动跑检查的机制）离线自检：`MOCK=1` 用预置脚本替代模型服务，无网络也全绿。

何时不用：一次性探索实验，直接调被测对象更快；只读代码不运行的场景，用不上调用层。

同类方案对比：

| 方案 | 差异 | 何时选它 |
|:--|:--|:--|
| 测试里直接 import 被测对象 | 每换对象重写驱动代码 | 只测一个对象、一次性 |
| HTTP API 层测试 | 要先起服务、管端口 | 被测对象必须是独立进程 |
| 进程内适配层（本实验） | 一个函数拿到结构化结果 | 同一断言覆盖多个被测对象 |

## Quick Start

前置条件：Python 3.10+；真实模式需要本机 Ollama（在本地运行大语言模型的工具）与 `qwen3.8:latest` 模型，离线模式两者都不需要。

```bash
cd aitest/01_testbench_sut
python3 testbench_sut.py                       # 全流程：探活→离线→真机→pytest
MOCK=1 python3 testbench_sut.py                # 纯离线
cd .. && MOCK=1 python3 -m pytest tests/ -q    # 冒烟套件（离线必绿）
cd .. && python3 -m pytest tests/ -q           # Ollama 在线时真机用例不跳过
```

全流程真机实测输出：

```text
=====> [probe] Ollama 探活(真实模式前置检查)
  http://localhost:11434/v1/models -> 存活 ✅
  LLM_MODEL = qwen3.8:latest (默认)

=====> [mock] 离线层: 同一个 run_sut 接口, 两个被测对象
  mh  (脚本剧本): [mh] turns=2 tools=['run_bash'] 0.03s final='已完成: hi.txt 已创建, 内容为 ok。'
  mini(模板链路): [mini] turns=3 tools=['mini-agent', '查库存 A1', '下单 A1 x2', '沉淀订单事实到记忆'] 0.002s final='ok'
  断言: mh 收敛有 final ✅ / mini 全链路自评 ok ✅

=====> [real] 真实层: mh 真调 LLM, 声称完成必须等于磁盘真变化
  模型回复: [mh] turns=2 tools=['run_bash'] 6.07s final='已创建 hi.txt,内容为 `ok`。'
  磁盘取证: /var/folders/.../aitest_sut_aceiwv8o/hi.txt -> 'ok'
  断言: final 非空 ✅ / hi.txt 内容=ok ✅ (测试台第一次抓住'真完成')

=====> [pytest] 冒烟套件(MOCK=1, 离线)
  4 passed, 1 skipped in 0.03s

=====> 项目 1 验收完成: 含真实层 ✅
```

诚实预期：Ollama 不在线时 real 段打印"诚实跳过"并以"离线层 ✅"收尾，不报错——这是设计行为。真机耗时与模型相关：qwen3.8（17GB）首跑含加载约 30 秒，模型已在内存时约 6 秒。

## How It Works

### 统一接口：一个函数签名

```python
run_sut(task, sut="mh", system=None, max_turns=8, model=None, sandbox=None, chat_fn=None)
# → {"sut", "task", "final", "turns", "tool_trace", "cwd", "elapsed_s"}
```

`chat_fn` 是关键注入口。`mh.loop.run_agent` 本就接受自定义对话函数，`MOCK=1` 时适配层传入 `mock_chat_fn()`（按次序回放"工具调用→文本收敛"两步剧本的假模型）；真实模式传 `None`，走默认 LLM 客户端。

对照 Quick Start 输出：mock 行 0.03 秒与 real 行 6.07 秒跑的是同一段循环代码，差别只在 chat_fn 的真假。

`sandbox` 缺省时每次调用自动建临时目录，任务产生的文件落在隔离目录里，测试之间互不污染。`model` 参数临时覆盖 `LLM_MODEL` 环境变量，跑完恢复原值。

### 辅 SUT：确定性对照样本

`qa/30_mini_agent` 是纯模板引擎（规划、护栏、执行全靠规则，零 LLM 调用）。适配层用 importlib（按文件路径动态加载 Python 模块的标准库）加载它，驱动 plan→execute→evaluate 三步。

它的价值是确定性：同一任务连跑两次输出完全一致（冒烟测试 test_mini_sut_deterministic 断言这一点），适合验证"测试台本身没坏"。

加载时有一个必要处理：mini 的 Tracer 与 Memory 会向自己目录写 trace.jsonl、memory.json，适配层把这两个路径重定向到临时目录，测试因此不弄脏被测对象自己的文件。

### 探活门与两层测试

`suts.ollama_alive()` 用标准库 urllib 探测本地模型服务，所有真实调用之前先过这道门。冒烟测试（smoke test，只验证最基本通路可用的快速自检）因此分两层：离线层（mock 协议、确定性对照、结果模型契约）任何环境必绿。

真机层用 `pytest.mark.skipif` 声明"MOCK=1 或服务不在线就跳过"，跳过在结果里留一行 `s`（skipped）而不是假装通过。

真机层断言的不只是模型说了什么：test_real_mh_creates_file_and_reports 在 SUT 汇报完成后打开磁盘核对 `hi.txt` 内容——声称完成与磁盘证据必须同时成立。

## Pitfalls & Q&A

### 踩坑清单

1. **tool_trace 有两种形态**。现象：汇总函数对 mh 正常、对 mini 抛 `KeyError: 1`。原因：mh.loop 产出 dict（含 tool/args/result 键），mini 产出 (type, name) 元组，同一字段名下结构不同。解法：按类型分派取名字；统一结果模型约束"字段存在"，不约束内部结构一致。

2. **被测对象不是单个函数**。现象：没法用一行调用驱动 mini。原因：mini 的可见入口是 main() 演示脚本，可编程入口是 plan/execute 函数组。解法：适配层复现 main 的调用序列并用 redirect_stdout 捕获打印，演示输出与编程接口解耦。

3. **真机模型首跑极慢**。现象：真实模式第一次约 30 秒，第二次 6 秒。原因：17GB 模型首次要从磁盘加载进内存。解法：探活门只判断"在不在线"，耗时预期写进文档而不是压进断言超时。

### 深入问答

**Q：主 SUT 为什么选 harness/mh，而不是同仓库更小的 mini_agent？**

测试台要测的是 LLM 行为：非确定性（同一输入多次运行输出不同）、工具选择、安全防御。mini_agent 零 LLM 调用，对它做温度方差、语义相似度、注入攻击实验全部得不到真实行为数据；mh 每轮真调模型，且自带权限/沙箱/预算模块，后续安全与性能项目有真实开关可对照。

**Q：MOCK=1 全绿证明了什么，没证明什么？**

证明测试台管道是通的：接口、结果模型、断言、轨迹解析都工作。没证明被测 Agent 行为正确——剧本是写死的，模型没有参与。所以后续每个项目的验收都分两档：MOCK 档验证机制，真实档验证行为。

**Q：结果模型为什么现在是手写 dict，不先定 JSON Schema（机器可校验的结构声明）？**

字段还在生长：项目 8 要加四类断言结果，项目 17 要加 token 用量。v0 先用最小契约跑起来，项目 18 统一 runner 时再冻结成 schema——过早冻结会逼着前面十几个项目反复改结构。
