# langchain · LangChain / LangGraph 框架深度实验

> 本线是 [docs/langchain.md](../docs/langchain.md) 学习清单的动手实现：直击
> LangChain 1.x / LangGraph 1.x **框架内核**（LCEL、结构化输出、create_agent、
> Middleware、状态图、持久化、中断、流式等），不重复
> [agents](../agents/README.md) 线已覆盖的入门用法。
> 每个实验：**六段式 README 教程 + 主脚本 + 图三件套**，全部在本机
> （Ollama + `qwen3.8:latest`，零云依赖、零 API Key）真机验证并带自断言验收。
> 当前进度：四阶段 12/12 全部完成 ✅；规划文档见 [docs/langchain.md](../docs/langchain.md)。

## 环境要求

依赖装在仓库根 `.venv`（版本清单与安装命令见
[docs/langchain.md](../docs/langchain.md) 的「环境配置」节）；真机实验需要本机
Ollama 已启动并拉取 `qwen3.8:latest`：

```bash
curl -sf http://localhost:11434/v1/models >/dev/null || ollama serve
```

01-04 与 07/08 自带 `--demo` 离线模式（假模型，无 Ollama 也能跑通结构断言）；
05/06 是纯离线实验（无模型调用），直接运行即是离线模式。

## 实验列表

### 第一阶段 · LangChain 1.x API 体系（4/4 ✅）

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 01 | [lcel](01_lcel/README.md) | LCEL 与 Runnable 协议：一条链，三种调用方式 |
| ✅ 02 | [messages_structured](02_messages_structured/README.md) | 消息/模板/结构化输出：坏 JSON 回炉重试 |
| ✅ 03 | [create_agent](03_create_agent/README.md) | create_agent 内核：工具契约与 Agent Loop |
| ✅ 04 | [middleware](04_middleware/README.md) | Middleware 钩子：拦截、限次、重试 |

### 第二阶段 · LangGraph 编排内核（4/4 ✅）

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 05 | [state_graph](05_state_graph/README.md) | StateGraph 三件套：Reducer 合并、条件边循环（纯离线） |
| ✅ 06 | [checkpointer](06_checkpointer/README.md) | Checkpointer：SIGKILL 崩溃恢复 + 时间旅行（纯离线） |
| ✅ 07 | [interrupt_hitl](07_interrupt_hitl/README.md) | interrupt/HITL：节点级闸门 + 工具级审批三决策 |
| ✅ 08 | [streaming](08_streaming/README.md) | 流式四模式 values/updates/messages/custom + 事件流 |

### 第三阶段 · 编排原语与 Agentic RAG（2/2 ✅）

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 09 | [orchestration](09_orchestration/README.md) | Send 动态扇出 + Command 监督者路由与 handoff（纯离线） |
| ✅ 10 | [agentic_rag](10_agentic_rag/README.md) | 检索 + 评分回炉 + 拒答（真机） |

### 第四阶段 · 可观测、评测与部署（2/2 ✅）

| 编号 | 实验 | 一句话主题 |
| :--- | :--- | :--- |
| ✅ 11 | [callbacks_trace](11_callbacks_trace/README.md) | 回调追踪 run tree 落盘 + 两版提示词轻评测（真机） |
| ✅ 🏁 12 | [dev_server](12_dev_server/README.md) | langgraph dev + SDK 总装：检索/HITL/追踪三合一服务（真机） |

## 每个实验怎么用

结构与其他线一致：

```
langchain/NN_xxx/
├── README.md          # 教程：六段式 + 一节一图（交互版链接）
├── xxxx.py            # 主脚本 = 学习重点，末尾附可执行验收断言
└── images/            # 图三件套
    ├── xxx.<type>.json  # 图源（Typed JSON，可 diff、可复现）
    ├── xxx.html         # 交互版（自包含单文件：缩放/聚焦/路径追踪）
    └── xxx.svg          # 双主题矢量图（跟随系统深浅色，README 内嵌）
```

脚本约定：真机模式直接跑（默认 `qwen3.8:latest`，可用 `LLM_MODEL` 环境变量
切换）；`--demo` 离线；末尾打印 `验收: N/N 通过` 并以退出码报告结果
（0 通过 / 1 断言失败 / 2 Ollama 未启动）。

## 已在真实环境验证过的事

- 十二个实验全部真机（或纯离线确定性）跑通并复测：01（6/6）、02（7/7）、
  03（7/7，3 连跑）、04（13/13，3 连跑）、05（5/5，纯离线）、06（6/6，纯
  离线含真 SIGKILL 崩溃恢复，3 连跑）、07（8/8，3 连跑）、08（7/7，3 连跑）、
  09（9/9，纯离线确定性）、10（6/6，3 连跑）、11（6/6，3 连跑数值全同）、
  12（7/7，修复残留重放后连跑验证）；01/02/03/04/07/08 的 `--demo` 离线模式
  分别为 6/6、7/7、5/5、3/3、4/4、4/4（01 另做 10 连跑稳定性复测）；
  05/06/09 纯离线直接运行。
- 实测沉淀的关键事实：工具调用类实验必须用 `qwen3.8:latest` 且
  `reasoning=False`（`qwen3:4b` 实测不触发工具调用）；`create_agent` 底层
  ToolNode 对工具异常默认**原样抛出**；检查点由后台线程异步落盘，硬崩溃会丢
  最近快照（"至少一次"语义）；SqliteSaver 的连接必须
  `check_same_thread=False`；流式四模式可单用也可传列表并用；langgraph dev
  拒绝自备 checkpointer（平台接管持久化），且 `.langgraph_api/` 残留任务会
  在下次启动重放（脚本启动前清理）；nomic-embed-text 中文短检索偏弱，靠
  评分回炉 + 拒答兜底。
- 十二张图（architecture/sequence/workflow）全部通过 showcase 级九项校验、
  多视口浏览器零溢出检查，并按像素实测做居中校正（细节见各 README 图注）。
