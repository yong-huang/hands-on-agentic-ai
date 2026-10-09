"""asserts.factuality — 幻觉检测器 (docs/aitest.md 项目 6)

语义断言(项目 5)只能回答"说得像不像标准答案", 回答不了"说得对不对"。
幻觉检测把回答拆成原子 claims(原子句), 逐条对照 source 段落三级核验:

    1. 子串包含   归一化后与 source 的最长公共片段 ≥6 字 -> supported
    2. 数值核对   claim 里的数字全部不在 source -> unsupported(硬信号);
                  部分在 -> 降级到第三级
    3. LLM judge  chat_fn 兜底判定 SUPPORTED/UNSUPPORTED; 未提供 -> unknown

    check(answer, source, chat_fn) -> FactualityResult

selftest: 5 段 source × 20 条预置回答(10 幻觉 + 10 忠实), 输出混淆矩阵,
验收口径 幻觉检出 ≥9/10 且 忠实误报 ≤1/10。真机运行(qwen3:4b 约 2 分钟)。
"""

import re
from difflib import SequenceMatcher

_SUBSTR_LEN = 8          # 中文归一化后最长公共片段的判定长度(数字claim不走此通道)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_PUNCT_RE = re.compile(r"[，。！？；：、\s\"'“”‘’()（）,.;:!?\[\]【】<>《》\-—…·]")


class FactualityResult:
    def __init__(self, claims):
        self.claims = claims          # [{"claim", "verdict", "method"}]

    @property
    def unsupported(self):
        return [c for c in self.claims if c["verdict"] == "unsupported"]

    @property
    def has_hallucination(self):
        return any(c["verdict"] == "unsupported" for c in self.claims)

    def __repr__(self):
        n = len(self.claims)
        bad = len(self.unsupported)
        return f"FactualityResult({n} claims, {bad} unsupported)"


# ============================================================
# claims 拆分
# ============================================================

def split_claims(answer):
    """按句切分, 过滤过短与纯寒暄句。原子化: 一句一个可判定的事实主张。"""
    parts = re.split(r"[。！？；;\n]", answer)
    claims = []
    for p in parts:
        p = p.strip()
        if len(p) < 6 or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", p):
            continue
        claims.append(p)
    return claims


def _norm(text):
    return _PUNCT_RE.sub("", text)


# ============================================================
# 三级核验
# ============================================================

def _substring_hit(claim_norm, source_norm):
    """子串快车道: 公共片段须覆盖 claim 的大半(≥60% 且 ≥8 字)。

    幻觉句几乎总会复用正确的主题词("Python的list"、"gitpush用于把"),
    只看公共片段长度会把'主题对、断言错'的句子放走 —— 覆盖率门槛把这类
    句子送去 judge, 快车道只留给几乎照抄 source 的 claim。
    """
    size = SequenceMatcher(None, claim_norm, source_norm) \
        .find_longest_match(0, len(claim_norm), 0, len(source_norm)).size
    return size >= max(_SUBSTR_LEN, int(len(claim_norm) * 0.6))


def _numeric_verdict(claim, source_norm):
    """数字核对: 全部不在 -> unsupported; 有在的 -> None(降级 judge); 无数字 -> None。"""
    nums = _NUM_RE.findall(claim)
    if not nums:
        return None
    present = [n for n in nums if n in source_norm]
    if not present:
        return "unsupported"
    return None


JUDGE_PROMPT = ("你是事实核查员。判断待判定句是否与资料完全一致。\n"
                "规则：数字、方向(如 push/pull、覆盖/追加、支持/反对)、主体对象"
                "必须与资料一致；全部一致答 SUPPORTED，任何一处不一致答 UNSUPPORTED。\n"
                "例1 资料：r 是读(值 4)，w 是写(值 2)，x 是执行(值 1)。"
                "待判定句：x 是执行(值 8)。答案：UNSUPPORTED\n"
                "例2 资料：>> 追加到文件末尾。"
                "待判定句：>> 是在文件结尾接着写。答案：SUPPORTED\n"
                "资料：{source}\n待判定句：{claim}\n只回答一个词。/no_think")


def _judge(claim, source, chat_fn):
    prompt = JUDGE_PROMPT.format(source=source, claim=claim)
    text = chat_fn([{"role": "user", "content": prompt}])
    if not text:  # 混合推理模型思考段吃掉 num_predict 时 content 为空, 重试一次
        text = chat_fn([{"role": "user", "content": prompt}])
    if not text:
        return "unknown"
    return "supported" if "SUPPORTED" in text and "UNSUPPORTED" not in text \
        else "unsupported"


def verify_claim(claim, source, chat_fn=None):
    """单条 claim 三级核验, 返回 (verdict, method)。

    顺序是刻意的: 带数字的 claim 不走子串快车道——数字被改错时句子其余部分
    与 source 仍然高度重合(如 SHA-256 vs SHA-1、chmod 755 语义颠倒),
    子串会误判 supported, 所以数字 claim 无论数字是否在场都由 judge 把关。
    """
    nums = _NUM_RE.findall(claim)
    source_norm = _norm(source)
    if nums:
        present = [n for n in nums if n in source_norm]
        if not present:
            return "unsupported", "numeric"
        return (_judge(claim, source, chat_fn), "judge") if chat_fn \
            else ("unknown", "no-judge")
    claim_norm = _norm(claim)
    if _substring_hit(claim_norm, source_norm):
        return "supported", "substring"
    if chat_fn is None:
        return "unknown", "no-judge"
    return _judge(claim, source, chat_fn), "judge"


