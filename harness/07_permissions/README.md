# 07 · 权限门：allow / ask / deny 三档 + HITL + 审计

> 沙箱（06）限制了"执行付多大代价"；权限门决定"执不执行"。`mh/permissions.py`
> 上线：YAML 规则 + fnmatch 首条命中，allow 直通、ask 挂起等人工（HITL
> interrupt）、deny 自动拒绝并把原因回喂模型，**每次判定写 audit.log**。
> 真机一幕值得反复看：rm 被拦后模型改试 `unlink` → 也被拦 → 最后**如实汇报
> "删除被策略禁止"**——拒绝原因回喂让模型从对抗者变成守规者。

## 1. 为什么需要它

Winder.AI 的判断："沙箱、权限、花费上限、审计 trails 编码的是**组织政策**，
模型升级不会废除它们"——这是 harness 里最接近护城河的部分。Salesforce 的
权限五步流程（拦截→验证→执行→净化→反馈）本篇实现前两步与最后一步。
HITL 不是降级方案而是合规要求：AI 起草邮件，人类点"发送"。

## 2. 总览：核心机制一图看懂

![权限门三档判定](images/permissions.workflow.svg)

**怎么看这张图**：模型意图进入规则匹配（fnmatch、YAML 声明、首条命中），
从三个出口离开——良性直通、敏感操作挂起等人、危险命令拒绝；三个出口
**全部**汇入 audit.log。判定是纯确定性代码，与模型强弱无关。

心智模型一句话：**权限门是意图与副作用之间的一次确定性审判，且审判必须留痕。**

> 🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/harness/07_permissions/images/permissions.html)
> （或本地打开 [`images/permissions.html`](images/permissions.html)）。

## 3. 快速开始

```bash
cd harness/07_permissions
python3 demo.py                    # 三档确定性验收（无 LLM）
python3 demo.py --agent            # 真机: 诱导 rm 观察拦截与改道
python3 demo.py --interactive-ask  # ask 档真实终端问答
```

真机实测（2026-09-19，qwen3.8）：

```text
run_bash(echo "keep" > keep.txt)     → [ok]（白名单直通）
run_bash(rm tmp.txt)                 → [权限拒绝] 命中规则 rm*: 删除类命令默认禁止
run_bash(python3 -c "os.remove...")  → [权限拒绝] 命中规则 (default): 无规则命中
最终回答: keep.txt 已创建；tmp.txt 删除失败——当前权限策略禁止所有删除操作
audit.log: 10 条（时间戳·判定·命中规则·命令·备注）
```

## 4. 核心概念

### 4.1 三档语义与"首条命中"

规则按序匹配，首条命中生效——所以 **deny 必须排在泛化的 allow 之前**
（demo 里 `python3*` 的 deny 在 `echo*` 的 allow 之后但 `rm*` 在最前）。
无命中走 `default`，本实现安全默认为 **deny**：权限系统的第一原则。

### 4.2 黑名单可绕过：本篇最大的教训

第一版真机跑出惊悚画面：模型被 rm 拒后直接改用 `python3 -c "import os;
os.remove('tmp.txt')"`——**解释器是所有命令黑名单的旁路**。解法分两档：
本系列把 `python3*` 一并 deny（粗但有效）；生产要白名单 + 容器隔离
（nsjail/Docker），词法规则永远只是纵深防御的一层。audit.log 里那次
`os.remove` 尝试就是永久证据——**这就是审计存在的意义**。

### 4.3 HITL interrupt 的工程形态

`ask` 档的实现是一个可注入的 `ask_fn`：真终端是 `input(y/N)`，测试里是
脚本注入答案，未来是 Slack 审批卡片。**interrupt 是 harness 的一等公民**
（Salesforce 语），它的接口必须与载体解耦——`PermissionGate(ask_fn=...)`。

## 5. 代码关键点

```python
PermissionGate(rules_file=..., audit_path=..., ask_fn=..., default="deny")
gate.decide(command)          # → (ok, 可回喂文本)  永不抛异常
wrap_tool(entry, gate)        # 给工具表套权限门, 拦截在执行之前
```

默认规则（演示用）：`rm*` deny → `pip install*` ask → `ls*`/`echo*`/
`printf*`/`touch*`/`cat*`/`wc*` allow → 兜底 deny。

## 6. 文件结构

```
harness/
├── mh/
│   └── permissions.py   # ⛓️ 本篇: PermissionGate / wrap_tool
└── 07_permissions/
    ├── README.md
    ├── demo.py          # 三档验收 + 规则 YAML + --agent 真机
    └── images/          # 工作流图三件套
```

## 7. 深入要点

- **为什么 default=deny 而不是 allow？** 第一版 default=allow 的真机跑批
  显示模型 7 轮里试了 echo/printf/touch/python3/mv 五种改道，全靠兜底拒绝
  兜住；安全默认的下限是"事情做不成"，宽松默认的下限是"事情做错"。
- **fnmatch 够用吗？** 不够。`rm  file`（多空格）、base64 编码、`$(echo cm0p`
  都能骗过词法匹配。它是演示级纵深防御的一层，不是边界。
- **审计为什么连 allow 都记？** 合规要求"谁在何时放行了什么"；只记拒绝
  等于只记录事故不记录决策——事故复盘需要决策链。
- **权限门和沙箱的分工？** 沙箱限制"错了赔多少"，权限门决定"做不做"。
  两者都在意图与副作用之间（02 解剖图同一位置），是纵深防御的两层。

## 8. 总结

控制面第一块上板：三档判定 + HITL interrupt + 审计留痕，真机验证了
"拦截→回喂→改道→如实汇报"的完整闭环，也暴露并记录了黑名单旁路问题。
下一篇 [08_hooks](../08_hooks/README.md) 把"执行前后插桩"做成通用机制：
pre-hook 阻断 + 反馈注入、post-hook 结果脱敏——权限门只是它的第一个用户。
