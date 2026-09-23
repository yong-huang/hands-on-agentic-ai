"""
面试项目 6 — ToT 求解器（BFS vs DFS）

覆盖面试题: ToT 和 CoT 本质区别？BFS/DFS 怎么选？计算成本怎么控？

核心: 思维树 (Tree of Thoughts) 引擎, 两个任务域共用:
  24 点游戏   状态 = 剩余数字, 动作 = 一次四则组合, 目标 = 只剩 24
  迷宫最短路  状态 = 坐标, 动作 = U/D/L/R, 目标 = 出口
LLM 只负责"生成候选"（每次扩展 1 次调用要 k 个候选）, 评估打分用规则
（24 点: 剩余数字能否凑出 24 的可达性神谕; 迷宫: 曼哈顿距离）, 搜索策略
BFS/DFS 可切换, 剪枝 = 分数阈值丢弃。统计每配置 LLM 调用数与成功率。

运行:
  MOCK=1 python tot_solver.py    # 离线: 求解器引导的预置提议 (结果确定)
  python tot_solver.py           # 真实: qwen3.8 生成候选
"""

import json, os, re, sys, urllib.request
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import BASE_URL, MODEL, API_KEY

MOCK = os.environ.get("MOCK") == "1"
EPS = 1e-6


def extract_json(text):
    """剥离思考标签后, 从后往前找第一个能解析的 JSON 块 (思考文本可能含花括号)。"""
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    for pat in (r"\[[^\[\]]*\]", r"\{[^{}]*\}"):
        for m in reversed(re.findall(pat, text, re.S)):
            try:
                return json.loads(m)
            except json.JSONDecodeError:
                continue
    return None


def llm_json(messages, num_predict=1500):
    """调用 LLM 并提取 JSON。注意: qwen3.8 是思考模型, max_tokens 必须
    覆盖思考+作答 (实测 900 仍被思考烧光, 1500 才能产出 content JSON)。"""
    if MOCK:
        return None
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": num_predict}
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
    except Exception as e:
        print(f"    ⚠ LLM 调用异常: {e}")
        return None
    r = extract_json(msg.get("content") or "")
    if r is None:
        r = extract_json(msg.get("reasoning") or msg.get("reasoning_content") or "")
    return r


# ============================================================
# 24 点任务域
# ============================================================

def can_reach(nums, target=24):
    """可达性神谕: 剩余数字能否通过四则运算凑出 target (指数复杂度但 n≤4 很快)。"""
    if len(nums) == 1:
        return abs(nums[0] - target) < EPS
    n = len(nums)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a, b = nums[i], nums[j]
            rest = [nums[k] for k in range(n) if k not in (i, j)]
            for v in (a + b, a - b, a * b):
                if can_reach(rest + [v], target):
                    return True
            if abs(b) > EPS and can_reach(rest + [a / b], target):
                return True
    return False


def solve_24_exact(nums):
    """穷举求解, 返回表达式串 (mock 提议器与展示用)。"""
    def rec(nums, exprs):
        if len(nums) == 1:
            return exprs[0] if abs(nums[0] - 24) < EPS else None
        n = len(nums)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                a, b, ea, eb = nums[i], nums[j], exprs[i], exprs[j]
                rest_n = [nums[k] for k in range(n) if k not in (i, j)]
                rest_e = [exprs[k] for k in range(n) if k not in (i, j)]
                for op in "+-*/":
                    if op == "/" and abs(b) < EPS:
                        continue
                    if op == "+":
                        v = a + b
                    elif op == "-":
                        v = a - b
                    elif op == "*":
                        v = a * b
                    else:
                        v = a / b
                    r = rec(rest_n + [v], rest_e + [f"({ea}{op}{eb})"])
                    if r:
                        return r
        return None
    return rec(list(nums), [str(x) for x in nums])