def check(answer, source, chat_fn=None):
    """幻觉检测主入口: 拆 claims -> 逐条核验。"""
    claims = [{"claim": c,
               "verdict": (v := verify_claim(c, source, chat_fn))[0],
               "method": v[1]}
              for c in split_claims(answer)]
    return FactualityResult(claims)


# ============================================================
# selftest: 5 段 source × 10 幻觉 + 10 忠实
# ============================================================

SOURCES = {
    "git": ("Git 是分布式版本控制系统。git commit 会把暂存区的改动记录为一个版本快照，"
            "快照包含完整的文件内容而非增量。每次 commit 生成一个唯一的 SHA-1 哈希作为标识。"
            "git push 用于把本地提交上传到远程仓库。"),
    "http": ("HTTP 是超文本传输协议，默认使用 80 端口，HTTPS 默认使用 443 端口。"
             "状态码 404 表示资源未找到，500 表示服务器内部错误。"
             "HTTP 是无状态协议，通常用 Cookie 维持会话状态。"),
    "perm": ("Linux 文件权限用 9 位字符表示，分为所有者、组、其他三组，每组是 rwx 三位。"
             "r 是读(值 4)，w 是写(值 2)，x 是执行(值 1)。"
             "chmod 755 表示所有者 rwx，组和其他用户 r-x。root 用户不受权限位限制。"),
    "python": ("Python 的 list 是可变有序容器，tuple 是不可变有序容器。"
               "字典 dict 的键必须是不可变类型。"
               "列表推导式 [x*2 for x in range(5)] 生成 0 到 8 的偶数序列。"),
    "redirect": ("bash 的 > 把标准输出重定向到文件并覆盖原内容，>> 追加到文件末尾。"
                 "2> 只重定向标准错误。&> 同时重定向标准输出和标准错误。"
                 "/dev/null 是黑洞设备，写入的内容被丢弃。"),
}

# (答案, source key, 是否幻觉) —— 幻觉样本含 虚构事实/错数字/语义颠倒/无中生有
SAMPLES = [
    ("git commit 会记录版本快照，每次 commit 生成一个 SHA-256 哈希作为标识。", "git", True),
    ("HTTP 默认使用 8080 端口，HTTPS 默认使用 443 端口。", "http", True),
    ("状态码 404 表示服务器内部错误，500 表示资源未找到。", "http", True),
    ("chmod 755 表示所有者可读写执行，组和其他用户只能读。", "perm", True),
    ("Linux 权限值 r 是 4，w 是 2，x 是 8。", "perm", True),
    ("Python 的 list 和 tuple 都是可变容器，区别是 tuple 速度更快。", "python", True),
    ("列表推导式 [x*2 for x in range(5)] 生成 0 到 18 的偶数序列。", "python", True),
    ("bash 的 > 重定向会保留原内容在末尾追加，2> 用于重定向标准输入。", "redirect", True),
    ("git push 用于把远程仓库的提交拉取到本地。", "git", True),
    ("/dev/null 是日志文件，写入的内容会保存 7 天。", "redirect", True),
    ("git commit 把改动记录为版本快照，并用 SHA-1 哈希唯一标识这次提交。", "git", False),
    ("HTTP 默认走 80 端口，HTTPS 用的是 443。", "http", False),
    ("404 是资源未找到，500 是服务器内部错误。", "http", False),
    ("权限 755 表示所有者 rwx，组和其他用户 r-x。", "perm", False),
    ("r、w、x 对应的权限值分别是 4、2、1。", "perm", False),
    ("list 可变而 tuple 不可变，字典的键必须用不可变类型。", "python", False),
    ("[x*2 for x in range(5)] 会生成 0 到 8 的偶数。", "python", False),
    ("> 覆盖写，>> 追加写。", "redirect", False),
    ("&> 同时重定向标准输出和标准错误，/dev/null 会把写入内容丢弃。", "redirect", False),
    ("Git 是分布式版本控制系统，push 负责把本地提交上传到远程仓库。", "git", False),
]


def selftest(chat_fn):
    """混淆矩阵: 幻觉检出率 与 忠实误报率。检出 >=9 且 误报 <=1 才算 PASS。"""
    tp = fn = tn = fp = 0
    rows = []
    for i, (answer, key, is_halluc) in enumerate(SAMPLES, 1):
        r = check(answer, SOURCES[key], chat_fn=chat_fn)
        detected = r.has_hallucination
        if is_halluc and detected:
            tp += 1
        elif is_halluc and not detected:
            fn += 1
        elif not is_halluc and detected:
            fp += 1
        else:
            tn += 1
        rows.append((i, "幻觉" if is_halluc else "忠实", detected, r))
        print(f"  [{i:02d}] {'✅' if detected == is_halluc else '❌'} "
              f"{'幻觉' if is_halluc else '忠实'} -> "
              f"{'检出' if detected else '通过'} {r}")
    print(f"\n混淆矩阵: 幻觉检出 {tp}/10 (验收 ≥9) · "
          f"忠实误报 {fp}/10 (验收 ≤1) · 漏检 {fn} · 通过 {tn}")
    print("      预测=幻觉  预测=忠实")
    print(f"实际=幻觉   {tp:>4}      {fn:>4}")
    print(f"实际=忠实   {fp:>4}      {tn:>4}")
    return tp >= 9 and fp <= 1


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "qa"))
    import llm as qa_llm
    sys.exit(0 if selftest(qa_llm.chat) else 1)
