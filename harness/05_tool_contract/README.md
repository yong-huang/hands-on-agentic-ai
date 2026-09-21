# 05 · 工具契约层：故障注入下量出契约的真实价值

> 03 实验的悬案：强模型 + 顺任务域里契约治理零差异。本篇照方抓药——
> **故障注入**：首个工具调用的参数被 harness 悄悄改坏（path 变数字、content
> 消失），然后比较两种工具层的自愈。`mh/tools.py` 同时上线：`@tool` 从类型
> 注解自动生成 schema，jsonschema 在**执行前**拦截，错误翻译成"哪里错、
> 怎么改"。loop 零改动换装成功——`Registry.to_loop_tools()` 直接喂 `run_agent`。

## 1. 为什么需要它

04 的工具表里 `fn(**args)` 是裸奔的：参数错不提前拦、异常直传模型。
工具系统的工业形态是**契约**——模型看到的不是函数而是 schema，harness 在
意图与副作用之间做校验。本篇还负责回答方法论问题：**测 harness 必须制造
故障**，否则 40 次调用全成功，A/B 配置连一次分歧的机会都没有（03 的教训）。

## 2. 总览：核心机制一图看懂

![工具契约时序](images/tool_contract.sequence.svg)

**怎么看这张图**：与 04 的循环时序相比，唯一变化是模型与执行之间插入了
`mh.tools`：参数先过 schema 校验，不合法就**在执行前**把修正指引回给模型；
合法才放行到工具函数。拦截点在副作用之前——这是契约的硬价值，与模型强弱无关。

心智模型一句话：**契约 = 在错误变成副作用之前，把它变成一条修正指令。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/05_tool_contract/images/tool_contract.html)
> （或本地打开 [`images/tool_contract.html`](images/tool_contract.html)）。

## 3. 快速开始

```bash
cd harness/05_tool_contract
MOCK=1 python3 demo.py     # 离线：剧本走"故障→自纠"全链路
python3 demo.py            # 真机：契约/裸奔各跑一次带故障的任务（验收口径）
python3 demo.py --trace    # 打印两种配置的完整消息历史
```

真机实测（2026-09-18，qwen3.8，两配置均被注入同样的参数故障）：

```text
B 契约版: 轮次 4, 错误回传 1 次, 文件落盘(2 行) ✅
  write_file(...) → [error] 参数校验失败: 工具 write_file 的参数
                     ['(根对象)'] 不合法 —— 'content' is a required property。
                     必填参数: ['path', 'content']。请修正后重新调用。
  write_file(...) → [ok] ok: 已写入 note.txt
A 裸奔版: 轮次 4, 错误回传 1 次, 文件落盘(2 行) ✅
  write_file(...) → [error] 工具 write_file 执行失败:
                     TypeError: write_file() missing 1 required positional
                     argument: 'content'。请修正后重试。
```

验收达成：**校验失败 → 错误回传 → 第二次调用成功**的完整两轮在日志可见；
`04 demo` 在 loop 零改动下回归通过。

## 4. 核心概念

### 4.1 契约三件套

| 组件 | 职责 | 一句话 |
|:--|:--|:--|
| `@tool` | 类型注解 + docstring → JSON Schema | 工具即函数，schema 不手写 |
| 校验器 | jsonschema 在**执行前**拦截 | 错误不变成副作用 |
| 错误翻译 | `ValidationError → 哪里错+必填清单+怎么改` | 错误是给模型的输入，不是给人的日志 |

### 4.2 故障注入：测 harness 的正确姿势

`build_tools()` 给每个工具包了一层 `poisoned`：首个调用参数被改坏（只注入
一次）。这就是 03 结论的落地——**顺任务测不出差异，故障域才能**。注入点
在 harness 层而非提示词层，保证 A/B 吃到完全相同的故障。

### 4.3 诚实报告：27B 模型下两种错误都能自愈

真机结果 A/B 同为 4 轮 1 次错误回传后恢复——连模型 thinking 里的反省措辞
都几乎一样。差别在**质**不在**量**：契约版拦截发生在执行前（零副作用风险）、
错误信息指名 schema 期望。差距要等弱模型（18 的 qwen3:4b 对照）或连环故障
（09 预算）才拉开。**连续两篇的零差异不是实验失败，而是"harness 价值 ∝
故障密度"这条规律的两次独立验证。**

## 5. 代码关键点

```python
@tool
def write_file(path: str, content: str, cwd: str = None) -> str: ...
# 类型注解 → schema; cwd 是运行时上下文, 对模型不可见

Tool.call(args)  # 永不抛异常: (ok, 文本) —— 错误也要成为模型的输入
Registry.to_loop_tools()  # 产出 04 循环认的工具表, loop 一行未改
```

本篇的坑：**闭包晚绑定**——循环里给每个工具包 `poisoned` 时引用了循环变量
`base`，所有包装函数共享了最后一个工具，write_file 实际调到了 count_lines。
修法是工厂函数绑定当次迭代的值。这是 harness 工程师的日常：**包装器比
被包装者更容易出错。**

## 6. 文件结构

```
harness/
├── mh/
│   ├── loop.py          # 主循环（本篇零改动——换装成功的证明）
│   └── tools.py         # ⛓️ 本篇: @tool / Tool / Registry
└── 05_tool_contract/
    ├── README.md
    ├── demo.py          # 故障注入对照实验
    └── images/          # 时序图三件套
```

## 7. 深入要点

- **校验为什么在执行前而不是把异常包起来？** 执行前拦截 = 副作用零风险；
  异常包装 = 错误已经发生，只是"说得好听"。权限门（07）同位置同哲学。
- **schema 该细到什么程度？** enum/格式约束越多，拦截越早，但 schema 膨胀
  吃上下文、增加模型理解成本。alphaXiv 论文的 token 通胀教训在这里适用。
- **为什么 `cwd` 不进 schema？** 工作目录是任务级约束，模型无权选择"在哪
  执行"——与 04 的权限观一致，07 会把它升级成显式规则。
- **`Tool.call` 永不抛异常对吗？** 对 harness 而言对——任何异常都要变成
  模型可读的文本。但对宿主进程，还有 06 沙箱兜底。

## 8. 总结

契约层上线：schema 自动生成、执行前拦截、错误翻译，loop 零改动换装。
真机故障注入实验再次验证：**强模型把错误信息质量的差距抹平了大半**——
harness 的价值在故障密度高的地方。下一篇 [06_sandbox](../06_sandbox/README.md)
给执行层上刑具：超时杀死、输出截断、目录隔离，让 `while True` 也拖不垮宿主。
