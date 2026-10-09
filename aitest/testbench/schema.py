"""schema — 统一结果模型 (docs/aitest.md 项目 18)

results.json 的唯一契约: 每次运行 = meta + 七个模块结果。
模块字段固定: name/status/passed/metrics/elapsed_s/detail。
status: ok(跑完) / error(模块崩溃, 被 runner 兜住) / skipped(前置不满足)
passed: 机制类模块的布尔结论; 阈值类模块为 null(交给 20 线门禁判)。
"""

RESULT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["meta", "modules"],
    "additionalProperties": False,
    "properties": {
        "meta": {
            "type": "object",
            "required": ["sut", "level", "generated_at", "elapsed_s"],
            "additionalProperties": True,
            "properties": {
                "sut": {"type": "string"},
                "level": {"enum": ["smoke", "full"]},
                "generated_at": {"type": "string"},
                "elapsed_s": {"type": "number"},
                "model": {"type": ["string", "null"]},
            },
        },
        "modules": {
            "type": "array",
            "minItems": 7,
            "items": {
                "type": "object",
                "required": ["name", "status", "passed", "metrics",
                             "elapsed_s", "detail"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "status": {"enum": ["ok", "error", "skipped"]},
                    "passed": {"type": ["boolean", "null"]},
                    "metrics": {"type": "object"},
                    "elapsed_s": {"type": "number"},
                    "detail": {"type": "string"},
                },
            },
        },
    },
}


def validate(report):
    """过 jsonschema; 不合法直接抛 ValidationError。返回 True。"""
    import jsonschema
    jsonschema.validate(report, RESULT_SCHEMA)
    return True
