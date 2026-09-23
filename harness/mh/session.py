"""mh.session — 会话持久化与崩溃恢复 (项目 11)

与 qa/31 的分界: 31 恢复的是"问答记录", 本模块恢复的是**带工具
副作用的 agent 会话**——消息历史之外还持久化"哪些命令已成功执行"的清单
(manifest), 恢复后这些命令**跳过重放**(文件 mtime 不变即证据), agent 从
断点继续而非从头再来。

三个部件:
  SessionStore   : 每轮原子落盘(tmp+rename)完整 agent 状态
  record_chat_fn : 包一层 chat_fn, 每次调用后快照
  skip_redo_tools: 给工具表套"已执行命令跳过重放"包装
恢复事件写入 store(11 的审计线)。
"""

import json
import os
import time
from pathlib import Path


class SessionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"messages": [], "done_commands": [], "recoveries": []}
        self.load()

    def load(self):
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text()))
            self.data["recoveries"].append(
                {"at": time.strftime("%H:%M:%S"),
                 "turns_restored": len(self.data.get("messages", [])),
                 "commands_restored": len(self.data.get("done_commands", []))})

    def resume_messages(self) -> list:
        """恢复用历史: 裁掉悬空尾部 —— 崩溃可能正好卡在
        assistant(带 tool_calls)与 tool 结果之间, 悬空调用会让模型协议错乱
        (11 实测: 输出全空)。带 tool_calls 的尾部 assistant 一律丢弃,
        其副作用是否已执行以 manifest(done_commands)为准。"""
        msgs = list(self.data.get("messages", []))
        while msgs and msgs[-1]["role"] == "assistant" \
                and msgs[-1].get("tool_calls"):
            msgs.pop()
        return msgs

    def save(self, messages, tool_trace=()):
        """原子落盘: 写临时文件再 rename, kill -9 打不断一致性。"""
        self.data["messages"] = messages
        self.data["tool_trace"] = list(tool_trace)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1))
        os.replace(tmp, self.path)

    def mark_done(self, command: str):
        if command not in self.data["done_commands"]:
            self.data["done_commands"].append(command)

    def flush(self):
        """只落盘当前 data(不清场)——副作用清单即时持久化用。"""
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1))
        os.replace(tmp, self.path)

    @property
    def done_commands(self):
        return self.data["done_commands"]


def record_chat_fn(chat_fn, store: SessionStore):
    """每次 LLM 调用后快照完整状态。"""
    def _chat(messages, tools=None, **kw):
        out = chat_fn(messages, tools=tools, **kw)
        store.save(messages, kw.get("tool_trace", ()))
        return out
    return _chat


def snapshotting_tools(tools: dict, store: SessionStore) -> dict:
    """工具表包装: 成功执行的命令记入 manifest(供恢复后跳过重放)。"""
    def make_wrapped(origin, store_ref):
        def wrapped(cwd=None, **args):
            result = origin(cwd=cwd, **args)
            if str(result).startswith("[ok]"):
                store_ref.mark_done(args.get("command", str(args)))
                store_ref.flush()  # 副作用清单即时落盘, 不动消息历史
            return result
        return wrapped

    out = {}
    for name, entry in tools.items():
        e = dict(entry)
        e["fn"] = make_wrapped(entry["fn"], store)
        e["fn"].__name__ = name
        out[name] = e
    return out


def skip_redo_tools(tools: dict, store: SessionStore) -> dict:
    """恢复态工具表包装: manifest 里的命令不再执行, 返回跳过说明。"""
    def make_resuming(origin, store_ref):
        def resuming(cwd=None, **args):
            cmd = args.get("command", "")
            if cmd in store_ref.done_commands:
                return "[ok] [已恢复·跳过重放] 该副作用在崩溃前已完成"
            return origin(cwd=cwd, **args)
        return resuming

    out = {}
    for name, entry in tools.items():
        e = dict(entry)
        e["fn"] = make_resuming(entry["fn"], store)
        e["fn"].__name__ = name
        out[name] = e
    return out
