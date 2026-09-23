# 20 · 文档加载与切分：RAG 的第一步

> 把 docs/ 下的 md / txt / pdf 三种格式加载成统一的 Document，再用递归
> 字符策略切成带来源元数据的 chunk。全程离线，不依赖任何模型。

## What

RAG 管线第一环：检索的对象不是文档本身，而是**切分后的块（chunk）**。
三种原始文件（md / txt / pdf）按扩展名分派给对应加载器，统一成
`Document`（source + type + text，PDF 文本经过 NFKC 归一化）；然后
`recursive_split` 按"段落 → 句子 → 字符"的优先级降级切分，小片合并成块
并在相邻块间回填 overlap，每个块带来源与序号。

统一文档结构：

| 字段 | 内容 | 用途 |
| :--- | :--- | :--- |
| source | 来源文件名 | 答案溯源 |
| type | txt / md / pdf | 调试与过滤 |
| text | 归一化后的全文 | 切分输入 |

心智模型一句话：**切分 = 沿语义边界把文档撕成整齐的小条，撕口互相咬合。**

## Why

模型的知识停在训练截止日，私有数据也不在模型参数里——RAG 的解法是
"先检索、后生成"。而切分粒度直接决定"检索回来的东西有没有用"：块太大
带噪音，块太小缺上下文。把这条链路的最前端做扎实，后面向量化与检索才有
意义。

## How

```bash
cd agents/20_doc_splitting
python doc_splitting.py --demo   # 内联文本演示切分算法
python doc_splitting.py          # 加载 docs/ 目录（md + txt + pdf）
```

目录模式会加载 docs/ 下三个样例文件并打印加载与切分两份报告。**实测
输出**：3 个文件共 735 字符 → 9 个 chunk，块长 78/89/100（min/avg/max），
0 个超限；chunk #0 尾部"…重新打"与 chunk #1 开头"测试用例上重新打分"
就是 overlap 衔接。

**递归字符切分：语义边界优先**——分隔符按优先级排队：`\n\n`（段落）→
`\n`（换行）→ `。！？；`（句子）→ 空格 → 逐字符。算法对超出块上限的片段
**降级**到下一级分隔符继续切——段落放得下就不拆句子，句子放得下就不拆词。
这就是 LangChain `RecursiveCharacterTextSplitter` 的核心思想，本篇用
40 行手写：

```python
def recursive_split(text, separators=SEPARATORS, chunk_size=CHUNK_SIZE):
    if estimate_len(text) <= chunk_size:
        return [text]
    sep, rest = separators[0], separators[1:]
    pieces = _split_by_sep(text, sep) if sep in text else (
        [text] if sep == "" else recursive_split(text, rest, chunk_size))
    chunks = []
    for piece in pieces:
        if estimate_len(piece) <= chunk_size:
            chunks.append(piece)
        elif rest:
            chunks.extend(recursive_split(piece, rest, chunk_size))   # 降级
        else:
            chunks.extend(piece[i:i+chunk_size]
                          for i in range(0, len(piece), chunk_size))  # 硬切兜底
    return chunks
```

**overlap：撕口互相咬合**——相邻块回填约 30 字符的尾部重叠。没有 overlap
时，"每次修改提示词都需要在同一组用例上重新打**分**"这句话可能被切成
两半，两半都答不全"怎么评估"。

## Deep Dive

**真实坑：PDF 的 NFKC 归一化**——Chrome 生成的 PDF 用 CID 字体，pypdf
提取出的汉字常是**兼容形式**（"⼿" U+2F8B 而非"手" U+624B）。肉眼看着
一样，检索时同一个词就是匹配不上。加载器统一做
`unicodedata.normalize("NFKC", text)`——**归一化必须发生在切分之前**。

踩坑清单：

- 长度口径用"CJK 记 1、其余记 0.5"的近似——纯字符数会低估中文信息密度；
- overlap 太大等于变相放大块，太小防不住切断，120/30 是本实验的折中值；
- 切分前必须归一化（NFKC）与去掉 Markdown 标记符号，否则垃圾进垃圾出。

## Q&A

**Q1: 块大小的权衡是什么？**

检索与注入都以 chunk 为单位。太大：一块多主题，检索带噪音；太小：上下文
不完整。折中值靠评估实验定，不是拍脑袋。

**Q2: overlap 解决什么问题？代价是什么？**

防止关键句被块边界切成两半；代价是存储与索引的少量冗余。

**Q3: chunk 的元数据有什么用？**

溯源（答案引用出处）、过滤（按文件/章节限定检索范围）、去重与更新。
