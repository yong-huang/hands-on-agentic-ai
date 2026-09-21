"""mh.hooks — 生命周期钩子 (项目 08): pre 可阻断 + 反馈注入, post 可改写

Hook 是 harness 的通用插桩机制——07 权限门本质上是"pre-hook 的一个特例"
(项目 02 解剖图的判断)。本篇把它做成一等机制:
  pre-hook(tool_name, args) -> None 放行 | (True, feedback) 阻断并注入反馈
  post-hook(tool_name, result) -> result   改写结果(脱敏/净化/裁剪)

阻断的关键设计: 不是简单拒绝, 而是把 feedback 作为工具结果回喂模型 ——
模型知道"为什么被拦、该怎么改", 从对抗者变成守规者(07 真机验证的行为链)。
"""

from typing import Callable

PreHook = Callable[[str, dict], object]   # None | (True, feedback)
PostHook = Callable[[str, str], str]


class HookManager:
    def __init__(self):
        self._pre, self._post = [], []

    def add_pre(self, hook: PreHook):
        self._pre.append(hook)

    def add_post(self, hook: PostHook):
        self._post.append(hook)

    def run_pre(self, tool_name: str, args: dict) -> tuple:
        """依次执行 pre-hook, 任一阻断即返回 (True, feedback)。"""
        for hook in self._pre:
            r = hook(tool_name, args)
            if r is not None:
                blocked, feedback = r
                if blocked:
                    return True, feedback
        return False, None

    def run_post(self, tool_name: str, result: str) -> str:
        for hook in self._post:
            result = hook(tool_name, result)
        return result

    def wrap_tool(self, entry: dict) -> dict:
        """给工具表条目挂上 pre/post 钩子。"""
        origin = entry["fn"]

        def hooked(cwd=None, **args):
            blocked, feedback = self.run_pre(entry["fn"].__name__, args)
            if blocked:
                return f"[hook 拦截] {feedback}"
            return self.run_post(entry["fn"].__name__, origin(cwd=cwd, **args))

        hooked.__name__ = entry["fn"].__name__
        out = dict(entry)
        out["fn"] = hooked
        return out


# ---- 常用 hook 工厂 ----

def protect_file(pattern: str, feedback: str) -> PreHook:
    """pre-hook: 命令文本含 pattern 即阻断(如保护 .env)。"""
    def _hook(tool_name, args):
        cmd = args.get("command", "")
        if pattern in cmd and any(op in cmd for op in (">", ">>", "tee", "rm", "mv", "sed -i")):
            return True, feedback
        return None
    return _hook


def redact_secrets() -> PostHook:
    """post-hook: 结果文本里的疑似密钥脱敏(演示正则, 生产用检测器)。"""
    import re
    pats = [r"(sk-[A-Za-z0-9]{6,})", r"(ghp_[A-Za-z0-9]{6,})",
            r"(AKIA[A-Z0-9]{8,})", r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)"]
    rx = re.compile("|".join(pats))

    def _hook(tool_name, result):
        return rx.sub(lambda m: m.group(1)[:6] + "…[已脱敏]", result)
    return _hook
