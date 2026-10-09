"""
02 · 消息体系、提示模板与结构化输出

三块内容：
  A. 消息体系与提示模板 — System/Human/AI 消息怎么排、MessagesPlaceholder
     怎么把 few-shot 示例注入模板（离线可验证）
  B. 坏输出重试 — JsonOutputParser 解析失败时，把错误回喂模型重试
     （离线：FakeListChatModel 先返回坏 JSON，再返回好 JSON）
  C. 真机结构化输出 — with_structured_output(Pydantic) 直接拿到校验过的对象

用法:
  python langchain/02_messages_structured/messages_structured.py
  python langchain/02_messages_structured/messages_structured.py --demo
"""

import os
import sys
from urllib.request import urlopen

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

MODEL = os.environ.get("LLM_MODEL", "qwen3.8:latest")
OLLAMA = "http://localhost:11434"

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def ollama_alive():
    try:
        with urlopen(f"{OLLAMA}/v1/models", timeout=3):
            return True
    except Exception:
        return False


def _text(msg):
    content = getattr(msg, "content", msg)
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)


# ============================================================
# 结构化抽取的目标模型
# ============================================================

class Person(BaseModel):
    """从文本中抽取的人物信息。"""

    name: str = Field(description="姓名")
    age: int = Field(description="年龄")
    city: str = Field(description="所在城市")


# ============================================================
# A. 消息体系与提示模板（离线）
# ============================================================

EXAMPLES = [
    HumanMessage("循环里查数据库是不是有问题？"),
    AIMessage("代码"),
    HumanMessage("1+1 等于几？"),
    AIMessage("数学"),
]


def build_triage_template():
    return ChatPromptTemplate.from_messages([
        ("system", "你是工单分诊员，把问题分类为 代码/数学/通用 之一，只输出分类词。"),
        MessagesPlaceholder("examples", optional=True),
        ("human", "{question}"),
    ])


def part_a_messages():
    section("[A] 消息体系与 MessagesPlaceholder（离线）")
    template = build_triage_template()

    plain = template.invoke({"question": "这段代码怎么优化？"}).to_messages()
    print("  不带示例的消息序列：")
    for m in plain:
        print(f"    {type(m).__name__:14s} {_text(m)[:40]}")
    ok_types = (
        isinstance(plain[0], SystemMessage)
        and isinstance(plain[-1], HumanMessage)
        and len(plain) == 2
    )
    check("无示例时 = [System, Human]", ok_types)

    with_shots = template.invoke(
        {"question": "这段代码怎么优化？", "examples": EXAMPLES}
    ).to_messages()
    print(f"  注入 2 组示例后共 {len(with_shots)} 条消息：")
    for m in with_shots:
        print(f"    {type(m).__name__:14s} {_text(m)[:40]}")
    ok_shots = (
        len(with_shots) == 2 + len(EXAMPLES)
        and isinstance(with_shots[1], HumanMessage)
        and isinstance(with_shots[2], AIMessage)
    )
    check("示例按 Human/AI 成对插入到占位符位置", ok_shots)


# ============================================================
# B. 坏输出重试（离线，真实解析器 + 假模型）
# ============================================================

class RetryExhausted(RuntimeError):
    def __init__(self, attempts, errors):
        super().__init__(f"{attempts} 次尝试均解析失败")
        self.attempts = attempts
        self.errors = errors


def invoke_with_retry(structured, messages, max_attempts=3, error_log=None):
    """调用结构化链；解析失败时把错误信息回喂模型重试。"""
    msgs = list(messages)
    errors = []
    for attempt in range(1, max_attempts + 1):
        try:
            return structured.invoke({"history": msgs}), attempt
        except OutputParserException as e:
            errors.append(e)
            if error_log is not None:
                error_log.append(e)
            msgs.append(HumanMessage(
                f"上次输出无法解析。请只输出符合要求的 JSON，不要包含其他文字。错误：{str(e)[:80]}"
            ))
    raise RetryExhausted(max_attempts, errors)


def build_parser_chain(llm):
    parser = PydanticOutputParser(pydantic_object=Person)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "从用户文本中抽取人物信息。\n{format_instructions}"),
        MessagesPlaceholder("history"),
    ]).partial(format_instructions=parser.get_format_instructions())
    return prompt | llm | RunnableLambda(lambda m: parser.parse(_text(m)))


