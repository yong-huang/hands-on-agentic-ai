# 13 · 工具调用错误处理：分类、重试与大结果卸载

> 现实里 API 会超时、参数会非法、查询会扑空，工具还会一口气吐出 50KB
> 文本撑爆上下文。给工具层装上三件护甲：结构化错误分类、区分暂时/永久
> 错误的重试策略、超长结果自动卸载为文件占位符。

## Background

在没有统一错误处理之前，Agent（能自主调用工具完成任务的 LLM 程序）调用
工具就是裸调用：直接执行函数，出了异常任其往上抛，或者把 `str(e)` 的
原文塞进对话继续跑。

这种做法在两个场景撞墙。其一是重试决策没有依据：网络抖动和参数写错在
程序眼里都是"抛了异常"，重试参数错误是白烧调用次数，不重试网络抖动则
任务直接失败。

其二是上下文被污染：Python 异常堆栈几十行，模型读不懂也用不上。一次
`read_file` 返回 80K 字符，直接进 messages（对话消息列表）就是几十万
token（模型计费与计长的最小文本单位）的账单和超限报错。

生产级 Agent 框架因此把工具调用包进一层执行器：错误先分类再决定重试，
错误信息裁剪成模型能行动的短句，超大结果改存文件。本实验用一段可读的
Python 代码实现这个生产 Agent 工具层的标准形态。

## What

工具调用错误处理是一种在 Agent 工具层统一兜底三类问题的机制：错误分类、
重试控制与大结果卸载（context offloading，把超长结果移出上下文、只留
一个引用）。本实验的载体是 `SafeExecutor`（执行器类，管分类与重试）和
`ResultManager`（结果管理器类，管体量检查与卸载）。

**结构化错误：分类 + retryable 标志**——retryable（可重试标志）决定
是否消耗重试预算，这是错误处理里最重要的一个判断：

| 类别 | 例子 | retryable | 理由 |
| :--- | :--- | :--- | :--- |
| timeout | 网络超时 | True | 等等再试可能就好 |
| internal | 未知异常 | True | 偶发性默认可再试 |
| invalid | 参数为空/非法 | False | 再试一百次也非法 |
| not_found | 查询无结果 | False | 结果确定性为空 |

**重试策略：预算 + 退避**（backoff，重试前等待一段时间再试的策略）——
`SafeExecutor(max_retries=2)`：retryable 错误 `sleep(retry_delay)` 后
重试，最多 3 次尝试；不可重试立即 break。

`history` 记录每次尝试的结果与耗时，`summary()` 汇总成功率。生产版会加
指数退避与抖动（每次重试的等待时间翻倍并加随机偏移），demo 用 0.1s
加速。

**大结果卸载**——上下文里只留一个**可寻址的引用**，需要时再配一个
`read_file` 工具按行取回。可以把上下文想象成内存、卸载文件想象成交换
分区：工作集留在上下文，全量放外存。但和虚拟内存不同的是，这里的"换入"
不会自动发生——模型必须显式调用 `read_file` 才能取回内容。

心智模型一句话：**错误要"分类可重试、信息可行动"，结果要"大而卸载、
小而直传"。**

## When to Use

判断标准是工具是否接触"不可靠的外部世界"——网络、数据库、文件系统都算。

典型场景：

- 给 LLM 接外部工具时（HTTP API、数据库、搜索）：网络与参数错误是日常，
  不分类就没法决定该不该重试；
- 工具会返回大段文本时（日志检索、网页抓取、读文件）：不卸载就会一次性
  打爆上下文窗口；
- 无人值守的长任务：重试预算与尝试历史（`history`/`summary()`）是事后
  排障的唯一线索。

何时不用：

- 工具全是本地纯函数（字符串处理、数值计算），遇不到环境类错误，一个
  普通 `try/except` 就够；
- 一次性脚本、人工盯着的调试：出错直接看原始堆栈更快。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 裸 `try/except` | 只捕获不分类，模型收到原始堆栈 | 一次性脚本、本地纯函数工具 |
| 重试库（如 Python 的 tenacity） | 只管重试节奏，不管错误语义与大结果 | 只需要"失败再多试几次" |
| `SafeExecutor + ResultManager`（本实验） | 分类 + 重试预算 + 大结果卸载一体 | 给 LLM 用的工具层 |

## Quick Start

前置条件：Python 3，无第三方依赖；`--demo` 模式完全离线，不需要 Ollama
（本地大模型运行环境）。

