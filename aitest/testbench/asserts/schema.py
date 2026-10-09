"""asserts.schema — 结构化输出断言 (docs/aitest.md 项目 4)

LLM 被要求输出 JSON 时, 实际会给你: 截断的、包着 ```json 围栏的、前后带客套话的、
类型随机的。本模块把"输出符合 schema"变成可编程断言:

    check(text, schema) -> AssertResult(ok, data, repairs)

三级处理管线:
  1. extract    从任意文本里抠出 JSON 对象(剥围栏/剥废话/括号配平)
  2. repair     规则修复(截断补全/尾逗号/单引号/类型强转/多余字段剔除)
  3. validate   手写 schema 校验器(type/required/enum/properties/items/additionalProperties)

规则修不好且给了 chat_fn 时, 走 LLM 修复重试一次(把校验错误喂回去重写);
selftest 用 10 条预置坏输出验证规则修复路径 ≥9/10(剩 1 条是 LLM 重试的活)。

零第三方依赖。校验器手写而非 jsonschema: 报错要带"字段路径+中文可读原因"
且修复管线需要逐字段尝试强转, jsonschema 的报错对象在这个场景反而碍事。
"""

import json
import re

RESULT_SCHEMA = {
    "type": "object",
    "required": ["answer", "confidence"],
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number"},
        "tool_used": {"type": "boolean"},
    },
    "additionalProperties": False,
}

FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


class AssertResult:
    def __init__(self, ok, data=None, repairs=None, error=None):
        self.ok = ok
        self.data = data
        self.repairs = repairs or []
        self.error = error

    def __repr__(self):
        tag = "PASS" if self.ok else "FAIL"
        return f"AssertResult({tag}, repairs={self.repairs}, error={self.error!r})"


# ============================================================
# 1. 提取: 从任意文本抠出第一个完整 JSON 对象
# ============================================================

def extract_json(text):
    """返回 (candidate, notes)。剥围栏 → 剥前后废话 → 括号配平截取。"""
    notes = []
    m = FENCE_RE.search(text)
    if m:
        text = m.group(1)
        notes.append("剥 ```json 围栏")
    start = text.find("{")
    if start == -1:
        return None, notes + ["未找到 JSON 起始 '{'"]
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                if i - start > 0 or text[start:i + 1].strip() != text.strip():
                    notes.append("剥前后废话")
                return text[start:i + 1], notes
    # 到结尾括号没配平 = 截断
    notes.append("检测到截断(括号未配平)")
    return text[start:], notes


# ============================================================
# 2. 规则修复: 逐条可解释, 修了什么记进 repairs
# ============================================================

def repair_rules(candidate):
    """对截取的 JSON 文本做规则修复, 返回 (text, repairs)。"""
    fixes = []

    def sub(pattern, repl, reason, flags=0):
        nonlocal candidate
        new = re.sub(pattern, repl, candidate, flags=flags)
        if new != candidate:
            candidate = new
            fixes.append(reason)

    if not candidate.rstrip().endswith("}"):
        body = candidate.rstrip().rstrip(",")
        if (body.count('"') - body.count('\\"')) % 2 == 1:
            body += '"'
            fixes.append("截断补全(补闭合引号)")
        opened = body.count("{") - body.count("}")
        if opened > 0:
            body += "}" * opened
            fixes.append(f"截断补全(补 {'}' * opened})")
        candidate = body
    sub(r",\s*([}\]])", r"\1", "去尾逗号")
    sub(r",\s*$", "", "去尾逗号")
    sub(r":\s*'([^']*)'", r': "\1"', "单引号值转双引号")
    sub(r"([{,]\s*)'([^']+)'(\s*:)", r'\1"\2"\3', "单引号键转双引号")
    if "\n" in candidate:
        candidate = re.sub(r"\n+", " ", candidate)
        fixes.append("字面换行替换为空格")
    return candidate, fixes


# ============================================================
# 3. 校验器 + 修复重试
# ============================================================

_TYPES = {"string": str, "number": (int, float), "integer": int,
          "boolean": bool, "object": dict, "array": list}


