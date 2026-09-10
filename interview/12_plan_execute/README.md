# 12 · Plan-and-Execute 规划器

> 覆盖面试题：Agent 的 Planning 怎么实现？多步任务的子目标分解怎么做？
> 先规划后执行（Plan-and-Execute）vs ReAct 逐拍决策，同一组旅行任务对跑：
> 规划器一次性输出子目标 DAG（JSON: 工具/参数/依赖），执行器按拓扑序调度、
> 工具调用零 LLM 消耗，最后做预算校验。工具全 mock 数据。

## 1. 运行与实测

```bash
MOCK=1 python plan_execute.py    # 离线: 脚本化规划与轨迹
python plan_execute.py           # 真实: qwen3.8 做规划与 ReAct 决策
```

真机实测（2026-09-09，qwen3.8）：

| 指标 | Plan-and-Execute | ReAct |
|:--|:--:|:--:|
| 成功率 | **3/3** | 2/3 |
| LLM 调用 | **1 次/任务** | 12 次/任务 |
| token | ≈2004 | ≈4944 |

真机规划器会"自由发挥"——给子目标发明工具不存在的参数（`start_date`、
`destination`、`check_in`…）或漏掉必需的 `city`。执行器的参数防御：
按工具签名**丢弃发明参数 + 从任务上下文补全缺失参数**（trace 里可见
"丢弃规划器发明的参数 ['start_date','end_date']"）——规划与执行解耦后，
执行侧必须有 schema 级防御（呼应项目 15/20）。ReAct 侧 2/3 是思考模型
在 12 步预算内的诚实结果：逐拍决策每步都烧一次长思考。

## 2. 面试要点

- Plan-and-Execute = 一次 LLM 规划（子目标 DAG）+ 程序化调度执行；
  LLM 调用从 O(步数) 降到 O(1)，步间不再互相污染上下文。
- 可解释性：规划器给出显式 DAG（打印即审计），ReAct 只有事后轨迹；
  出错时 DAG 能定位是"哪一步的依赖"错了。
- 代价与边界：规划时信息不全（查不到天气就无法按天气调整行程）——
  生产常见混合式：先规划，关键结果回来后允许局部重规划（项目 13）。
- 实践教训：LLM 规划的参数必须按工具 schema 校验/修复，不能直接 `**args`。

## 3. 文件结构

```
interview/12_plan_execute/
├── README.md            # 本篇
└── plan_execute.py      # DAG 规划 + 拓扑执行 + ReAct 对照（约 330 行）
```
