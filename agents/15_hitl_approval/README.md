# 15 · HITL 审批：分级授权与人工确认

> 完整的 HITL（Human-in-the-loop）审批层：auto/confirm/deny 三档策略、
> 终端人工确认、全程审计日志——模型的每次工具请求都要先过这道门。

## Background

在审批层出现之前，Agent 的工具管控通常只有一张白名单：登记过的工具就
执行，没登记的就拒绝。这是一个"允许/不允许"的二元判断，Agent 拿到
许可后完全自主执行。

二元判断在真实工具集面前不够用：`calculator` 随便跑没问题，`delete_file`
删错了用户要找人对质，`format_disk` 想都别想——三种风险等级挤在同一个
开关里。更麻烦的是没有留痕：工具执行了就执行了，出了事故无法回答
"谁批准的、什么时候、参数是什么"。

HITL（Human-in-the-loop，人在回路——关键决策交由人确认）审批层因此
成为生产 Agent 平台的标准组件：在模型请求与工具执行之间插入分级策略、
人工确认与审计日志（audit log，记录谁在何时对哪个工具做了什么决定的
日志）。本实验用三件套实现这个安全层的最小完整形态。

## What

HITL 审批层是一种在"模型请求工具"与"工具真正执行"之间插入人工决策
的机制。三个部件各管一段：`ApprovalPolicy`（策略表，工具名 → 档位）、
`ApprovalGate`（审批门，执行判定与问人）、`ApprovalLog`（审计日志，
全程记账）。

所有工具按三档管理：

| 档位 | 语义 | 本篇示例 |
| :--- | :--- | :--- |
| auto | 放心工具，立即执行 | calculator / get_weather / search |
| confirm | 危险工具，暂停问人 | delete_file / send_email / execute_command |
| deny | 毁灭性工具，无条件拒绝 | format_disk / rm_rf / drop_database |

**未登记的工具默认 confirm**（fail-safe：出错了要倒向更安全一侧的设计
原则）——新工具上线时宁可多问一句，不可静默放行。

审计日志的每条记录格式如下：

```python
{"time": "2026-09-02T15:30:45", "tool": "delete_file",
 "args": {"filepath": "important.db"}, "policy": "confirm",
 "decision": "denied", "detail": "User denied"}
```

心智模型一句话：**策略定档位、人工把关、日志记全程——模型说了不算。**

## When to Use

判断标准：工具是否触碰"不可撤销的真实世界"。

典型场景：

- 工具有真实副作用时（删文件、发邮件、执行命令、花钱操作）：一次误
  调用的代价远高于问一句的时间；
- Agent 面向企业或生产环境部署时：合规与事故追责要求每一步留痕；
- 新工具刚上线、风险未知的灰度期：默认 confirm 起步，观察后再降档。

何时不用：

- 全是只读工具（计算、查天气、搜索）：全配 auto，审批层本身不拦截
  任何东西，加了也是空转；
- 个人调试脚本、自己盯着跑的交互会话：出问题当场就能看到。

同类方案对比：

| 方案 | 差异 | 什么时候选它 |
| :--- | :--- | :--- |
| 白名单（12 实验主题） | 只有允许/拒绝两档，无留痕 | 纯只读工具集 |
| HITL 审批层（本实验） | 三档策略 + 人工确认 + 审计日志 | 有副作用的工具、生产部署 |
| 全自动 + 事后审计 | 不阻塞执行，只事后追责 | 低风险、高吞吐的批处理管道 |

## Quick Start

前置条件：Python 3，无第三方依赖。`--demo` 用预置决策序列，不需要
人工输入；`--interactive` 会在终端真实等你按键。

```bash
cd agents/15_hitl_approval
python hitl_approval.py --demo          # 模拟模式：预置 y/y/n 决策序列
python hitl_approval.py --interactive   # 交互模式：真实在终端等你按 y/n
```

运行输出（节选）：

```text
============================================================
HITL Approval -- Demo Mode (no Ollama)
============================================================

--- Approval Policy ---
  calculator           -> auto       [SAFE]
  delete_file          -> confirm    [RISKY]
...
--- Auto-approve mode (simulating user decisions) ---
  [OK] calculator({'expression': '2+3'}) -> ALLOWED: Auto-approved (safe tool)
  ...
  [X] format_disk({}) -> BLOCKED: Tool 'format_disk' is forbidden
  ...
  [X] delete_file({'filepath': 'important.db'}) -> BLOCKED: User denied

--- Approval Log: 1 auto, 3 approved, 1 denied, 1 forbidden, 6 total ---
  [.] calculator           auto         
  [+] delete_file          approved     User approved
  ...
  [!] format_disk          forbidden    Tool is forbidden by policy
  ...
  [-] delete_file          denied       User denied
...
```