def part_b_retry(demo_llm=None):
    section("[B] 坏输出重试：解析失败 → 错误回喂 → 再解析（离线）")
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    flaky = FakeListChatModel(responses=[
        "这不是 JSON，我只是随便聊聊。",
        '{"name": "张三", "age": 30, "city": "杭州"}',
    ])
    chain = build_parser_chain(flaky)
    messages = [HumanMessage("我叫张三，今年 30 岁，住在杭州。")]

    errors = []
    person, attempts = invoke_with_retry(chain, messages, error_log=errors)
    print(f"  第 1 次解析失败异常: {type(errors[0]).__name__ if errors else '无'}")
    print(f"  第 {attempts} 次得到: {person}")
    check("坏输出抛出 OutputParserException 并被捕获",
          bool(errors) and isinstance(errors[0], OutputParserException))
    check("回喂错误后第 2 次解析成功", attempts == 2 and person.name == "张三")

    always_bad = FakeListChatModel(responses=["仍然不是 JSON"])
    bad_chain = build_parser_chain(always_bad)
    try:
        invoke_with_retry(bad_chain, messages, max_attempts=3)
        check("连续坏输出 3 次后放弃", False, "未抛出 RetryExhausted")
    except RetryExhausted as e:
        check("连续坏输出 3 次后放弃", e.attempts == 3, f"attempts={e.attempts}")


# ============================================================
# C. 真机：with_structured_output 与 few-shot 风格对比
# ============================================================

STYLE_EXAMPLES = {
    "正式": [
        HumanMessage("这价格太贵了。"),
        AIMessage("该定价超出了我们的预算预期。"),
    ],
    "活泼": [
        HumanMessage("这价格太贵了。"),
        AIMessage("这价格确实有点吓人呀！"),
    ],
}


def build_style_chain(llm, examples):
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是文字编辑：模仿示例的风格改写用户句子，只输出改写结果。"),
        MessagesPlaceholder("examples"),
        ("human", "{text}"),
    ])
    return prompt | llm | StrOutputParser()


def part_c_real(llm):
    section("[C] 真机：结构化输出与 few-shot 风格")
    structured = ChatPromptTemplate.from_messages([
        ("system", "从用户文本中抽取人物信息。\n{format_instructions}"),
        MessagesPlaceholder("history"),
    ]).partial(
        format_instructions=PydanticOutputParser(pydantic_object=Person).get_format_instructions()
    ) | llm.with_structured_output(Person)

    person, attempts = invoke_with_retry(
        structured, [HumanMessage("我叫李雷，今年 28 岁，住在杭州。")]
    )
    print(f"  with_structured_output -> {person}（尝试 {attempts} 次）")
    check("真机返回严格 Pydantic 对象",
          isinstance(person, Person) and person.name == "李雷" and person.age == 28,
          f"name={person.name}, age={person.age}, city={person.city}")

    sentence = "这个方案不行。"
    out = {}
    for style, examples in STYLE_EXAMPLES.items():
        out[style] = build_style_chain(llm, examples).invoke(
            {"text": sentence, "examples": examples}
        ).strip()
        print(f"  {style}风格: {out[style]}")
    check("两种 few-shot 风格产出不同结果",
          bool(out["正式"]) and bool(out["活泼"]) and out["正式"] != out["活泼"])


def main():
    demo = "--demo" in sys.argv
    print("=" * 64)
    print("[02] 消息体系、提示模板与结构化输出")
    print(f"模式: {'离线演示（FakeListChatModel）' if demo else f'真机（{MODEL}）'}")
    print("=" * 64)

    part_a_messages()
    part_b_retry()

    if demo:
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        fake = FakeListChatModel(responses=[
            '{"name": "李雷", "age": 28, "city": "杭州"}',
            "（演示）该方案难以落地。",
            "（演示）这方案不太行哦！",
        ])
        section("[C] 演示：结构化输出与 few-shot 风格（假模型）")
        structured = build_parser_chain(fake)
        person, attempts = invoke_with_retry(
            structured, [HumanMessage("我叫李雷，今年 28 岁，住在杭州。")]
        )
        print(f"  parser chain -> {person}（尝试 {attempts} 次）")
        check("返回严格 Pydantic 对象", isinstance(person, Person) and person.age == 28)
        out = {}
        for style, examples in STYLE_EXAMPLES.items():
            out[style] = build_style_chain(fake, examples).invoke(
                {"text": "这个方案不行。", "examples": examples}
            ).strip()
            print(f"  {style}风格: {out[style]}")
        check("两种 few-shot 风格产出不同结果",
              bool(out["正式"]) and bool(out["活泼"]) and out["正式"] != out["活泼"])
    else:
        from langchain_ollama import ChatOllama

        if not ollama_alive():
            print("\n⏭️ Ollama 未启动，真机部分无法运行：先 `ollama serve`，"
                  "或加 `--demo` 看离线行为")
            return 2
        llm = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_predict=256)
        part_c_real(llm)

    passed = sum(1 for _, ok in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{'=' * 64}")
    print(f"验收: {passed}/{total} 通过" + (" ✅" if passed == total else " ❌"))
    print("=" * 64)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
