"""mh.skills — Skills 按需注入 (项目 14): frontmatter 索引 · 触发加载 · 懒加载

Claude Code 的 Skills 模式: 启动时上下文里只有"菜单"(名称+描述+触发词,
几十 token), 命中需求时才通过 load_skill 工具加载正文(数千 token)——
渐进式披露, token 只为用到的知识付费。

  SkillBook(skills_dir)        # 扫描 */SKILL.md, 解析 YAML frontmatter
  book.index()                 # 菜单文本(注入 system)
  book.load(name)              # 正文全文(经 load_skill 工具懒加载)
  system_with_skills(base, book)
"""

from pathlib import Path

import yaml


class Skill:
    def __init__(self, name, desc, triggers, body):
        self.name, self.desc, self.triggers, self.body = name, desc, triggers, body


class SkillBook:
    def __init__(self, skills_dir):
        self.skills = {}
        for md in sorted(Path(skills_dir).glob("*/SKILL.md")):
            text = md.read_text()
            if not text.startswith("---"):
                continue
            fm_raw, body = text[3:].split("---", 1)
            fm = yaml.safe_load(fm_raw)
            self.skills[fm["name"]] = Skill(
                fm["name"], fm.get("description", ""),
                [t.strip() for t in str(fm.get("triggers", "")).split(",") if t.strip()],
                body.strip())

    def index(self) -> str:
        lines = [f"- {s.name}：{s.desc}（触发场景：{'/'.join(s.triggers)}）"
                 for s in self.skills.values()]
        return "\n".join(lines)

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        if not s:
            return f"[error] 未知 skill: {name}。可用: {', '.join(self.skills)}"
        return s.body


def skill_tools(book: SkillBook) -> dict:
    def load_skill(name: str) -> str:
        """加载指定 skill 的完整正文。只在确实需要该知识时调用。"""
        return book.load(name)
    schema = {"type": "function", "function": {
        "name": "load_skill",
        "description": "加载某个 skill 的完整操作规范。仅当当前任务命中该 skill 的触发场景时调用。",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string",
                                               "description": "skill 名称"}},
                       "required": ["name"]}}}
    return {"load_skill": {"desc": schema["function"]["description"],
                           "schema": schema, "fn": load_skill}}


def system_with_skills(base: str, book: SkillBook) -> str:
    return (f"{base}\n\n[可用 Skills 菜单 · 需要时用 load_skill 加载正文]\n"
            f"{book.index()}")
