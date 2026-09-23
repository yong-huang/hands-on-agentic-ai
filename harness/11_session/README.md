# 11 · 会话持久化与崩溃恢复：kill -9 之后的断点续跑

> 任务进行到第 6/8 个目录时进程被 `kill -9`——恢复后 agent 拿着 13 条消息
> 历史继续跑 6 轮补齐 d7/d8，**d1-d6 的文件 mtime 分毫未动**（没有重复
> 执行）。`mh/session.py` 三件套：原子快照（tmp+rename）、悬空尾部裁剪、
> manifest 跳过重放。这是 qa/31 的进阶版：恢复的不是问答记录，是
> **带工具副作用的完整 agent 会话**。

## What

会话持久化 = 运行中持续快照、失败时从精确断点恢复。Phase A 运行中每轮
原子快照（消息历史 + 已成功命令清单 manifest）；kill -9 只杀进程，
checkpoint 完好；Phase B 恢复分三步——裁掉悬空尾部、manifest 比对跳过
重放、注入历史继续。

心智模型一句话：**恢复的可信度不取决于消息历史，取决于副作用清单。**

## Why

长任务跑 40 分钟，第 39 分钟断电，一切从零？Salesforce 把这叫"AI 失忆"
问题，解法是生命周期管理：运行中持续快照、失败时从精确断点恢复。本篇的
关键升级在于**副作用感知**：消息历史好恢复，但"哪些命令已经执行过"才是
恢复安全的前提——不解决它，恢复等于把 `mkdir`、写文件全部重放一遍。

## How

```bash
cd harness/11_session
python3 demo.py    # 完整流程: 启动 worker → 13s 后 kill -9 → resume → 五断言
```

真机实测：

```text
Phase A: 崩溃前 13 条消息, 6 条已成功命令, 已建 6/8 个目录
Phase B: 跳过重放直调探针 ✅ | resume 循环继续 6 轮
验收 ①②③④⑤ 全绿:
  ② 崩溃前 6 个 f.txt 的 mtime 全部未变 ✅
  ③ 8 个目录最终全部建成 ✅
  ④ 恢复事件留档 {turns_restored:13, commands_restored:6} ✅
最终回答: 任务完成：已串行创建 d1 到 d8 共 8 个目录……
```

实现代码：

```python
SessionStore(path)            # load 时自动记录 recovery 事件(审计线)
record_chat_fn(chat_fn, store)     # 每轮 LLM 调用后快照
snapshotting_tools(tools, store)   # 成功命令即时入 manifest
skip_redo_tools(tools, store)      # 恢复态: manifest 内命令拒绝重放
store.resume_messages()            # 裁悬空尾部
```

loop 侧唯一改动：`run_agent(..., messages=None)` 新增可选参数——传入历史
即为恢复会话。**加法扩展**，04 以来的所有 demo 全部照常（本篇跑批前
回归过）。

## Deep Dive

**manifest：副作用清单是恢复的安全带。**每个成功命令即时落盘（`flush()`），
恢复时两点用处：① 包装层直接拒绝重放（"已恢复·跳过重放"），mtime 分毫
未动是铁证；② 模型侧即使想重做也会被拦。诚实边界：跳过判定基于**命令
文本相同**——生产要用"效果哈希"（目标文件内容指纹）判定，本篇是演示级。

**原子写：kill -9 打不断一致性。**快照用 `write(tmp)` + `os.replace()`——
任何时刻被杀，磁盘上要么是旧完整版本要么是新完整版本，永远不会是半截
JSON。这是单文件事务的标准姿势。

踩坑清单：

- **悬空尾部：崩溃最阴险的遗产**：第一版恢复后模型输出**全空**。重放
  checkpoint 发现：崩溃正好卡在 `assistant(带 tool_calls)` 与 `tool(结果)`
  之间——恢复后模型看到一条"悬空的工具调用"，协议错乱、不知所措。解法：
  `resume_messages()` 裁掉所有尾部带 tool_calls 的 assistant 消息——**那个
  调用没执行过，协议上它就不该存在**；副作用真伪以 manifest 为准。

## Q&A

**Q1: 为什么跳过重放不基于"文件已存在"？**

`f.txt 存在`可能是别的进程建的、内容可能是错的。manifest 记录的是
"**本会话确实执行过这条命令且成功**"，因果明确。效果哈希（内容指纹）是
生产级加强。

**Q2: 为什么快照在 chat_fn 出口而不是每条消息？**

快照点是"完整轮次边界"，此处消息历史处于协议一致态；在 assistant/tool
之间快照正是悬空尾部的来源——但崩溃仍可能卡在任何位置，所以裁剪仍是
必需的双重保险。

**Q3: HANDOFF（09）和 checkpoint（本篇）什么关系？**

HANDOFF 是"时间不够"时给**人**的交接摘要；checkpoint 是"电没了"时给
**程序**的完整状态。一个有损、一个无损。

**Q4: 与 12 记忆的分界？**

本篇恢复的是"这个任务的进度"；12 恢复的是"跨任务的世界观"。粒度不同，
载体不同（checkpoint.json vs MEMORY.md）。
