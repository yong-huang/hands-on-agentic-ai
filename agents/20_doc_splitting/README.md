# 20 · 文档加载与切分：RAG 的第一步

> 进入第五阶段 RAG。检索增强生成的答案质量上限由检索决定，而检索质量的上限
> 由**切分**决定——块太大带噪音，块太小缺上下文。本篇实现 RAG 管线的第一环：
> 把 docs/ 下的 md / txt / pdf 三种格式加载成统一的 Document，再用递归字符
> 策略切成带来源元数据的 chunk。全程离线，不依赖任何模型。

## 1. 为什么需要它

模型的知识停在训练截止日，私有数据也不在模型参数里——RAG 的解法是"先检索、
后生成"。但检索的对象不是文档本身，而是**切分后的块（chunk）**：切分粒度直接
决定"检索回来的东西有没有用"。本篇把这条链路的最前端做扎实：多种格式的统一
加载、语义边界优先的递归切分、块级元数据。下一章（21）把这些块向量化建索引。

## 2. 总览：核心机制一图看懂

![文档加载与递归字符切分](images/doc_splitting.dataflow.svg)

**怎么看这张图**：三种原始文件（md / txt / pdf）按扩展名分派给对应加载器，
统一成 `Document`（source + type + text，PDF 文本经过 NFKC 归一化）；然后
`recursive_split` 按"段落 → 句子 → 字符"的优先级降级切分，小片合并成块并在
相邻块间回填 overlap，每个块带来源与序号。

心智模型一句话：**切分 = 沿语义边界把文档撕成整齐的小条，撕口互相咬合。**

🌐 **交互版**：[在线打开（GitHub Pages）](https://yong-huang.github.io/hands-on-agentic-ai/agents/20_doc_splitting/images/doc_splitting.dataflow.html)（或本地打开 [`images/doc_splitting.dataflow.html`](images/doc_splitting.dataflow.html)）。

## 3. 快速开始

```bash
cd agents/20_doc_splitting
python doc_splitting.py --demo   # 内联文本演示切分算法
python doc_splitting.py          # 加载 docs/ 目录（md + txt + pdf）
```

目录模式会加载 docs/ 下三个样例文件并打印加载与切分两份报告。**实测输出**：
3 个文件共 735 字符 → 9 个 chunk，块长 78/89/100（min/avg/max），0 个超限；
chunk #0 尾部"…重新打"与 chunk #1 开头"测试用例上重新打分"就是 overlap 衔接。

## 4. 核心概念

### 4.1 统一文档结构

| 字段 | 内容 | 用途 |
| :--- | :--- | :--- |
| source | 来源文件名 | 答案溯源 |
| type | txt / md / pdf | 调试与过滤 |
| text | 归一化后的全文 | 切分输入 |

三种格式三个加载器，一个分派函数——新增格式（html、docx）只需加一个加载器。

### 4.2 递归字符切分：语义边界优先

分隔符按优先级排队：`\n\n`（段落）→ `\n`（换行）→ `。！？；`（句子）→
空格 → 逐字符。算法对超出块上限的片段**降级**到下一级分隔符继续切——段落
放得下就不拆句子，句子放得下就不拆词。这就是 LangChain
`RecursiveCharacterTextSplitter` 的核心思想，本篇用 40 行手写。

### 4.3 overlap：撕口互相咬合

相邻块回填约 30 字符的尾部重叠。没有 overlap 时，"每次修改提示词都需要在同
一组用例上重新打**分**"这句话可能被切成两半，两半都答不全"怎么评估"。
实测 chunk #0/#1 的衔接就是 overlap 在工作。

### 4.4 真实坑：PDF 的 NFKC 归一化

Chrome 生成的 PDF 用 CID 字体，pypdf 提取出的汉字常是**兼容形式**（"⼿"
U+2F8B 而非"手" U+624B）。肉眼看着一样，检索时同一个词就是匹配不上。加载器
统一做 `unicodedata.normalize("NFKC", text)`——**归一化必须发生在切分之前**。

## 5. 代码关键部分

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

坑清单：

- 长度口径用"CJK 记 1、其余记 0.5"的近似——纯字符数会低估中文信息密度；
- overlap 太大等于变相放大块，太小防不住切断，120/30 是本实验的折中值；
- 切分前必须归一化（NFKC）与去掉 Markdown 标记符号，否则垃圾进垃圾出。

## 6. 文件结构

```
20_doc_splitting/
├── README.md                            # 本篇教程
├── doc_splitting.py                     # 主脚本（约 200 行）：加载器 + 递归切分 + 报告
├── docs/                                # 实验材料（三种格式各一份）
│   ├── rag_notes.md                     #   Markdown 学习笔记
│   ├── quick_ref.txt                    #   纯文本速查
│   └── eval_handbook.pdf                #   PDF 手册（Chrome 生成，含中文）
└── images/
    ├── doc_splitting.dataflow.json      # 图源：dataflow 类型（加载→切分管线）
    ├── doc_splitting.dataflow.html      # 交互版架构图
    └── doc_splitting.dataflow.svg       # 双主题矢量图
```

## 7. 面试要点

- **Q: 为什么 RAG 要先切分文档？块大小的权衡是什么？**
  A: 检索与注入都以 chunk 为单位。太大：一块多主题，检索带噪音；太小：上下文
  不完整。折中值靠评估实验定，不是拍脑袋。
- **Q: 递归字符切分的"递归"体现在哪？**
  A: 分隔符按语义强度排队（段落→句子→字符），超长片段降级到下一级分隔符
  递归切分，保证尽可能沿语义边界断开。
- **Q: overlap 解决什么问题？代价是什么？**
  A: 防止关键句被块边界切成两半；代价是存储与索引的少量冗余。
- **Q: 为什么 PDF 提取的文本要做 NFKC 归一化？**
  A: CID 字体常把汉字映射为兼容形式（如 U+2F8B），不归一化会导致检索匹配
  失败——肉眼看不出的 bug。
- **Q: chunk 的元数据有什么用？**
  A: 溯源（答案引用出处）、过滤（按文件/章节限定检索范围）、去重与更新。

## 8. 总结

三种格式统一加载、语义边界优先的递归切分、咬合式 overlap、块级元数据——
RAG 管线第一环完成，产出的 chunks 已经是"可索引"的形态。下一篇把它们
embedding 后灌进向量库，实现真正的相似度检索。
