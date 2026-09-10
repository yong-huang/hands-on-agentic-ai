path = '12_plan_execute/plan_execute.py'
src = open(path).read()
old = '''            tool = s["tool"]
            if tool == "verify_budget":'''
new = '''            tool = s["tool"]
            if tool in TOOLS:
                # 工具签名过滤: LLM 规划可能发明不存在的参数 (如 start_date)
                import inspect
                params = inspect.signature(TOOLS[tool]).parameters
                dropped = [k for k in s["args"] if k not in params]
                if dropped:
                    s["args"] = {k: v for k, v in s["args"].items()
                                 if k in params}
                    trace.append("    [{}] 丢弃规划器发明的参数 {} -> {}".format(
                        s["id"], dropped, s["args"]))
            if tool == "verify_budget":'''
assert old in src
src = src.replace(old, new)
open(path, 'w').write(src)
import ast
ast.parse(src)
print('patched + syntax ok')
