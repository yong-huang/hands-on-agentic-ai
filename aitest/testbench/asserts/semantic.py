"""asserts.semantic — 语义断言 (docs/aitest.md 项目 5)

字面断言卡不住同义改写("回归测试是改后重跑旧用例" vs "回归就是改完再验证一遍"),
语义断言用 embedding 余弦相似度做阈值判定:

    check(text, reference, threshold) -> SemanticResult(ok, sim)

阈值不拍脑袋: 内置 10 组"等价改写对"(应通过) + 10 组"同域无关对"(应拒绝),
calibrate() 扫描阈值曲线取判别精度最高点, selftest() 用选定阈值输出两个
10 格矩阵(通过矩阵/拒绝矩阵), 验收口径 双侧 ≥9/10。

embedding 走 Ollama /v1/embeddings(默认模型 nomic-embed-text, 274MB);
零第三方依赖, 离线时 cosine/阈值逻辑可单测(纯函数), selftest 需真机。
"""

import json
import math
import os
import urllib.request

EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")


class SemanticResult:
    def __init__(self, ok, sim, threshold):
        self.ok = ok
        self.sim = round(sim, 4)
        self.threshold = threshold

    def __repr__(self):
        return f"SemanticResult({'PASS' if self.ok else 'FAIL'}, sim={self.sim})"


# ============================================================
# embedding 与相似度
# ============================================================

