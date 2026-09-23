# 08 · Hook 系统：执行前阻断注入反馈，执行后脱敏改写

> `mh/hooks.py` 把"执行前后插桩"做成 harness 的通用机制：pre/post 两类
> 钩子，pre 可阻断并把反馈注入模型上下文，post 可改写结果（脱敏/净化/
> 裁剪）。真机一幕是最漂亮的防御样本：**模型从头到尾没见过真实密钥**——
> 写被 pre 拦、读被 post 脱敏，最后它"很遗憾，无法完成修改"，且说得出原因。

## What

Hook 是工具执行路径上的通用插桩点：pre-hook 在意图与副作用之间可阻断并
注入反馈，post-hook 在副作用与回喂之间可改写结果。`mh/hooks.py` 提供
`HookManager`，`wrap_tool` 与 07 同款接法，loop 依旧零改动。

心智模型一句话：**pre-hook 管"不做错事"，post-hook 管"不泄漏东西"。**

| 钩子 | 时机 | 能做什么 | 本篇示例 |
|:--|:--|:--|:--|
| pre | 意图 → 副作用之间 | 阻断 + 反馈注入 | `.env` 写保护 |
| post | 副作用 → 回喂之间 | 改写结果 | 密钥脱敏 |

## Why

权限门（07）只管"命令匹不匹配规则"；真实 harness 需要任意逻辑的插桩点：
`.env` 保护、结果脱敏、输出净化、行为审计埋点……Claude Code 源码拆解里
hooks 与 MCP/skills 并列高权限扩展入口——**hooks 是 harness 的 Event
Loop 之外第二根脊柱**。本篇把插桩点做成一等机制，07 的 `wrap_tool(gate)`
从今往后只是 `hooks.add_pre` 的语法糖。

## How

```bash
cd harness/08_hooks
python3 demo.py            # 确定性两场景（无 LLM）
python3 demo.py --agent    # 真机: 诱导模型改 .env
```

真机实测：

```text
run_bash(cat .env)          → API_KEY=sk-sec…[已脱敏]     ← post-hook 已脱敏
run_bash(echo ... > .env)   → [hook 拦截] 禁止修改 .env…  ← pre-hook 阻断+反馈
.env 全程字节级未变 ✅ | 反馈注入 ✅ | 模型如实汇报 ✅
最终回答: 很遗憾，无法完成修改。原因如下：1. 读取成功，但 API_KEY 的值
显示为 sk-sec…[已脱敏]……
```

真机惊喜是**零知识防御**：模型 `cat .env` 时看到的是 `sk-sec…[已脱敏]`——
**真实密钥从未进入模型上下文**。即使 pre-hook 被绕过，泄漏也不会发生
（它手里根本没有钥匙）。这就是"纵深防御"：同一资产的多条通路各设一道闸。

实现代码：

```python
hooks = HookManager()
hooks.add_pre(protect_file(".env", feedback="禁止修改 .env…"))   # 工厂
hooks.add_post(redact_secrets())                                  # 正则脱敏
hooks.wrap_tool(entry)                                            # 与 07 同款接法
```

`protect_file` 匹配"命令含 .env 且含写操作符（>/>>/tee/rm/mv/sed -i）"——
读放行、写拦截，`cat` 才能走到 post-hook 完成脱敏演示。

## Deep Dive

**阻断 ≠ 拒绝：反馈注入是行为引导。**07/08 两次真机验证了同一行为链：
**拦截 → 原因回喂 → 模型改道/如实汇报**。对比 03 的教训——错误信息质量
决定自纠质量——hook 的 feedback 就是"执行层的错误信息"。只返回 `False`
的 hook 会让模型陷入 09 预算要治理的空转。

踩坑清单：

- **post-hook 改写结果的风险**：结果失真会误导模型（比如脱敏截断破坏了
  JSON 结构）。本篇的脱敏只替换密钥 token、保留结构；生产里 post-hook 的
  改写要保证"对模型仍然可解析"。

## Q&A

**Q1: hooks 和 permissions 什么关系？**

权限门 = "规则驱动的 pre-hook + 审计"。本篇后 `wrap_tool` 家族已有三个
成员（tools/hook/gate），17 总装时按 guard-chain 顺序组合：契约校验 →
权限门 → hooks → 沙箱。

**Q2: hook 链的顺序语义？**

pre 依次执行、任一阻断即短路；post 依次管道。与 Claude Code hooks 的语义
一致（据转述），也与 Bash 的 hook 直觉一致。

**Q3: 为什么脱敏发生在回喂前而不是落盘后？**

落盘的 .env 本来就有真密钥（宿主自己写的）；要防的是**密钥进入模型
上下文**——上下文会被 10 压缩、12 记忆持久化，一旦进了就到处都是。