class Game24:
    name = "24点"
    max_depth = 3
    max_calls = 12
    prune_threshold = 0.5          # 剪枝: 剩余数字凑不出 24 (score=0) 的分支丢弃

    def __init__(self, nums):
        assert can_reach(nums), f"{nums} 无解"
        self.init_nums = sorted(nums)
        self.answer_expr = solve_24_exact(self.init_nums)

    def init_state(self):
        return {"nums": list(self.init_nums), "exprs": [str(x) for x in self.init_nums]}

    def is_goal(self, state):
        return len(state["nums"]) == 1 and abs(state["nums"][0] - 24) < EPS

    def key(self, state):
        return tuple(sorted(round(x, 6) for x in state["nums"]))

    def apply(self, state, cand):
        """候选 {"i","j","op"}: 对下标 i,j 两数做一次四则运算。非法返回 None。"""
        try:
            op = {"×": "*", "÷": "/", "＋": "+", "－": "-"}.get(str(cand["op"]),
                                                              str(cand["op"]))
            i, j = int(cand["i"]), int(cand["j"])
            nums = state["nums"]
            if not (0 <= i < len(nums) and 0 <= j < len(nums)) or i == j or op not in "+-*/":
                return None
            a, b = nums[i], nums[j]
            if op == "/" and abs(b) < EPS:
                return None
            if op == "+":
                v = a + b
            elif op == "-":
                v = a - b
            elif op == "*":
                v = a * b
            else:
                v = a / b
            ea, eb = state["exprs"][i], state["exprs"][j]
            return {"nums": [x for k, x in enumerate(nums) if k not in (i, j)] + [v],
                    "exprs": [x for k, x in enumerate(state["exprs"]) if k not in (i, j)]
                             + [f"({ea}{op}{eb})"]}
        except (KeyError, TypeError, ValueError):
            return None

    def evaluate(self, state):
        return 1.0 if can_reach(state["nums"]) else 0.0

    def propose(self, state, strategy_tag):
        if MOCK:
            # 求解器引导: 沿"保持可达"的一步作为候选, 再给一个干扰候选
            step = self._greedy_step(state)
            cands = [step] if step else []
            cands.append({"i": 0, "j": 1, "op": "+"})
            return cands[:3]
        nums = state["nums"]
        idx = " ".join(f"#{k}:{x}" for k, x in enumerate(nums))
        prompt = (f"24点游戏。当前数字: {idx}。\n"
                  "选两个数字做一次四则运算合并成一个新数, 给出最多 3 个不同候选, "
                  '只输出 JSON 数组: [{"i": 下标, "j": 下标, "op": "+-*/"}, ...]')
        r = llm_json([{"role": "user", "content": prompt}])
        if isinstance(r, dict):                     # 模型可能用对象包一层
            r = next((v for v in r.values() if isinstance(v, list)), [])
        return r if isinstance(r, list) else []

    def _greedy_step(self, state):
        nums = state["nums"]
        for i in range(len(nums)):
            for j in range(len(nums)):
                if i == j:
                    continue
                for op in "+-*/":
                    if op == "/" and abs(nums[j]) < EPS:
                        continue
                    st2 = self.apply(state, {"i": i, "j": j, "op": op})
                    if st2 and self.evaluate(st2) > 0:
                        return {"i": i, "j": j, "op": op}
        return None

    def result(self, state):
        return state["exprs"][0]


# ============================================================
# 迷宫任务域
# ============================================================

class Maze:
    max_depth = 40
    max_calls = 40

    def __init__(self, grid, name):
        self.grid, self.name_ = grid, name
        self.h, self.w = len(grid), len(grid[0])
        self.start = next((r, c) for r in range(self.h) for c in range(self.w)
                          if grid[r][c] == "S")
        self.goal = next((r, c) for r in range(self.h) for c in range(self.w)
                         if grid[r][c] == "G")
        self.max_dist = self.h + self.w

    def init_state(self):
        return self.start

    def is_goal(self, state):
        return state == self.goal

    def key(self, state):
        return state

    def apply(self, state, cand):
        mv = cand.get("move", "") if isinstance(cand, dict) else None
        dr, dc = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}.get(mv, (0, 0))
        r, c = state[0] + dr, state[1] + dc
        if 0 <= r < self.h and 0 <= c < self.w and self.grid[r][c] != "#":
            return (r, c)
        return None

    def evaluate(self, state):
        d = abs(state[0] - self.goal[0]) + abs(state[1] - self.goal[1])
        return 1.0 - d / self.max_dist

    def propose(self, state, strategy_tag):
        if MOCK:
            opts = []
            for mv in "UDLR":
                st2 = self.apply(state, {"move": mv})
                if st2 is not None:
                    opts.append((self.evaluate(st2), mv))
            opts.sort(reverse=True)
            best = [{"move": mv} for _, mv in opts[:2]]
            if opts:
                best.append({"move": opts[-1][1]})     # 掺一个远离出口的干扰走法
            return best
        r, c = state
        rows = []
        for rr in range(max(0, r - 1), min(self.h, r + 2)):
            rows.append("".join("#" if self.grid[rr][cc] == "#" else
                                ("你" if (rr, cc) == (r, c) else
                                 ("出" if (rr, cc) == self.goal else "."))
                                for cc in range(max(0, c - 1), min(self.w, c + 2))))
        prompt = ("迷宫局部图 (#墙 .路 出=出口 你=当前位置):\n" + "\n".join(rows) +
                  '\n走一步(U/D/L/R), 只输出 JSON: {"move": "U"}')
        r2 = llm_json([{"role": "user", "content": prompt}])
        return [r2] if isinstance(r2, dict) else []

    def result(self, state):
        return f"到达 {state}"


