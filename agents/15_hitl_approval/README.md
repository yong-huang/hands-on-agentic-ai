# 15 · HITL 审批：分级授权与人工确认

> 工具越来越强，胆子也越来越大：删文件、发邮件、执行 shell…… Agent 的能力
> 边界不能只靠 prompt 里一句"请小心"。本篇实现完整的 HITL（Human-in-the-loop）
> 审批层：auto/confirm/deny 三档策略、终端人工确认、全程审计日志——模型
> 的每次工具请求都要先过这道门。

## 1. 为什么需要它

白名单（项目 12）只能回答"允许/不允许"二元问题，现实要细腻得多：`calculator`
随便跑，`delete_file` 得问一下人，`format_disk` 想都别想。更关键的是**审批
要留痕**——出了事故能回答"谁批准的、什么时候、参数是什么"。本篇的
`ApprovalPolicy + ApprovalGate + ApprovalLog` 三件套是 Agent 安全层
（项目 29 的前奏）的最小完整实现，且与工具框架完全解耦。

## 2. 总览：核心机制一图看懂

![HITL 审批门工作流](images/approval_gate.workflow.svg)

**怎么看这张图**：所有工具请求先过 `ApprovalPolicy.get(name)` 分级——auto
直接执行；confirm 落到人工泳道，终端里 y/n 决定执行还是拒绝；deny 秒拒。
三条路的出口都汇到"结果或原因 → 模型"，而 `ApprovalLog` 在每一步默默记账。

心智模型一句话：**策略定档位、人工把关键、日志记全程——模型说了不算。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/15_hitl_approval/images/approval_gate.workflow.html)（或本地打开 [`images/approval_gate.workflow.html`](images/approval_gate.workflow.html)）。

## 3. 快速开始

```bash
cd agents/15_hitl_approval
python hitl_approval.py --demo          # 模拟模式：预置 y/y/n 决策序列
python hitl_approval.py --interactive   # 交互模式：真实在终端等你按 y/n（推荐！）
```

`--demo` 依次演示：打印策略表 → auto-approve 模式批演 6 条调用（`rm -rf /`
这类模拟命令被批准、`delete_file important.db` 被"用户"拒绝、`format_disk`
被策略禁止）→ 打印审计日志与 `summary()` 计数。

`--interactive` 用同样的 6 条调用，但 confirm 级工具会真的暂停：
`Approve? [y/n]:`——**亲手拒绝一次 Agent，比读十篇安全文章有用**。
Ctrl+C/Ctrl+D 视为拒绝（fail-closed）。

## 4. 核心概念

### 4.1 三档策略 + 默认安全

| 档位 | 语义 | 本篇示例 |
| :--- | :--- | :--- |
| auto | 放心工具，立即执行 | calculator / get_weather / search |
| confirm | 危险工具，暂停问人 | delete_file / send_email / execute_command |
| deny | 毁灭性工具，无条件拒绝 | format_disk / rm_rf / drop_database |

**未登记的工具默认 confirm**（fail-safe）：新工具上线时宁可多问一句，不可
静默放行。这比黑白名单的二元模型细一档。

### 4.2 决策与执行解耦

`ApprovalGate.check(name, args) -> {"allowed": bool, "reason": str}` 是纯
决策层：不执行、只判定、只记账。Agent 循环拿到 allowed 后自己去执行，
把拒绝原因作为 tool 消息回传模型（"Tool execution denied by user"）——
模型会换个方式（比如先向用户解释）。**审批层可以套在任何工具框架外面。**

### 4.3 审计日志：每一次决策都留痕

```python
{"time": "2026-09-02T15:30:45", "tool": "delete_file",
 "args": {"filepath": "important.db"}, "policy": "confirm",
 "decision": "denied", "detail": "User denied"}
```

decision 取值 `auto / approved / denied / forbidden`，`summary()` 输出分类
计数。合规审查、事故回放、策略调优全靠它。**易错点**：日志要记 args 摘要
（注意脱敏），不记完整敏感参数。

### 4.4 可测试的交互

`--demo` 用 `mock_ask` 猴子补丁替换 `_ask_user`，把人工输入变成预置序列
（y/y/n）——同一个 Gate 逻辑，测试时可完全离线重放。**凡是依赖人的环节，
都要设计成可注入的。**

## 5. 代码关键部分

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

坑清单：

- `_ask_user` 必须捕获 `KeyboardInterrupt/EOFError` 并视为拒绝（fail-closed），
  管道/无人值守环境下不能把"读不到输入"当成"同意"；
- `execute_command` 这类模拟工具只回显不执行，但策略等级要按真实工具配；
- 审批在多 Agent 并发时要加会话维度，避免 A 的批准被 B 复用。

## 6. 文件结构

```
15_hitl_approval/
├── README.md                          # 本篇教程
├── hitl_approval.py                   # 主脚本（约 340 行）：Policy + Gate + Log + 双模式
└── images/
    ├── approval_gate.workflow.json    # 图源：workflow 类型（审批门三岔口）
    ├── approval_gate.workflow.html    # 交互版架构图
    └── approval_gate.workflow.svg     # 双主题矢量图
```

## 7. 面试要点

- **Q: HITL 审批层应该放在 Agent 架构的哪一层？**
  A: 工具执行之前、模型决策之后——以纯决策组件（check 返回 allowed/reason）
  解耦实现，可套在任何工具框架外。
- **Q: 为什么未登记工具默认 confirm 而不是 auto？**
  A: fail-safe 原则：新工具的风险未知时，多问一句的成本远低于误放行的代价。
- **Q: 用户拒绝后模型收到什么？**
  A: 一条说明被拒的 tool 消息（"denied by user"），模型可调整策略（解释、
  换方案），而不是整个循环崩溃。
- **Q: 审批日志要记什么？**
  A: 时间、工具、参数摘要（脱敏）、策略档位、决策结果——支撑合规审计与
  事故回放。
- **Q: 无人值守场景下 confirm 怎么办？**
  A: 明确降级策略：要么 fail-closed（视为拒绝），要么预先配置自动批准范围
  并记录；绝不能默认放行。

## 8. 总结

分级策略、人工确认、审计留痕——三件套让 Agent 的能力边界第一次变得
"可配置、可监督、可追责"。至此第三阶段（工具系统）收官：Function Calling、
Registry、MCP、错误处理、安全审批齐备。下一篇进入第四阶段：让 Agent 拥有
跨会话的记忆与上下文工程。
