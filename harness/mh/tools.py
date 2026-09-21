"""mh.tools — 工具契约层 (项目 05)

三件事:
  1. @tool 装饰器: 从类型注解 + docstring 自动生成 JSON Schema —— 工具即函数;
  2. jsonschema 参数校验: 缺参数/错类型在执行**前**拦截;
  3. 错误回传设计: 校验失败翻译成"哪里错、怎么改"(03 实验: 强模型顺任务域
     测不出契约价值, 契约的价值在故障域 —— 必须注入扰动才看得到)。

Registry.to_loop_tools() 产出与 mh.loop 兼容的工具表, loop 零侵入换装。
"""

import inspect
import jsonschema

_PY2JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _schema_from(fn, name, desc):
    sig = inspect.signature(fn)
    props, required = {}, []
    for pname, p in sig.parameters.items():
        if pname in ("cwd", "kwargs"):
            continue  # 运行时上下文, 不进 schema(模型不可见)
        props[pname] = {"type": _PY2JSON.get(p.annotation, "string")}
        if p.default is inspect.Parameter.empty:
            required.append(pname)
        else:
            props[pname]["description"] = f"默认 {p.default!r}"
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": required or props and required}}}


class Tool:
    """一个带契约的工具: 自动 schema + 执行前校验 + 错误翻译。"""

    def __init__(self, fn, name=None, desc=None, validate=True):
        self.fn = fn
        self.name = name or fn.__name__
        first = (fn.__doc__ or "").strip().splitlines()
        self.desc = desc or (first[0] if first else self.name)
        self.schema = _schema_from(fn, self.name, self.desc)
        self.validate = validate

    def validate_args(self, args):
        """返回 None 表示合法, 否则返回给模型的修正指引。"""
        try:
            jsonschema.validate(args or {}, self.schema["function"]["parameters"])
            return None
        except jsonschema.ValidationError as e:
            where = list(e.absolute_path) or ["(根对象)"]
            return (f"参数校验失败: 工具 {self.name} 的参数 {where} 不合法 —— {e.message}。"
                    f"必填参数: {self.schema['function']['parameters'].get('required', [])}。"
                    f"请修正后重新调用。")

    def call(self, args, cwd=None):
        """执行一次调用, 返回 (ok: bool, 文本结果)。永不抛异常。"""
        if self.validate and (msg := self.validate_args(args)):
            return False, msg
        sig = inspect.signature(self.fn)
        kwargs = {k: v for k, v in (args or {}).items() if k in sig.parameters}
        if "cwd" in sig.parameters and cwd:
            kwargs["cwd"] = cwd
        try:
            return True, str(self.fn(**kwargs))
        except Exception as e:  # noqa: BLE001 —— 错误也要成为模型的输入
            return False, (f"工具 {self.name} 执行失败: {type(e).__name__}: {e}。"
                           f"请修正后重试。")

    def as_loop_entry(self):
        """产出 mh.loop 工具表条目(错误以文本回传, 不抛异常)。

        cwd 必须是显式形参: loop 按 'cwd' in signature 注入任务目录,
        写成 **args 会让 cwd 静默丢失 —— 06 实验踩过, 沙箱隔离整条链路失效。
        """
        def _fn(cwd=None, **args):
            ok, out = self.call(args, cwd=cwd)
            return ("[ok] " if ok else "[error] ") + out
        _fn.__name__ = self.name
        return {"desc": self.desc, "schema": self.schema, "fn": _fn}


def tool(fn=None, *, name=None, desc=None, validate=True):
    """@tool 装饰器。类型注解生成 schema, docstring 首行作描述。"""
    def wrap(f):
        return Tool(f, name=name, desc=desc, validate=validate)
    return wrap(fn) if fn else wrap


class Registry:
    """工具注册表: loop 用的就是这个。"""

    def __init__(self):
        self._tools = {}

    def add(self, t: Tool):
        self._tools[t.name] = t
        return t

    def get(self, name) -> Tool:
        return self._tools[name]

    def to_loop_tools(self):
        return {n: t.as_loop_entry() for n, t in self._tools.items()}
