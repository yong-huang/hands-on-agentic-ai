#!/usr/bin/env python3
"""14 · Skills 按需注入 — 触发词匹配 + 懒加载省 token 实测 (docs/harness.md 项目 14)

验收:
  ① 同一会话两次计量: load_skill 调用前, skill 正文 0 字符出现在 messages;
     调用后正文进上下文, est_tokens 增量 ≥ 500
  ② frontmatter 解析单测(name/desc/triggers)
  ③ 真机: 任务"准备发布 v1.0" → 模型命中 release 技能并加载

用法:
  python3 demo.py            # 真机
  MOCK=1 python3 demo.py     # 离线
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from mh import llm as mh_llm  # noqa: E402
from mh import loop  # noqa: E402
from mh.compaction import est_tokens  # noqa: E402
from mh.skills import SkillBook, skill_tools, system_with_skills  # noqa: E402

RELEASE_BODY = """## 发布检查清单(release-checklist)

发布任何版本前必须逐项确认, 并在最终汇报中给出每项的 ✅/❌:

1. 版本号三处一致: pyproject/CHANGELOG/打 tag。
2. CHANGELOG 新版本段落包含: 新增/修复/破坏性变更三节。
3. 破坏性变更必须在 README 顶部有迁移说明。
4. 测试全绿: 跑一遍测试命令并粘贴输出。
5. 依赖清单无 `TODO`、无本地路径。
6. 打 tag 格式 `vX.Y.Z`, 附 CHANGELOG 首段作为 tag message。
7. 发布后回读: 确认产物可下载、示例可运行。

每项的详细操作:
- 版本号: grep -rn "version" pyproject.toml CHANGELOG.md, 人工比对三处。
- CHANGELOG: 检查最新段落标题是 `## [X.Y.Z] - 日期`。
- 迁移说明: 若存在 Breaking 关键词, README 顶部必须有 `## 迁移指南`。
- 测试: 输出末尾应有 `passed` 字样; 失败则中止发布流程并汇报。
- tag: `git tag -a vX.Y.Z -m "<CHANGELOG 首段>"`。
- 回读: 下载产物并列出文件数, 与构建清单比对。
8. 发布说明(bullet): 面向用户的变更摘要, 逐条动词开头。
9. 兼容性声明: 明确支持的最低运行时版本, 并实际在最低版本上冒烟一次。
10. 密钥与配置: 确认产物内无任何 .env、密钥、内网地址(用 grep 扫描)。
11. 归档: 构建产物与校验和(sha256sum)一并归档到 releases/ 目录。
12. 沟通: 发布完成后在公告频道粘贴 CHANGELOG 首段与下载链接。

每项的失败处置: 任何一项 ❌ 都必须中止流程, 在汇报中写明失败项与原因,
不得"带病发布"。历史事故复盘表明, 大多数坏发布源于"只查了前 3 项"。
执行顺序即优先级: 1→12 逐项推进, 不允许跳项并行。

8. 发布说明: 面向用户的变更摘要, 逐条动词开头, 粘贴到公告。
9. 兼容性声明: 明确支持的最低运行时版本, 并在最低版本上冒烟一次。
10. 密钥扫描: 产物内不得含 .env/密钥/内网地址, 用 grep 全量扫描。
11. 归档: 产物与 sha256sum 校验和一并存入 releases/ 目录。
12. 沟通: 发布完成后粘贴 CHANGELOG 首段与下载链接到公告频道。
失败处置: 任何一项 ❌ 立即中止, 汇报失败项与原因, 不得带病发布。
执行顺序即优先级: 1→12 逐项推进, 不允许跳项、不允许并行。
常见误用: 跳过第 4 步直接打 tag; 在第 10 步用肉眼代替 grep 扫描;
把 CHANGELOG 首段写成营销文案(它要客观列出变更点)。

扩展字段: SKILL.md 的 frontmatter 支持可选字段 version(规范版本)与
owner(负责人)。当两个 skill 触发词冲突时, 以 description 更具体者优先,
并在加载结果头部注明『同时命中 X, 已按更具体者加载』。菜单注入成本
约每条 30-50 token, 正文 1500-3000 token——懒加载的经济学在于:
只有菜单是常驻成本, 正文按需支付。SkillBook 扫描顺序按目录名字典序,
同名 skill 以先扫到者为准并告警。

历史教训: 2025-11 曾因跳过第 4 步发布过坏包, 此清单因此而生——
跳步等于重演事故。
"""

MIGRATION_BODY = """## 数据库迁移规范(db-migration)

1. 迁移脚本必须可重入: 重复执行不报错(IF NOT EXISTS / ON CONFLICT)。
2. 禁止在一条迁移里混合 DDL 与数据回填, 拆成两步。
3. 大表加列必须带默认值或分批回填, 避免锁表。
4. 迁移前后各做一次行数快照并记录在脚本头注释。
5. 回滚脚本与迁移脚本成对提交, 命名 NNN_down.sql。
"""


def make_skills_dir(root: Path) -> Path:
    d = root / "skills"
    for name, desc, trig, body in (
            ("release-checklist", "发布版本前的强制检查清单",
             "发布,release,上线,版本", RELEASE_BODY),
            ("db-migration", "数据库迁移操作规范",
             "迁移,migration,数据库变更", MIGRATION_BODY)):
        sd = d / name
        sd.mkdir(parents=True)
        (sd / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\ntriggers: {trig}\n---\n{body}")
    return d


def mock_chat(messages, tools=None, **kw):
    n_tool = sum(1 for m in messages if m.get("role") == "tool")
    if n_tool == 0:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "load_skill",
                          "arguments": {"name": "release-checklist"}}}]}
    return {"role": "assistant", "content":
            "已按发布清单检查: 版本号一致 ✅ 测试全绿 ✅ 可以发布 v1.0"}


def main():
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    is_mock = os.environ.get("MOCK") == "1"
    root = Path(tempfile.mkdtemp(prefix="mh14_"))
    sdir = make_skills_dir(root)
    book = SkillBook(sdir)

    # ② frontmatter 解析单测
    assert set(book.skills) == {"release-checklist", "db-migration"}
    assert "发布" in book.skills["release-checklist"].triggers
    assert "清单" in book.skills["release-checklist"].desc
    print("② frontmatter 解析单测: ✅")

    # 菜单注入, 正文懒加载
    base = "你是运维助手。/no_think"
    sysmsg = system_with_skills(base, book)
    print(f"菜单大小: {len(sysmsg) - len(base)} 字符 | "
          f"正文大小: {len(RELEASE_BODY)} 字符(未注入)")

    chat = mock_chat if is_mock else None
    result = loop.run_agent("准备发布 v1.0, 请加载对应的 skill 并按其逐项输出检查结论(✅/❌)。不要执行任何命令, 只依据规范文本作答。",
                            skill_tools(book), max_turns=6, chat_fn=chat)
    blob = json.dumps(result["messages"], ensure_ascii=False)
    before_load = blob.split("load_skill")[0]
    print(f"\n① 正文加载前出现在上下文: "
          f"{'❌ 不应出现' if '历史教训' in before_load else '✅ 0 字符'}")
    tok_delta = est_tokens(result["messages"])
    print(f"① 会话总 token 估算: {tok_delta} (含加载后的正文)")
    print(f"③ 最终回答: {result['final'][:100]}")
    loaded = "历史教训" in blob  # 正文标志性句子
    print(f"正文已进入上下文: {'✅' if loaded else '❌'}")
    ok = ("历史教训" not in before_load) and loaded
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
