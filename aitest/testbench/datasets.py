"""datasets.py — 评测集构建与版本化 (docs/aitest.md 项目 2)

golden set(固定标注的基准用例集)是 AI 回归测试的"标准卷": 集合不动,
被测对象或提示词怎么改, 都能逐用例回答"变好了还是变坏了"。

本模块三件事(全部零第三方依赖, pyyaml 除外):
  load(name)                 加载 aitest/datasets/<name>.yaml
  validate                   schema 校验: python3 -m testbench.datasets validate [name]
  diff                       版本对比:   python3 -m testbench.datasets diff v1 v2

用例 schema(golden_v1 起, 项目 8 run_eval 按此消费):
  id             必填, ^[a-z]+_[0-9]{3}$, 全集唯一 —— 前缀即类别缩写
  category       必填, fact | tool | injection | chitchat 四类之一
  query          必填, 发给 SUT 的任务文本
  expected_points 必填, ≥1 条期望要点 —— 项目 8 各类断言的判分原料
  tags           可选, 辅助筛选(smoke/e2e/...), 不参与校验语义

为什么手写校验器不用 jsonschema: id 唯一性、类别枚举、要点非空这些规则
需要中文定位报错("第 7 条用例缺期望要点"), 且要一次报出全部错误而不是
遇错即停 —— 手写 40 行换来可读报错, 值。
"""

import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(os.path.dirname(HERE), "datasets")

CATEGORIES = ("fact", "tool", "injection", "chitchat")
ID_PATTERN = re.compile(r"^[a-z]+_[0-9]{3}$")


def dataset_path(name):
    """golden_v1 -> aitest/datasets/golden_v1.yaml"""
    if not name.endswith(".yaml"):
        name = f"{name}.yaml"
    return os.path.join(DATASETS_DIR, name)


def load(name):
    """加载评测集, 返回 dict。文件不存在或 YAML 语法错抛异常。"""
    path = dataset_path(name)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层必须是映射, 实际 {type(data).__name__}")
    return data


def validate_dataset(data, name=""):
    """返回全部错误列表(空列表 = 通过)。一次报全, 不遇错即停。"""
    errors = []
    cases = data.get("cases")

    if data.get("schema_version") != 1:
        errors.append(f"schema_version 必须是 1, 实际 {data.get('schema_version')!r}")
    if not isinstance(cases, list) or not cases:
        errors.append("cases 必须是非空列表")
        return errors

    seen_ids = set()
    for i, case in enumerate(cases, 1):
        where = f"第 {i} 条"
        if not isinstance(case, dict):
            errors.append(f"{where} 不是映射")
            continue
        cid = case.get("id", "(缺 id)")
        where = f"第 {i} 条({cid})"

        if "id" not in case:
            errors.append(f"{where} 缺 id")
        elif not ID_PATTERN.match(case["id"]):
            errors.append(f"{where} 的 id 不符合 ^[a-z]+_[0-9]{{3}}$: {case['id']!r}")
        elif case["id"] in seen_ids:
            errors.append(f"{where} 的 id 重复: {case['id']}")
        else:
            seen_ids.add(case["id"])

        if case.get("category") not in CATEGORIES:
            errors.append(f"{where} 的 category 必须是 {'/'.join(CATEGORIES)} 之一, "
                          f"实际 {case.get('category')!r}")

        query = case.get("query")
        if not isinstance(query, str) or not query.strip():
            errors.append(f"{where} 缺 query 或为空白")

        points = case.get("expected_points")
        if not isinstance(points, list) or len(points) == 0:
            errors.append(f"{where} 缺 expected_points 或为空列表")
        else:
            for j, p in enumerate(points, 1):
                if not isinstance(p, str) or not p.strip():
                    errors.append(f"{where} 的第 {j} 条期望要点为空")

        tags = case.get("tags", [])
        if not isinstance(tags, list):
            errors.append(f"{where} 的 tags 必须是列表")
    return errors


def diff_datasets(base, cand):
    """按 id 做集合运算 + 字段级变更检测。

    返回 {"added": [id], "removed": [id],
          "changed": [(id, [变更字段])]}
    changed 的字段范围: category / query / expected_points / tags。
    """
    bc = {c["id"]: c for c in base.get("cases", []) if isinstance(c, dict)}
    cc = {c["id"]: c for c in cand.get("cases", []) if isinstance(c, dict)}
    added = sorted(set(cc) - set(bc))
    removed = sorted(set(bc) - set(cc))
    changed = []
    for cid in sorted(set(bc) & set(cc)):
        fields = [f for f in ("category", "query", "expected_points", "tags")
                  if bc[cid].get(f) != cc[cid].get(f)]
        if fields:
            changed.append((cid, fields))
    return {"added": added, "removed": removed, "changed": changed}


# ============================================================
# 命令行入口
# ============================================================

def cmd_validate(name="golden_v1"):
    data = load(name)
    errors = validate_dataset(data, name)
    if errors:
        print(f"FAIL {name}: {len(errors)} 个问题")
        for e in errors:
            print(f"  - {e}")
        return 1
    cases = data["cases"]
    by_cat = {}
    for c in cases:
        by_cat[c.get("category", "?")] = by_cat.get(c.get("category", "?"), 0) + 1
    stat = " ".join(f"{k}={v}" for k, v in sorted(by_cat.items()))
    print(f"PASS {name}: {len(cases)} 条用例 ({stat})")
    return 0


def cmd_diff(base, cand):
    d = diff_datasets(load(base), load(cand))
    n_add, n_del, n_chg = len(d["added"]), len(d["removed"]), len(d["changed"])
    print(f"diff {base} -> {cand}: +{n_add} 增 / -{n_del} 删 / ~{n_chg} 改 "
          f"(共 {n_add + n_del + n_chg} 处)")
    for cid in d["added"]:
        print(f"  + {cid}")
    for cid in d["removed"]:
        print(f"  - {cid}")
    for cid, fields in d["changed"]:
        print(f"  ~ {cid}: 字段变更 {'/'.join(fields)}")
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python3 -m testbench.datasets validate [name] | diff <base> <cand>",
              file=sys.stderr)
        return 2
    if argv[0] == "validate":
        return cmd_validate(argv[1] if len(argv) > 1 else "golden_v1")
    if argv[0] == "diff" and len(argv) == 3:
        return cmd_diff(argv[1], argv[2])
    print("用法: python3 -m testbench.datasets validate [name] | diff <base> <cand>",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