```bash
cd agents/13_error_handling
python error_handling.py --demo          # 离线：7 步错误/卸载演示，不需要 Ollama
python error_handling.py "查询 python 的资料"   # 真实 Agent 循环
```

`--demo` 依次演示七件事：

1. 正常调用；
2. 空参数 → `invalid`（不重试，1 次即止）；
3. 查无结果 → `not_found`（不重试）；
4. `weather('timeout')` → 重试 2 次共 3 次尝试全失败；
5. `big_data` 返回超长结果 → 被卸载成 `<file:...>` 占位符；
6. `executor.summary()` 与逐条尝试历史（OK/ERR 标记）；
7. 清理临时目录。

预期关键输出：`[ERR] timeout` 出现 3 次 attempts、
`<file:/tmp/agent_result_.../big_data_1.txt> (1000 chars offloaded)`。

第二条命令需要本地模型服务在线，没有 Ollama 会连接失败——先用 `--demo`
跑通全部机制即可。

## How It Works

机制分两条线：错误线（分类 → 重试 → 回传）和结果线（体量检查 → 卸载）。

执行器主体——`except` 只捕获本实验定义的 `ToolError`（带 `category`、
`retryable`、`detail` 字段的异常类），成功路径也要过体量检查：

```python
class SafeExecutor:
    def execute(self, fn, **kwargs):
        attempts = 0
        while attempts <= self.max_retries:
            attempts += 1
            try:
                result = fn(**kwargs)
                self._log("OK", fn, attempts)
                return ResultManager.check_size(str(result))   # 成功也要过体量检查
            except ToolError as e:
                self._log("ERR", fn, attempts, e)
                if not e.retryable:
                    break                                       # 永久错误不浪费预算
                time.sleep(self.retry_delay)
        return f"Error [{e.category}]: {e.detail}"              # 最终以字符串回传模型
```

代码与 demo 输出互相印证。`invalid`/`not_found` 只出现 1 次 attempts，
因为 `retryable=False` 走 `break`；`timeout` 出现 3 次 attempts，因为
`retryable=True` 走 `sleep` 后重来。

`<file:...>` 占位符则来自成功路径上的 `ResultManager.check_size`。

结果线的卸载逻辑——超过阈值就把完整内容写盘、返回占位符：

```python
if len(result) > MAX_RESULT_SIZE:                      # demo 200, 生产 80000+
    path = write_temp(f"{tool_name}_{n}.txt", result)  # 完整内容落盘
    return f"<file:{path}> ({len(result)} chars offloaded)"
```

错误回传的形态——模型读到分类与细节后通常能自行调整（换关键词、问
澄清）：

```
{"role": "tool", "tool_name": "search", "content": "Error [not_found]: no result for 'quantum'"}
```

喂给模型的分寸：只传"分类 + 一句话细节"——类别机器可判定、细节模型可
行动。把异常堆栈直接丢给模型是错的：噪声大且可能含敏感路径。

## Pitfalls & Q&A

踩坑清单（现象 + 原因 + 解法）：

- **分类体系外的异常让程序崩溃**。现象：工具抛了非 `ToolError` 的异常，
  执行器没接住。原因：`except` 只写了 `ToolError` 一种。解法：兜底把
  未识别的异常归类为 `internal(retryable=True)`，别让它裸穿。
- **卸载的临时文件越积越多**。现象：临时目录残留大量 offload 文件。
  原因：写盘之后没人负责清理。解法：给 `ResultManager` 配 `reset()`，
  任务结束调用——demo 第⑦步演示了这一步。
- **MAX_RESULT_SIZE 取值失当**。现象：取小了正常结果也被卸载、模型频繁
  取回片段；取大了照样撑爆上下文。原因：阈值没按模型上下文与并发量定。
  解法：demo 的 200 只是教学值，生产 80000+ 按所用模型定。

**Q1: 重试要注意什么？**

只重试暂时性错误（见 What 节的 retryable 表）；设预算上限；生产环境用
指数退避 + 抖动，防止大量请求同时重试把服务压垮（雪崩）；重试历史留痕。

**Q2: 大结果为什么不能直接进上下文？**

token 成本随结果长度线性增长，还会把真正相关的上下文挤出窗口。机制见
How It Works 的卸载逻辑，结论是卸载到外存、上下文只留引用、按需取回。

**Q3: 什么错误不该让模型看到？**

认证失败、配额耗尽等"重试无意义且涉及安全"的错误应由运行时接管
（熔断——连续失败后暂停调用一段时间，以及告警），对模型只返回统一的
"服务暂不可用"。