MAZE = Maze([
    "S..#..",
    ".##..#",
    "...#..",
    "#.#...",
    "...#.G",
    ".#....",
], "maze6x6")


# ============================================================
# ToT 引擎: BFS / DFS + 剪枝
# ============================================================

class Node:
    __slots__ = ("state", "score", "parent", "depth")

    def __init__(self, state, score, parent):
        self.state, self.score = state, score
        self.parent, self.depth = parent, (parent.depth + 1 if parent else 0)


def tot_solve(domain, strategy="bfs", prune=False):
    """搜索主循环。返回 (成功?, 结果串, LLM调用数, 展开节点数)。"""
    root = Node(domain.init_state(), domain.evaluate(domain.init_state()), None)
    frontier = deque([root])
    visited = {domain.key(root.state)}
    calls = expanded = 0
    while frontier and calls < domain.max_calls:
        node = frontier.popleft() if strategy == "bfs" else frontier.pop()
        if domain.is_goal(node.state):
            return True, domain.result(node.state), calls, expanded
        if node.depth >= domain.max_depth:
            continue
        proposals = domain.propose(node.state, strategy)
        calls += 1
        expanded += 1
        children = []
        for cand in proposals:
            st2 = domain.apply(node.state, cand)
            if st2 is None or domain.key(st2) in visited:
                continue
            visited.add(domain.key(st2))
            score = domain.evaluate(st2)
            if prune:
                # 24点: 不可达即剪; 迷宫: 允许至多"一步远离"的绕行, 更远的回退剪掉
                thr = Game24.prune_threshold if isinstance(domain, Game24) \
                    else node.score - 1.0 / domain.max_dist - 1e-9
                if score < thr:
                    continue
            children.append(Node(st2, score, node))
        children.sort(key=lambda n: -n.score)
        for c in children[:2]:                 # beam=2: 每节点最多保留 2 个子节点
            frontier.append(c)                 # BFS 队列层进 / DFS 栈: 高分后入先出
    return False, "搜索预算耗尽", calls, expanded


def cot_24(domain):
    """CoT 基线: 一步到位输出完整表达式, 程序验证。"""
    prompt = (f"用数字 {domain.init_nums} 和 +-*/ 及括号算出 24, 每个数恰好用一次。"
              '只输出 JSON: {"expr": "表达式"}')
    r = llm_json([{"role": "user", "content": prompt}])
    if not isinstance(r, dict):
        return False, "解析失败", 1
    expr = str(r.get("expr", ""))
    try:
        used = sorted(int(x) for x in re.findall(r"\d+", expr))
        val = eval(re.sub(r"[^0-9\+\-\*\/\.\(\) ]", "", expr))
    except Exception:
        return False, f"非法表达式 {expr!r}", 1
    ok = used == sorted(domain.init_nums) and abs(val - 24) < EPS
    return ok, expr, 1


def cot_maze(domain):
    """CoT 基线: 一步输出完整走法序列, 逐步模拟。"""
    prompt = (f"迷宫 {domain.h}x{domain.w}, 起点 {domain.start}, 出口 {domain.goal}, "
              f'# 是墙。输出一连串走法(U/D/L/R), 只输出 JSON: {{"moves": "DDRR..."}}')
    r = llm_json([{"role": "user", "content": prompt}])
    if not isinstance(r, dict):
        return False, "解析失败", 1
    pos, path = domain.start, ""
    for mv in str(r.get("moves", "")):
        st2 = domain.apply(pos, {"move": mv})
        if st2 is None:
            return False, f"撞墙@{path}", 1
        pos, path = st2, path + mv
        if pos == domain.goal:
            return True, path, 1
    return False, path, 1


# ============================================================
# 实验: 10 题 24 点 + 迷宫, CoT vs ToT(BFS/DFS/BFS+剪枝)
# ============================================================

PUZZLES = [[1, 2, 3, 4], [1, 3, 4, 6], [1, 5, 5, 5], [2, 3, 4, 6], [1, 1, 3, 8],
           [4, 6, 1, 2], [6, 6, 6, 6], [3, 3, 7, 7], [3, 3, 8, 8], [4, 4, 10, 10]]