`--demo` 依次演示：打印策略表 → auto-approve 模式演示 6 条调用的自动
批准（`rm -rf /` 这类模拟命令被批准、`delete_file important.db` 被
"用户"拒绝、`format_disk` 被策略禁止）→ 打印审计日志与 `summary()` 计数。

`--interactive` 用同样的 6 条调用，但 confirm 级工具会真的暂停：
`Approve? [y/n]:`。Ctrl+C/Ctrl+D 视为拒绝（fail-closed：问不到人就
拒绝，见 How It Works）——不想继续时直接按键退出即可，不会被当成
同意。

## How It Works

所有工具请求先过 `ApprovalPolicy.get(name)` 分级——auto 直接执行；
confirm 落到人工泳道，终端里 y/n 决定执行还是拒绝；deny 秒拒。三条路
的出口都汇到"结果或原因 → 模型"，而 `ApprovalLog` 在每一步记账。

**决策与执行解耦**：`ApprovalGate.check(name, args) ->
{"allowed": bool, "reason": str}` 是纯决策层：不执行、只判定、只记账。

Agent 循环拿到 allowed 后自己去执行，把拒绝原因作为 tool 消息（工具
结果回传给模型的消息类型）回传模型
（"Tool execution denied by user"）——模型会换个方式（比如先向用户
解释）。**审批层可以套在任何工具框架外面**：

```python
class ApprovalGate:
    def check(self, tool_name, args):
        level = self.policy.get(tool_name)                 # 未登记 -> 默认 confirm
        if level == "deny":
            self.log.record(tool_name, args, level, "forbidden", "Tool is forbidden by policy")
            return {"allowed": False, "reason": ...}
        if level == "auto":
            self.log.record(tool_name, args, level, "auto", "Auto-approved (safe tool)")
            return {"allowed": True, ...}
        approved = self._ask_user(tool_name, args)         # confirm: 暂停问人
        decision = "approved" if approved else "denied"
        self.log.record(tool_name, args, level, decision, ...)
        return {"allowed": approved, ...}
```

三条分支（deny/auto/confirm）每条都先 `log.record` 再返回——你在
`--demo` 输出末尾看到的审计日志，就是这三次 `record` 调用的产物。

**可测试的交互**：`--demo` 用 `mock_ask` 猴子补丁（monkey patch，运行时
替换对象方法的技巧）替换 `_ask_user`，把人工输入变成预置序列（y/y/n）
——同一个 Gate 逻辑，测试时可完全离线重放。**凡是依赖人的环节，都要
设计成可注入的。**

**fail-closed 是审批层的第一原则**：读不到人工输入（管道断开、无人
值守）时视为拒绝，绝不能把"问不到"当成"同意"。

## Pitfalls & Q&A

踩坑清单（现象 + 原因 + 解法）：

- **无人值守时程序崩溃或被误判为同意**。现象：管道关闭后 `_ask_user`
  抛 `KeyboardInterrupt/EOFError`。原因：没有捕获这两个异常。解法：
  捕获并一律视为拒绝（fail-closed）。
- **模拟工具被配成 auto**。现象：demo 里 `execute_command` 只回显不
  执行，被顺手配成 auto 档。原因：把演示实现的安全当成了真实工具的
  安全。解法：策略等级按真实工具的风险配，不按当前实现配。
- **审计日志泄露敏感参数**。现象：日志里出现密码、token 等完整参数。
  原因：`record` 直接落了全量 args。解法：只记 args 摘要并脱敏。
- **并发下批准被复用**。现象：A 会话的批准被 B 会话直接拿来执行。
  原因：审批记录没有会话维度。解法：多 Agent 并发时给审批加会话
  标识。

**Q1: HITL 审批层应该放在 Agent 架构的哪一层？**

工具执行之前、模型决策之后；实现方式见 How It Works 的"决策与执行
解耦"——纯决策组件，可套在任何工具框架外。

**Q2: 为什么未登记工具默认 confirm 而不是 auto？**

fail-safe 原则：新工具的风险未知时，多问一句的成本远低于误放行的代价。

**Q3: 无人值守场景下 confirm 怎么办？**

明确降级策略：要么 fail-closed（视为拒绝），要么预先配置自动批准范围
并记录；绝不能默认放行。
