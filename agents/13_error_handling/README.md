# 13 · 工具调用错误处理：分类、重试与大结果卸载

> 现实里 API 会超时、参数会非法、查询会扑空，工具还会一口气吐出 50KB
> 文本撑爆上下文。给工具层装上三件护甲：结构化错误分类、区分暂时/永久
> 错误的重试策略、超长结果自动卸载为文件占位符。

## What

**结构化错误：分类 + retryable 标志**——retryable 决定是否消耗重试预算，
这是错误处理里最重要的一个判断：

| 类别 | 例子 | retryable | 理由 |
| :--- | :--- | :--- | :--- |
| timeout | 网络超时 | True | 等等再试可能就好 |
| internal | 未知异常 | True | 偶发性默认可再试 |
| invalid | 参数为空/非法 | False | 再试一百次也非法 |
| not_found | 查询无结果 | False | 结果确定性为空 |

**重试策略：预算 + 退避**——`SafeExecutor(max_retries=2)`：retryable
错误 `sleep(retry_delay)` 后重试，最多 3 次尝试；不可重试立即 break。
`history` 记录每次尝试的结果与耗时，`summary()` 汇总成功率。生产版会加
指数退避与抖动，demo 用 0.1s 加速。

**大结果卸载（context offloading）**——上下文里只留一个**可寻址的引用**，
需要时再配一个 `read_file` 工具按行取回。和操作系统的虚拟内存是同一个
思想：**工作集留在上下文，全量放外存**：

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

心智模型一句话：**错误要"分类可重试、信息可行动"，结果要"大而卸载、
小而直传"。**

## Why

工具错误处理的双重要求相互矛盾：**对程序**要分类明确（能不能重试？），
**对模型**要信息充分（下一步怎么办？）。更隐蔽的是成功路径上的陷阱——
一个 `read_file` 返回 80K 字符，直接进 messages 就是几十万 token 的账单和
超限报错。`SafeExecutor + ResultManager` 组合是生产 Agent 工具层的标准
形态。

## How

```bash
cd agents/13_error_handling
python error_handling.py --demo          # 离线：7 步错误/卸载演示，不需要 Ollama
python error_handling.py "查询 python 的资料"   # 真实 Agent 循环
```

`--demo` 依次演示七件事：①正常调用；②空参数 → `invalid`（不重试，1 次
即止）；③查无结果 → `not_found`（不重试）；④`weather('timeout')` →
重试 2 次共 3 次尝试全失败；⑤`big_data` 返回超长结果 → 被卸载成
`<file:...>` 占位符；⑥`executor.summary()` 与逐条尝试历史（OK/ERR 标记）；
⑦清理临时目录。

预期关键输出：`[ERR] timeout` 出现 3 次 attempts、
`<file:/tmp/agent_result_.../big_data_1.txt> (1000 chars offloaded)`。

执行器主体——成功路径也要过体量检查：

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

## Deep Dive

**错误喂给模型的分寸**：传"分类 + 一句话细节"——类别机器可判定、细节
模型可行动。把异常堆栈直接丢给模型是错的：噪声大且可能含敏感路径。

踩坑清单：

- 未识别的异常要归类为 `internal(retryable=True)`，别让它裸穿；
- 卸载目录要配 `reset()` 清理，demo 结束演示了这一步；
- MAX_RESULT_SIZE 按模型上下文与并发量定，demo 的 200 只是教学值。

## Q&A

**Q1: 重试要注意什么？**

只重试暂时性错误；设预算上限；指数退避+抖动防雪崩；重试历史留痕。

**Q2: 大结果为什么不能直接进上下文？**

token 成本线性爆炸且挤掉真正相关的上下文；应卸载到外存、上下文只留
引用，按需取回片段。

**Q3: 什么错误不该让模型看到？**

认证失败、配额耗尽等"重试无意义且涉及安全"的错误应由运行时接管
（熔断/告警），对模型只返回统一的"服务暂不可用"。