def validate(data, schema, path="$"):
    """手写校验器: 返回错误列表(空 = 通过)。"""
    errors = []
    t = schema.get("type")
    if t and not isinstance(data, _TYPES.get(t, type(None))) or \
       (t == "number" and isinstance(data, bool)) or \
       (t == "integer" and isinstance(data, bool)):
        errors.append(f"{path}: 期望 {t}, 实际 {type(data).__name__}")
        return errors
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: {data!r} 不在枚举 {schema['enum']}")
    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{path}: 缺必填字段 {key!r}")
        props = schema.get("properties", {})
        for key, val in data.items():
            if key in props:
                errors += validate(val, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: 多余字段 {key!r}(schema 未声明)")
    if isinstance(data, list) and "items" in schema:
        for i, item in enumerate(data):
            errors += validate(item, schema["items"], f"{path}[{i}]")
    return errors


def _coerce_types(data, schema):
    """按 schema 做保守类型强转: 数字字符串→数字 / 数字→字符串。返回 (data, fixes)。"""
    fixes = []
    if isinstance(data, dict) and schema.get("type") == "object":
        for key, rule in schema.get("properties", {}).items():
            if key not in data:
                continue
            val, want = data[key], rule.get("type")
            if want == "number" and isinstance(val, str):
                try:
                    data[key] = float(val)
                    fixes.append(f"强转 {key}: '数字字符串'→number")
                except ValueError:
                    pass
            elif want == "string" and isinstance(val, (int, float, bool)):
                data[key] = json.dumps(val) if isinstance(val, bool) else str(val)
                fixes.append(f"强转 {key}: {type(val).__name__}→string")
            elif want == "boolean" and isinstance(val, str) and val.lower() in ("true", "false"):
                data[key] = val.lower() == "true"
                fixes.append(f"强转 {key}: 'true/false'→boolean")
    return data, fixes


def _strip_unknown(data, schema):
    fixes = []
    if isinstance(data, dict) and schema.get("additionalProperties") is False:
        for key in list(data):
            if key not in schema.get("properties", {}):
                data.pop(key)
                fixes.append(f"剔除多余字段 {key!r}")
    return data, fixes


def check(text, schema=None, chat_fn=None):
    """结构化输出断言主入口。chat_fn 给定且规则修不好时做一次 LLM 修复重试。"""
    schema = schema or RESULT_SCHEMA
    candidate, notes = extract_json(text)
    if candidate is None:
        return AssertResult(False, error="无可提取的 JSON 对象", repairs=notes)

    repairs = list(notes)
    fixed, more = repair_rules(candidate)
    repairs += more
    try:
        data = json.loads(fixed)
    except json.JSONDecodeError as e:
        return AssertResult(False, error=f"JSON 解析失败: {e}", repairs=repairs)

    data, more = _coerce_types(data, schema)
    repairs += more
    data, more = _strip_unknown(data, schema)
    repairs += more

    errors = validate(data, schema)
    if not errors:
        return AssertResult(True, data=data, repairs=repairs)

    if chat_fn is None:
        return AssertResult(False, error="; ".join(errors), repairs=repairs)

    # LLM 修复重试: 把错误清单喂回去重写一次
    prompt = (f"以下内容应是符合 schema 的 JSON 但有问题: {errors}。"
              f"原文: {text}\n只输出修复后的 JSON, 不要解释。")
    try:
        retry = chat_fn([{"role": "user", "content": prompt}])
    except Exception as e:  # noqa: BLE001 —— 修复失败也算断言失败
        return AssertResult(False, error=f"{errors}; LLM 修复重试异常: {e}",
                            repairs=repairs + ["LLM 修复重试"])
    retry_candidate, _ = extract_json(retry)
    try:
        data2 = json.loads(repair_rules(retry_candidate)[0])
    except (json.JSONDecodeError, TypeError):
        return AssertResult(False, error="; ".join(errors),
                            repairs=repairs + ["LLM 修复重试仍不可解析"])
    errors2 = validate(data2, schema)
    if errors2:
        return AssertResult(False, error="; ".join(errors2),
                            repairs=repairs + ["LLM 修复重试未通过校验"])
    return AssertResult(True, data=data2, repairs=repairs + ["LLM 修复重试"])


# ============================================================
# selftest: 10 条预置坏输出, 规则修复 ≥9/10
# ============================================================

BAD_CASES = [
    ('```json\n{"answer": "git commit 用于提交变更", "confidence": 0.9}\n```', "围栏包裹"),
    ('好的, 结果如下: {"answer": "HTTP 80 是网页服务", "confidence": 0.8} 希望有帮助!', "前后废话"),
    ('{"answer": "提交后回退", "confidence": 0.9,}', "尾逗号"),
    (": {'answer': '环境变量是运行期配置', 'confidence': 0.7}", "单引号"),
    ('{"answer": "Git 提交', "值内截断"),
    ('{"answer": "rwx 是读写执行", "confidence": 0.9', "对象截断"),
    ('{"answer": "多行\n回答", "confidence": 0.5}', "字面换行"),
    ('{"answer": "端口 22", "confidence": "0.95"}', "类型错: 数字写成字符串"),
    ('{"answer": 42, "confidence": 0.9}', "类型错: 答案写成数字"),
    ('{"answer": "ls 列目录", "confidence": 0.9, "mood": "happy"}', "多余字段+缺 boolean 可选"),
]


def selftest():
    """规则修复路径验收: ≥9/10 过 RESULT_SCHEMA。最后一条用来演示 LLM 重试路径。"""
    passed = 0
    print(f"selftest: {len(BAD_CASES)} 条坏输出, 走规则修复(无 LLM)")
    for i, (bad, label) in enumerate(BAD_CASES, 1):
        r = check(bad)
        mark = "✅" if r.ok else "❌"
        passed += r.ok
        detail = f"修复={r.repairs}" if r.ok else f"error={r.error}"
        print(f"  [{i:02d}] {mark} {label}: {detail}")
    print(f"规则修复: {passed}/{len(BAD_CASES)} (验收口径 ≥9)")
    # 第 7 条(缺 confidence 的场景未预置)与 LLM 重试路径在 demo 里真机演示
    return passed >= 9


if __name__ == "__main__":
    import sys
    sys.exit(0 if selftest() else 1)
