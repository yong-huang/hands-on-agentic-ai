"""mh.budget — 预算与止损 (项目 09): token 计量 · 轮次上限 · 优雅降级

07 真机见过: 权限拒绝后模型可以空转 7 轮。预算是它的硬性天花板。
设计(超限不抛异常):
  warn  : 预算将尽(max-1 轮), 注入系统提醒"请准备收尾";
  force : 预算耗尽(max 轮), 最后一轮撤走 tools(模型无法再调用工具),
          强制其输出 HANDOFF 摘要 —— 已完成/未完成/关键文件。
agent 收敛或止损, 都从同一扇门出去 —— 这就是"优雅降级"。

用法: budget_chat_fn(chat_fn, budget) 产出可注入 loop.run_agent 的 chat_fn。
token 计量用字符估算(中英混合 ~3 字符/token), 供预算判断; 精确计量
(Ollama eval_count)留待 16 评测台。
"""

import json


class Budget:
    def __init__(self, max_turns: int = None, max_tokens: int = None):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.turns_used = 0
        self.tokens_est = 0
        self.events = []  # (kind, turn) — kind: warn/force

    def est_tokens(self, messages) -> int:
        return sum(len(json.dumps(m, ensure_ascii=False)) for m in messages) // 3

    @property
    def exhausted(self) -> bool:
        if self.max_turns and self.turns_used >= self.max_turns:
            return True
        return bool(self.max_tokens and self.tokens_est >= self.max_tokens)

    @property
    def warn(self) -> bool:
        if self.max_turns and self.turns_used >= self.max_turns - 1:
            return True
        return bool(self.max_tokens and self.tokens_est >= self.max_tokens * 0.8)

    def snapshot(self) -> str:
        return (f"turns {self.turns_used}/{self.max_turns or '∞'}, "
                f"tokens ~{self.tokens_est}/{self.max_tokens or '∞'}")


def budget_chat_fn(chat_fn, budget: Budget):
    """包一层 chat_fn: 计量 → 提醒 → 强制收尾。"""

    def _chat(messages, tools=None, **kw):
        budget.turns_used += 1
        # 增量计量: 新进入的消息 + 上一轮回复
        delta = budget.est_tokens(messages[-1:]) if messages else 0
        budget.tokens_est += delta
        if budget.exhausted:
            # 强制收尾: 撤走 tools(模型无法再调用工具), 命令输出 HANDOFF
            budget.events.append(("force", budget.turns_used))
            finalize = messages + [{"role": "user", "content":
                "[系统·预算强制收尾] 预算已耗尽, 禁止再调用任何工具。"
                "现在立即输出 HANDOFF 摘要, 固定三行: "
                "已完成: … / 未完成: … / 关键文件: …。不要输出其他内容。"}]
            return chat_fn(finalize, tools=None, **kw)
        if budget.warn:
            budget.events.append(("warn", budget.turns_used))
            messages = messages + [{"role": "system", "content":
                "预算即将耗尽, 请尽快收敛; 不要开始新的子任务。"}]
        out = chat_fn(messages, tools=tools, **kw)
        budget.tokens_est += len(out.get("content", "")) // 3
        return out
    return _chat