# mock CoT 预置: 简单题一步答对, 难题([3,3,7,7]类)一步失败 —— 模拟小模型真实行为
MOCK_COT_EASY = [[1, 2, 3, 4], [1, 1, 3, 8], [4, 6, 1, 2], [6, 6, 6, 6]]

CONFIGS = [("CoT", None, None), ("ToT-BFS", "bfs", False),
           ("ToT-DFS", "dfs", False), ("ToT-BFS+剪枝", "bfs", True)]
# 真机模式只跑 CoT + ToT-BFS+剪枝 (思考模型约 100s/次, BFS/DFS 策略对比
# 是引擎机制与模型无关, 由离线 mock 全量覆盖)
ACTIVE = CONFIGS if MOCK else [CONFIGS[0], CONFIGS[3]]


def main():
    maze_tag = f"迷宫 {MAZE.name_} {MAZE.h}x{MAZE.w}"
    print("=" * 72)
    print(f"ToT 求解器 (BFS vs DFS vs 剪枝) -- {'MOCK (离线)' if MOCK else '真实 qwen3.8'}")
    print(f"24点 {len(PUZZLES)} 题 | {maze_tag} | beam=2 | 评估器=规则神谕")
    print(f"真机配置: {[c[0] for c in ACTIVE]}" +
          (" (BFS/DFS 策略对比见 mock 全量表)" if not MOCK else ""))
    print("=" * 72)

    stats = {name: {"ok": 0, "calls": 0} for name, _, _ in ACTIVE}
    for nums in PUZZLES:
        dom = Game24(nums)
        print(f"\n24点 {nums}:  神谕解 {dom.answer_expr}")
        for name, strat, pr in ACTIVE:
            if name == "CoT":
                ok, res, calls = cot_24(dom) if not MOCK else \
                    (nums in MOCK_COT_EASY, dom.answer_expr if nums in MOCK_COT_EASY
                     else "一步推理失败", 1)
            else:
                ok, res, calls, _ = tot_solve(dom, strat, pr)
            stats[name]["ok"] += ok
            stats[name]["calls"] += calls
            print(f"  [{name:<12}] {'✓' if ok else '✗'} calls={calls}  {res[:46]}")

    maze_stats = None
    if MOCK:
        print(f"\n==> {maze_tag}")
        maze_stats = {}
        for name, strat, pr in CONFIGS:
            if name == "CoT":
                ok, res, calls = cot_maze(MAZE) if not MOCK else \
                    (False, "一步规划路径错误", 1)
            else:
                ok, res, calls, _ = tot_solve(MAZE, strat, pr)
            maze_stats[name] = (ok, calls, res)
            print(f"  [{name:<12}] {'✓' if ok else '✗'} calls={calls}  {res[:46]}")

    print("\n" + "=" * 72)
    print(f"{'配置':<14}{'24点成功':>9}{'24点调用':>9}"
          + (f"{'迷宫':>6}{'迷宫调用':>9}" if MOCK else ""))
    print("-" * 72)
    for name, _, _ in ACTIVE:
        row = f"{name:<14}{stats[name]['ok']:>6}/10{stats[name]['calls']:>9}"
        if MOCK:
            m_ok, m_calls, _ = maze_stats[name]
            row += f"{'✓' if m_ok else '✗':>7}{m_calls:>9}"
        print(row)
    if MOCK:
        bfs_calls = stats["ToT-BFS"]["calls"]
        pruned_calls = stats["ToT-BFS+剪枝"]["calls"]
        saved = 100 - pruned_calls * 100 // max(bfs_calls, 1)
        print("-" * 72)
        print(f"剪枝节省 (24点): {bfs_calls} → {pruned_calls} 次调用 (省 {saved}%)"
              f"  {'✓ ≥30%' if saved >= 30 else '✗ <30%'}")
    print(f"""
要点: ToT vs CoT / BFS vs DFS / 成本控制
  1) 本质区别: CoT 是单链自回归, 错一步错到底; ToT 是树搜索, 支持
     分叉-评估-回溯——把"生成"交给模型, 把"验证与调度"交给程序。
  2) BFS vs DFS: BFS 层层展开、找浅解稳但调用多; DFS 贪心深潜、首解
     快但回溯代价大 (离线全量表: 24点两者相近, 迷宫 DFS 13 < BFS 17)。
  3) 成本控制三板斧: beam 宽度限制每层保留数 / 评估器剪枝砍死分支 /
     max_calls 预算熔断。评估器越强(本题是神谕), 剪枝省得越多。
""")


if __name__ == "__main__":
    main()
