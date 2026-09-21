"""mh.memory — 跨会话记忆 (项目 12): MEMORY.md 沉淀 · 新会话注入 · 遗忘入口

与 11 session 的分界: session 恢复"本任务的进度"(checkpoint), memory 沉淀
"跨任务的世界观"(偏好/事实)。三件套:
  remember(fact)      : 带时间戳追加一条
  recall()            : 注入新会话 system 的记忆块(空则返回 "")
  forget(keyword)     : 删除含关键词的条目(遗忘与记住同样是一等操作)
  consolidate(chat_fn): 会话收尾时让模型判断"值得跨会话记住什么"——
                        模型输出不可全信, 所以每条带时间戳可追溯可删除。
存储就是人类可读的 MEMORY.md —— 12 记忆污染的解药之一是"看得见、可手改"。
"""

import time
from pathlib import Path


class Memory:
    def __init__(self, path):
        self.path = Path(path)
        self.lines = []
        if self.path.exists():
            self.lines = [l.rstrip("\n") for l in self.path.read_text().splitlines()
                          if l.strip()]

    def remember(self, fact: str):
        self.lines.append(f"- {time.strftime('%Y-%m-%d %H:%M')} | {fact.strip()}")
        self.flush()

    def forget(self, keyword: str) -> int:
        keep = [l for l in self.lines if keyword not in l]
        removed = len(self.lines) - len(keep)
        self.lines = keep
        self.flush()
        return removed

    def recall(self) -> str:
        return "\n".join(self.lines)

    def flush(self):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text("\n".join(self.lines) + ("\n" if self.lines else ""))


def consolidate(chat_fn, transcript, memory: Memory, max_items: int = 3) -> list:
    """会话收尾: 让模型从对话提取值得跨会话记住的事实/偏好(≤max_items 条)。"""
    dump = "\n".join(f"[{m.get('role')}] {str(m.get('content', ''))[:150]}"
                     for m in transcript if m.get("role") in ("user", "assistant"))
    out = chat_fn([{"role": "user", "content":
                    "从下面的对话里提取值得跨会话长期记住的用户偏好或项目事实, "
                    f"最多 {max_items} 条, 每条一行、以 '- ' 开头; "
                    "没有就只输出一行: (无)\n\n" + dump + "\n/no_think"}],
                  tools=None, num_predict=400)
    added = []
    for line in out.get("content", "").splitlines():
        line = line.strip()
        if line.startswith("- ") and "(无)" not in line:
            memory.remember(line[2:])
            added.append(line[2:])
    return added


def system_with_memory(base_system: str, memory: Memory) -> str:
    """把记忆块拼进 system 提示词(空记忆则原样返回)。"""
    block = memory.recall()
    if not block:
        return base_system
    return (f"{base_system}\n\n[长期记忆 · 用户偏好与项目事实, 必须遵守]\n{block}")
