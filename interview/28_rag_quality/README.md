# 28 · RAG 质量量化（Faithfulness / Relevance）

> 覆盖面试题：如何评估 RAG 的检索质量？Faithfulness 和 Relevance 怎么量化？
> 30 条文档语料，3 种 chunking（整段 / 滑窗 200 字 / 句级）各建索引：
> Relevance = 检索块与问题的 embedding 相似度均值；Faithfulness = 答案
> 逐句回溯检索证据（字面重合率）算有支撑句占比。注入幻觉句验证指标
> 能否抓出幻觉。真机：nomic 检索 + qwen3.8 生成回答（3 题 × 3 chunking）。

## 1. 运行与实测

```bash
MOCK=1 python rag_quality.py    # 离线: hash 向量 + 抽取式回答
python rag_quality.py           # 真实: nomic + qwen3.8
```

真机实测（2026-09-09）：

| chunking | 块数 | Relevance | Faithfulness |
|:--|:--:|:--:|:--:|
| whole | 30 | 0.648 | 0.44 |
| window | 30 | 0.648 | 0.44 |
| pair(句级) | 59 | **0.698** | 0.42 |

真机两个诚实的指标发现：

1. **幻觉对照未被抓出**（注入前后都 0.50）——字面重合法的双向误差：
   抽象改写的正确句被判"无支撑"（低估），含共用词的幻觉句可能过阈值。
   结论：字面重合法只适合做初筛，生产 Faithfulness 要用 NLI 或带引用
   要求的 LLM Judge。
2. 句级切块 Relevance 更高（0.698）且证据粒度精确，与"chunking 越细
   证据越准"的预期一致；Faithfulness 三者接近（qwen 回答抽象度高，
   字面支撑天然低）。

## 2. 深入要点

- 两个指标分开看：Relevance 管"检索得准不准"，Faithfulness 管
  "说得对不对"——分别归因检索问题与生成问题。
- Faithfulness 是幻觉的量化：离线注入幻觉后 1.00 → 0.50 立刻下降，
  生产上用它做线上幻觉监控，低分样本进人工复核队列。
- chunking 没有万能解：句子级证据精确、整段上下文完整，按任务误差
  代价选择，并用 Hit@k + Faithfulness 双指标驱动调参。

## 3. 文件结构

```
interview/28_rag_quality/
├── README.md            # 本篇
└── rag_quality.py       # 3 种 chunking + 双指标 + 幻觉注入对照（约 230 行）
```
