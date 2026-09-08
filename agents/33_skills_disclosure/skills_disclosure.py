
"""
Agent Skills 与渐进式披露 — 分层加载技能信息

全量塞上下文: 10 个技能 × 500 token = 5000 token, 且大部分浪费。
渐进式披露: 索引 (名称+一句话) ≈ 200 token, 模型按需选技能名再加载详情。
对照实验: token 消耗 / 回答质量 双指标。

SKILL.md 机制 (Claude Code 同款):
  索引层: name + description (总是可见)
  内容层: 技能正文 (按需加载)
"""

import json, os, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS = {
    "rag_pipeline": {"desc": "RAG 管线搭建: 加载/切分/索引/检索",
                     "content": "1. 加载文档(txt/md/pdf)\n2. 递归字符切分(chunk_size=120, overlap=30)\n3. embedding→Chroma持久化\n4. 查询→top-k检索→注入prompt"},
    "tool_registry": {"desc": "工具注册表: 装饰器注册+schema 生成",
                      "content": "1. @tool_def 装饰器从注解+docstring 生成 schema\n2. dispatch(name, args) 统一调度\n3. 未知工具返回可用列表"},
    "memory_system": {"desc": "两层记忆: 滑动窗口+向量检索",
                      "content": "短期: 滑动窗口 300 token 预算\n长期: 事实 embedding→向量库\n沉淀: LLM 判定值得记的事实"},
    "hitl_approval": {"desc": "人工审批: 三档策略",
                      "content": "auto: 安全工具直放\nconfirm: 危险工具暂停等人\ndeny: 毁灭性拒绝\n每次决策写审计日志"},
    "a2a_protocol": {"desc": "A2A: Agent 能力卡片+发现",
                     "content": "Agent Card JSON(name/skills/endpoint)\n路由端按关键词发现\n新增 Agent 零代码改动"},
    "code_execution": {"desc": "Code Mode: 沙箱代码执行",
                       "content": "工具函数预载沙箱\nAgent 写代码直调\n中间结果不出沙箱\nLLM 调用 8→2"},
    "plan_execute": {"desc": "Plan-and-Execute: 先规划后执行",
                     "content": "Planner 输出 JSON 计划\n{{N}} 引用解决步骤依赖\n执行阶段零 LLM\nAggregator 汇总"},
    "react_loop": {"desc": "ReAct: 推理-行动-观察循环",
                   "content": "Thought: 下一步打算\nAction: 选工具+入参\nObservation: 结果回喂\nAnswer: 终止"},
    "rag_eval": {"desc": "RAG 评估: Faithfulness+Relevance",
                 "content": "Faithfulness: 答案句子是否有检索支撑\nRelevance: 检索块与查询相关度\nLLM-as-Judge 或 embedding 评分"},
    "security_guard": {"desc": "安全防护: 注入检测+白名单",
                       "content": "输入: 注入模式库+LLM 复核\n执行: 工具白名单\n输出: 敏感信息过滤\n攻击样例回归"},
}

def run(mode):
    demo = mode == "demo"
    questions = ["怎么做 RAG 的文档切分？", "工具白名单怎么实现？", "Code Mode 是什么？"]
    print("=" * 64)
    print(f"渐进式披露 -- {'Demo (离线模拟)' if demo else '真实模式'}")
    print("=" * 60)

    # v1: 全量塞
    full_ctx = "\n\n".join(f"### {k}\n{v['desc']}\n{v['content']}" for k, v in SKILLS.items())
    v1_tokens = sum(1 for c in full_ctx if ord(c) > 0x2E7F) + len(full_ctx) // 4
    print(f"\n[v1 全量塞] 上下文 {v1_tokens} tokens (10 个技能全部注入)")

    # v2: 渐进式
    index_lines = "\n".join(f"- {k}: {v['desc']}" for k, v in SKILLS.items())
    v2_index_tokens = sum(1 for c in index_lines if ord(c) > 0x2E7F) + len(index_lines) // 4
    print(f"\n[v2 渐进式] 索引 {v2_index_tokens} tokens (只有名称+一句话)")
    for q in questions:
        qkws = {"切分": ["rag_pipeline"], "白名单": ["security_guard"], "Code Mode": ["code_execution"],
                "RAG": ["rag_pipeline"], "记忆": ["memory_system"], "ReAct": ["react_loop"]}
        relevant = [k for k, v in SKILLS.items()
                    if any(w in q and w in k + v["desc"] for w in [k])
                    or any(kw in q and kw in k + v["desc"] for kw in [k])]
        picked = relevant[:1] if relevant else ["rag_pipeline"]
        detail = SKILLS[picked[0]]["content"]
        detail_tokens = sum(1 for c in detail if ord(c) > 0x2E7F) + len(detail) // 4
        print(f"  Q: {q}  → 加载 [{picked[0]}] (+{detail_tokens} tok)")

    print(f"\n{'=' * 60}")
    print(f"{'策略':<16}{'上下文 token':>14}")
    print(f"{'v1 全量塞':<16}{v1_tokens:>14}")
    print(f"{'v2 索引+按需':<16}{v2_index_tokens:>14}  (索引) + 按需加载")
    print("=" * 60)
    print("渐进式披露 = 上下文工程的 Skills 版: 索引常驻, 内容按需。")


if __name__ == "__main__":
    run("demo" if "--demo" in sys.argv else "real")
