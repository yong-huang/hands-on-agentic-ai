"""
文档加载与切分 — RAG 的第一步 (不依赖任何 LLM/API, 纯离线)

RAG 的答案质量上限由检索决定, 检索质量的上限由切分决定。本篇实现 RAG 管线的
第一环: 把 docs/ 下的多种格式 (txt / md / pdf) 加载成统一的 Document,
再用递归字符策略切分成带元数据的 chunk。

两种模式 (均离线, 无需 Ollama):
  --demo  内联示例文本, 演示切分算法本身
  默认    加载 docs/ 目录 (md + txt + pdf 三种格式)

递归字符切分的核心思想: 优先按语义边界切 (段落 -> 句子 -> 字符),
块间保留 overlap 防止关键句被切断。LangChain 的
RecursiveCharacterTextSplitter 就是这个算法的工业版。
"""

import os
import sys
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(SCRIPT_DIR, "docs")

SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", " ", ""]   # 语义边界优先级
CHUNK_SIZE = 120        # 每块目标上限 (字符)
OVERLAP = 30            # 相邻块重叠字符数


# ============================================================
# 加载器: 三种格式 -> 统一的 Document
# ============================================================

def normalize(text):
    """NFKC 归一化: Chrome 生成的 PDF 常把汉字映射成兼容形式 (⼿ U+2F8B
    而非 手 U+624B), 不归一化会让检索时同一个词匹配不上。"""
    return unicodedata.normalize("NFKC", text)


def load_txt(path):
    with open(path, encoding="utf-8") as f:
        return normalize(f.read())


def load_md(path):
    """Markdown: 去掉标记符号但保留标题行作为结构边界。"""
    lines = []
    for line in load_txt(path).splitlines():
        lines.append(line.lstrip("#").strip() if line.startswith("#") else line)
    return "\n".join(lines)


def load_pdf(path):
    """PDF: pypdf 提取文本 (安装: pip install pypdf)。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit(f"读取 PDF 需要 pypdf: pip install pypdf ({path})")
    reader = PdfReader(path)
    return normalize("\n".join(page.extract_text() or "" for page in reader.pages))


LOADERS = {".txt": load_txt, ".md": load_md, ".pdf": load_pdf}


def load_directory(root):
    """扫描目录, 按扩展名分派加载器, 返回统一 Document 列表。"""
    docs = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        ext = os.path.splitext(name)[1].lower()
        if os.path.isfile(path) and ext in LOADERS:
            text = LOADERS[ext](path)
            docs.append({"source": name, "type": ext.lstrip("."), "text": text})
    return docs


# ============================================================
# 递归字符切分
# ============================================================

def _split_by_sep(text, sep):
    if sep == "":
        return list(text)                    # 最后手段: 逐字符
    parts = text.split(sep)
    return [p + sep for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def recursive_split(text, separators=SEPARATORS, chunk_size=CHUNK_SIZE):
    """优先用高级别分隔符; 超长片段降级到下一级分隔符递归。"""
    if estimate_len(text) <= chunk_size:
        return [text]
    sep, rest = separators[0], separators[1:]
    pieces = _split_by_sep(text, sep) if sep in text else ([text] if sep == "" else recursive_split(text, rest, chunk_size))
    chunks = []
    for piece in pieces:
        if estimate_len(piece) <= chunk_size:
            chunks.append(piece)
        elif rest:
            chunks.extend(recursive_split(piece, rest, chunk_size))
        else:
            # 无分隔符可用: 硬切 (理论上到不了这里, 兜底)
            chunks.extend(piece[i:i + chunk_size] for i in range(0, len(piece), chunk_size))
    return chunks


def estimate_len(text):
    """切分用的长度口径: CJK 记 1, 其余记 0.5 (近似 token 感知)。"""
    cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
    return cjk + round((len(text) - cjk) * 0.5)


def merge_with_overlap(pieces, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    """小片合并成块; 相邻块之间回填 overlap 尾部, 防止关键句被切断。"""
    chunks, current = [], ""
    for piece in pieces:
        if current and estimate_len(current + piece) > chunk_size:
            chunks.append(current)
            current = current[-overlap:] + piece if overlap else piece
        else:
            current += piece
    if current.strip():
        chunks.append(current)
    return chunks


def split_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    return merge_with_overlap(recursive_split(text, chunk_size=chunk_size),
                              chunk_size, overlap)


def split_documents(docs, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    """切分并挂元数据: 来源文件 + 块序号。"""
    chunks = []
    for doc in docs:
        for i, piece in enumerate(split_text(doc["text"], chunk_size, overlap)):
            chunks.append({"source": doc["source"], "type": doc["type"],
                           "chunk_id": i, "text": piece.strip()})
    return chunks


# ============================================================
# 报告
# ============================================================

def print_report(docs, chunks):
    print("\n--- 加载报告 ---")
    for doc in docs:
        print(f"  {doc['source']:22s} [{doc['type']:3s}] {len(doc['text'])} 字符")
    sizes = [estimate_len(c["text"]) for c in chunks]
    print(f"\n--- 切分报告 ---")
    print(f"  chunk 数: {len(chunks)}   "
          f"长度 min/avg/max = {min(sizes)}/{sum(sizes) // len(sizes)}/{max(sizes)}")
    over = [s for s in sizes if s > CHUNK_SIZE * 1.3]
    print(f"  超限块 (>{CHUNK_SIZE * 1.3}): {len(over)} 个")

    print("\n--- 前两个 chunk (注意块尾/块首的 overlap 衔接) ---")
    for c in chunks[:2]:
        preview = c["text"].replace("\n", " ")
        print(f"  [{c['source']}#{c['chunk_id']}] {preview[:70]}…")


# ============================================================
# 入口
# ============================================================

def run(docs_root):
    if not os.path.isdir(docs_root):
        raise SystemExit(f"目录不存在: {docs_root}")
    docs = load_directory(docs_root)
    if not docs:
        raise SystemExit(f"{docs_root} 中没有可加载的文件 (支持: {', '.join(LOADERS)})")
    chunks = split_documents(docs)
    print(f"加载目录: {docs_root}")
    print_report(docs, chunks)


def run_demo():
    """内联文本演示: 只用切分算法本身, 不读任何文件。"""
    text = ("RAG 的答案质量上限由检索决定。\n\n"
            "切分直接决定检索精度：块太大带噪音，块太小缺上下文。\n"
            "递归字符切分优先按段落切，段落太长再按句子切。\n"
            "相邻块保留重叠，关键句就不会被边界切断。")
    print("=" * 60)
    print("文档加载与切分 -- Demo 模式（内联文本, 演示切分算法）")
    print("=" * 60)
    chunks = split_text(text)
    print(f"\n输入 {len(text)} 字符 -> {len(chunks)} 个 chunk:")
    for i, c in enumerate(chunks):
        bar = "█" * max(1, estimate_len(c) // 10)
        print(f"  [{i}] ({estimate_len(c):3d}) {bar}")
        print(f"      {c.strip()[:56]}…")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        print("Usage: python doc_splitting.py [--demo] [docs_dir]\n"
              "  --demo            : 内联文本演示切分算法（离线）\n"
              "  (无参数)           : 加载 docs/ 目录 (md + txt + pdf, 离线)\n")
        run(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else DOCS_DIR)
