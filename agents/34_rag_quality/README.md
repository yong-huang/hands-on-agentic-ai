# 34 · RAG 质量量化：Faithfulness / Relevance + chunking 对照

> 六文档小语料上三种 chunking 策略（固定长度 / 递归字符 / 段落感知）对照
> 实验：Relevance（检索块与查询相关度）+ Faithfulness（答案句子是否有检索
> 证据支撑）双指标打分。

## What

两个指标分开归因：

- **Faithfulness**：答案逐句回溯，句子有检索证据支撑的占比——低分即幻觉
  信号，可做线上监控；
- **Relevance**：检索块与查询的相关度（embedding 相似度近似）——低分先查
  chunking 与召回，不要急着改提示词。

chunking 三策略：固定长度（简单粗暴）/ 递归字符（段落→句子逐级回退）/
段落感知（语义边界优先）。

心智模型一句话：**先分桶（检索 vs 生成）再动手——两个指标就是分桶依据。**

## Why

"RAG 效果不好"没法修——不知道是检索的问题还是生成的问题。拆成两个指标
才能归因：**Relevance 低 → 修检索**（chunking/嵌入/召回）；**Faithfulness
低 → 修生成**（提示词约束/引用要求/幻觉检测）。

## How

```bash
cd agents/34_rag_quality
python rag_quality.py --demo   # 离线: 规则评分
python rag_quality.py          # 真实: LLM 生成回答后评分
```

离线实测（6 文档 / 6 查询）：三种 chunking 的 Relevance 均 0.25、
Faithfulness 均 1.00——小语料上区分度有限，实验的价值在于**指标管线
本身**（切分→检索→生成→双指标打分）。结论口径：递归字符切分在语义边界
保留与 overlap 衔接上最均衡，是生产默认。真机对照（大语料、LLM 回答）见
[qa/28](../../qa/28_rag_quality/README.md)——那里有句级切块 Relevance
0.698 更优与字面重合法双向误差的深度分析。

## Deep Dive

**指标的局限**：Faithfulness 用字面重合实现时对"改写正确句"会误判、对
"含共用词的幻觉句"会漏判（qa/28 有实测数据）——生产用 NLI 或引用式
LLM Judge。

踩坑清单：

- chunking 没有万能解：粒度、边界、overlap 三参数用双指标驱动调优；
- 小语料上指标区分度有限——评估管线先搭好，语料上量后才有结论。

## Q&A

**Q1: "RAG 效果差怎么排查"？**

先分桶再动手：Relevance 低修检索侧（chunking/嵌入/召回），Faithfulness
低修生成侧（约束/引用/幻觉检测）——两个指标就是分桶依据。
