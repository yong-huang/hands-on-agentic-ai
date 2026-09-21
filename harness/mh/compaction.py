"""mh.compaction — 上下文压缩 (项目 10): 阈值触发 · 模型自摘要 · 工具结果占位

context rot 的对策(02 解剖图的"续航面"):
  上下文估算 token 超阈值 → 把中段历史(保留任务头 + 最近 K 条)压缩为
  结构化摘要(由模型生成, 强制保留文件名/数字/路径), 中段工具结果替换为
  占位符; 压缩事件与摘要全文留档(暗桩存活检查的依据)。

compact_chat_fn(chat_fn, threshold, keep_recent) 产出可注入 loop 的 chat_fn ——
loop 依旧零改动: 直接对传入的 messages 列表做原地截断(messages[:] = ...)。
"""

import json


def est_tokens(messages) -> int:
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in messages) // 3


SUMMARY_PROMPT = (
    "你是 agent 对话历史的压缩器。把下面的对话历史压缩为不超过 250 字的"
    "结构化摘要, 分两节: [已完成的操作] 与 [关键事实]。必须原样保留所有"
    "文件名、目录路径和数字, 这是硬性要求。只输出摘要本身。/no_think")


def compact_chat_fn(chat_fn, threshold: int = 2500, keep_recent: int = 6):
    """产出带压缩能力的 chat_fn。compactor.events 记录每次压缩。"""
    events = []  # {"turn": n, "before": tok, "after": tok, "summary": str}
    state = {"calls": 0}

    def summarize(middle) -> str:
        dump = "\n".join(
            f"[{m.get('role')}] {str(m.get('content', ''))[:160]}"
            + (f" tool={m['tool_name']}" if m.get("tool_name") else "")
            for m in middle)
        out = chat_fn([{"role": "user", "content": f"{SUMMARY_PROMPT}\n\n{dump}"}],
                      tools=None)
        return out.get("content", "").strip()

    def _chat(messages, tools=None, **kw):
        state["calls"] += 1
        before = est_tokens(messages)
        if before <= threshold or len(messages) < keep_recent + 3:
            return chat_fn(messages, tools=tools, **kw)
        head, tail = messages[:2], messages[-keep_recent:]
        middle = messages[2:-keep_recent]
        summary = summarize(middle)
        compacted = head + [
            {"role": "user", "content":
                f"[历史摘要 · 此前 {len(middle)} 条消息已压缩]\n{summary}\n"
                f"(以上为压缩摘要, 请基于它继续当前任务)"}] + tail
        messages[:] = compacted  # 原地替换: loop 持有的历史同步瘦身
        events.append({"call": state["calls"], "before": before,
                       "after": est_tokens(messages), "summary": summary})
        return chat_fn(messages, tools=tools, **kw)
    _chat.events = events
    _chat.state = state
    return _chat