def embed(text, model=None, timeout=30):
    """单条文本 → 向量。Ollama OpenAI 兼容 /v1/embeddings。"""
    body = json.dumps({"model": model or EMBED_MODEL, "input": text}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/embeddings", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["data"][0]["embedding"]


def cosine(a, b):
    """余弦相似度, 纯函数可单测。零向量按 0.0 处理。"""
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def similarity(text, reference):
    return cosine(embed(text), embed(reference))


def check(text, reference, threshold):
    """语义断言主入口: 相似度达到阈值即 PASS。"""
    sim = similarity(text, reference)
    return SemanticResult(sim >= threshold, sim, threshold)


# ============================================================
# 标定集: 10 组等价改写(应通过) + 10 组同域无关(应拒绝)
# ============================================================

PARAPHRASE_PAIRS = [
    ("回归测试是在软件修改后重新运行已有测试，确认原有功能未被破坏",
     "回归测试就是改完代码后把旧用例再跑一遍，防止新改动弄坏原来的功能"),
    ("Git 的 commit 是把当前改动作为版本快照记录下来，可以随时回退",
     "commit 相当于给代码拍快照存档，之后可以随时退回这个版本"),
    ("80 端口是 HTTP 协议的默认端口，浏览器访问网页时使用",
     "HTTP 服务默认监听 80 端口，上网浏览网页走的就是它"),
    ("ls -l 输出的 rwx 表示读、写、执行三种权限",
     "那串字母是权限位，r 是读 w 是写 x 是执行"),
    ("环境变量是操作系统传给程序运行期的配置，PATH 是典型例子",
     "环境变量就是程序启动时系统递给它的参数，最常见的是 PATH"),
    ("bash 里 > 覆盖写入文件，>> 追加到文件末尾",
     "> 会清空原内容重写，>> 则在文件结尾接着写"),
    ("Python 的 list 可变，tuple 不可变",
     "列表能增删改元素，元组创建之后就不能修改了"),
    ("SSH 默认使用 22 端口做远程登录",
     "远程连接服务器的 ssh 协议默认走 22 号端口"),
    ("run_bash 工具在任务目录里执行 shell 命令并返回输出",
     "run_bash 的作用是在指定目录下跑命令，把 stdout 和 stderr 收回来"),
    ("沙箱为任务提供隔离的执行目录，防止误操作影响宿主系统",
     "沙箱就是个隔离的工作目录，任务里删错文件也不会伤到真实系统"),
]

UNRELATED_PAIRS = [
    ("回归测试是在软件修改后重新运行已有测试，确认原有功能未被破坏",
     "HTTP 默认端口是 80，用于网页服务"),
    ("Git 的 commit 是把当前改动作为版本快照记录下来，可以随时回退",
     "rwx 分别代表读、写、执行三种权限"),
    ("80 端口是 HTTP 协议的默认端口，浏览器访问网页时使用",
     "Python 的 tuple 一旦创建就不能修改元素"),
    ("ls -l 输出的 rwx 表示读、写、执行三种权限",
     "环境变量 PATH 决定了系统去哪里找命令"),
    ("环境变量是操作系统传给程序运行期的配置，PATH 是典型例子",
     "git commit 会为当前改动创建一个可回退的版本"),
    ("bash 里 > 覆盖写入文件，>> 追加到文件末尾",
     "SSH 是加密的远程登录协议，默认端口 22"),
    ("Python 的 list 可变，tuple 不可变",
     "回归测试要在每次代码改动之后重新执行既有用例"),
    ("SSH 默认使用 22 端口做远程登录",
     "bash 的 >> 重定向把输出追加到文件尾部"),
    ("run_bash 工具在任务目录里执行 shell 命令并返回输出",
     "80 端口承载着 HTTP 网页流量"),
    ("沙箱为任务提供隔离的执行目录，防止误操作影响宿主系统",
     "list 是 Python 里可变的有序容器"),
]


def calibrate(verbose=True):
    """扫描阈值 0.40→0.95(步长 0.05), 返回判别精度最高的阈值与曲线数据。"""
    pos = [similarity(p, r) for r, p in PARAPHRASE_PAIRS]
    neg = [similarity(p, r) for r, p in UNRELATED_PAIRS]
    curve = []
    best = (0.70, -1.0)
    t = 0.40
    while t <= 0.951:
        acc = sum(s >= t for s in pos) / len(pos) * 0.5 + \
              sum(s < t for s in neg) / len(neg) * 0.5
        curve.append((round(t, 2), round(acc, 3)))
        if acc > best[1]:
            best = (round(t, 2), acc)
        t += 0.05
    if verbose:
        print("阈值扫描曲线 (threshold -> balanced accuracy):")
        for th, a in curve:
            bar = "█" * int(a * 30)
            mark = "  ← 选定" if abs(th - best[0]) < 1e-9 else ""
            print(f"  {th:.2f}  {a:.3f} {bar}{mark}")
    return best[0], curve, pos, neg


def _matrix(pairs, threshold, expect_pass):
    cells = [("✅" if (sim >= threshold) == expect_pass else "❌")
             for _, sim in pairs]
    return cells, sum(1 for c in cells if c == "✅")


def selftest(threshold=None):
    """验收入口: 标定 → 双侧矩阵。返回 bool。"""
    threshold, _, pos, neg = calibrate()
    print(f"\n选定阈值: {threshold}")
    pos_pairs = list(zip([p for _, p in PARAPHRASE_PAIRS], pos))
    neg_pairs = list(zip([p for _, p in UNRELATED_PAIRS], neg))
    cells_p, n_pass = _matrix(pos_pairs, threshold, expect_pass=True)
    cells_n, n_rej = _matrix(neg_pairs, threshold, expect_pass=False)

    def show(title, pairs, cells):
        print(f"\n{title}")
        for i, ((text, sim), mark) in enumerate(zip(pairs, cells), 1):
            print(f"  [{i:02d}] {mark} sim={sim:.3f} {text[:28]}...")

    show("等价改写矩阵(应 PASS):", pos_pairs, cells_p)
    show("同域无关矩阵(应 REJECT):", neg_pairs, cells_n)
    print(f"\n通过 {n_pass}/10 (验收 ≥9) · 拒绝 {n_rej}/10 (验收 ≥9)")
    return n_pass >= 9 and n_rej >= 9


if __name__ == "__main__":
    import sys
    sys.exit(0 if selftest() else 1)
