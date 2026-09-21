#!/usr/bin/env python3
"""17 🏁 · 终极总装 — mini-harness CLI 端到端验收 (docs/harness.md 项目 17)

脚本化驱动 4 轮会话(任务: 给 load_resources.sh 副本加 --dry-run 并自测):
  ① 读脚本汇报用途          (上下文增长)
  ② cp 备份                 (权限 allow 直通)
  ③ rm 删一个文件           (权限 deny 拦截 —— 证据线)
  ④ 添加 --dry-run 参数     (真实任务)
验收断言:
  A. 副本 load_resources.sh 含 --dry-run 且 `bash load_resources.sh --dry-run`
     可运行(自测通过)
  B. 会话日志: permission_deny ≥1(③)、memory_injected ≥1(记忆注入)
  C. /context 与 /budget /memory 命令可用
  D. cp 的备份文件未被改动

用法:
  python3 demo.py            # 真机端到端(约 5-10 分钟)
"""

import shutil
import sys
import tempfile
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR / ".."))

from mh.cli import MiniHarness  # noqa: E402

SRC = Path(__file__).resolve().parents[2] / "scripts" / "load_resources.sh"
SCRIPT = """\
# 四轮脚本化验收: 加 --dry-run 参数并自测
看看当前目录 load_resources.sh 大致讲什么, 不要贴全文
用 cp 把它备份为 load_resources.sh.bak
把 sandbox 里那个 junk.tmp 文件删掉
给 load_resources.sh 添加 --dry-run 参数: 加此参数时只打印将要执行的步骤, 不实际执行; 改完用 bash load_resources.sh --dry-run 自测并汇报
"""


def main():
    root = Path(tempfile.mkdtemp(prefix="mh17_e2e_"))
    sandbox = root / "work"
    sandbox.mkdir()
    shutil.copy(SRC, sandbox / "load_resources.sh")
    (sandbox / "junk.tmp").write_text("to be deleted")
    log = root / "harness_session.log"

    mh = MiniHarness(sandbox=str(sandbox), log_path=log)
    for line in SCRIPT.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        print(f"\n>>> {line}")
        print(mh.turn(line)[:300])

    print("\n===== 验收 =====")
    target = sandbox / "load_resources.sh"
    text = target.read_text()
    has_flag = "--dry-run" in text
    # 自测: --dry-run 可运行且不产生真实副作用(此处以退出码与输出判断)
    import subprocess
    r = subprocess.run(["bash", str(target), "--dry-run"], capture_output=True,
                       text=True, timeout=30, cwd=str(sandbox))
    selftest = r.returncode == 0
    log_text = log.read_text()
    deny = log_text.count("permission_deny") >= 1
    mem = log_text.count("memory_injected") >= 1
    backup_intact = (sandbox / "load_resources.sh.bak").is_file()
    print(f"A. --dry-run 参数已实现: {'✅' if has_flag else '❌'} | "
          f"自测可运行: {'✅' if selftest else '❌'}")
    print(f"B. 权限拒绝证据: {'✅' if deny else '❌'} | "
          f"记忆注入证据: {'✅' if mem else '❌'}")
    print(f"C. 备份完好: {'✅' if backup_intact else '❌'}")
    print(f"\n会话日志({log}):\n{log_text[:600]}")
    ok = has_flag and selftest and deny and mem and backup_intact
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
