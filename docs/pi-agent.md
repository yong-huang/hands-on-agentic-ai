# 🥧 pi coding agent 源码精读与扩展 17 小项目学习清单 · Todo List（TypeScript 真机跑通 · 配置零侵入）

> 通过 17 个小项目吃透 pi（badlogic/pi-mono，npm 现为 `@earendil-works` scope）极简 agent harness 的**架构设计、代码实现与扩展机制**
> 本机 pi CLI 0.84.3 已装好且真机调用实测通过——清单**零安装、零升级、零侵入**：extension 用 `-e` 直载、skill/theme/模板用对应旗标直载、会话走 `--session-dir`，一切写入隔离在 `pi/` 学习目录，不动 `~/.pi/agent` 生产配置（orca 等扩展在用）
> 知识体系型：阶段即能力等级；全部脚本/扩展/配置累积在 `pi/` 实验目录，🏁 项目 17 组装成「我的超级 pi 发行版」
> 决策默认：TypeScript 为主（pi 原生栈）· 源码精读+扩展实战兼顾 · LLM 用本机已认证的默认 provider（离线场景由 mock provider 承担，不再依赖 Ollama）；对齐提问未及作答按推荐默认，2026-10-16 按用户要求改为「去掉安装/升级/纯配置项，配置全部隔离」
> 预计周期：3-4 周（每天 3-4 小时）

---

## 🤖 AI 辅助提示词速查

| 场景 | 提示词 |
|:---|:---|
| **开始一个新项目** | `我要开始 pi agent 项目「[名称]」，目标是 [目标]。请给我完整 TypeScript 代码约 [行数] 行，用 @earendil-works/pi-* SDK（版本与本机 pi --version 对应的源码 tag，Node 22，ESM），附验收命令。只输出代码。` |
| **读源码卡壳** | `我在读 pi-mono 仓库 [包名]/src/[文件] 这段代码：[粘贴]。请逐段解释它在 agent loop 里的角色，以及谁调用它、它调用谁。` |
| **extension 不生效** | `我的 pi extension 代码：[粘贴]，用 pi -e 直载（或 pi install -l 装在项目级 .pi/），启动后 [现象]。请按 pi extension 加载机制排查原因并给修复。` |
| **RPC 对接排障** | `我用 [语言] 宿主进程通过 stdin/stdout JSON-RPC 驱动 pi --mode rpc，收到的报错/事件流：[粘贴]。请分析消息格式哪里不符合协议并给修复。` |

---

## 📊 总进度

进度：░░░░░░░░░░░░░░░░░ 0/17 (0%)

| 阶段 | 项目数 | 已完成 |
|:---|:---:|:---:|
| 第一阶段：跑通与全景 | 2 | 0 |
| 第二阶段：pi-ai 统一 LLM 层 | 3 | 0 |
| 第三阶段：pi-agent-core 循环引擎 | 4 | 0 |
| 第四阶段：pi-coding-agent 产品层 | 4 | 0 |
| 第五阶段：端口、生态与终极串联 | 4 | 0 |
| **合计** | **17** | **0** |

---

## 🗂️ 第一阶段：跑通与全景（项目 1-2）

> **目标**：真机驾驭 pi 的全部运行形态，亲手画出七包分层架构地图

### [ ] 项目 1：四种运行模式全景跑通

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~40（探针脚本 + 笔记） |
| **核心知识点** | TUI/`-p`/`--mode json`/`--mode rpc` 四端口、session JSONL、`--session-dir` 会话隔离 |
| **技术栈** | pi CLI 0.84.3（本机已装，保持不动）、jq |
| **验收标准** | `pi -p "Reply with exactly: ok" --session-dir pi/sessions` 退出码 0；`pi -p "hi" --mode json --session-dir pi/sessions` 输出能被 `jq` 解析出 message 事件；在 `pi/sessions/`（而非默认目录）找到本次 JSONL 并列出 entry 类型清单，写进笔记 `pi/01_modes_probe/NOTES.md` |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「四种运行模式全景跑通」。本机 pi CLI 已装好（pi --version 查看，保持不动、禁止升级）。请给我一个 ~40 行的 bash 探针脚本：1) 记录当前版本；2) 依次跑默认 TUI（仅打印启动命令不进交互）、`-p` 非交互、`--mode json`、`--mode rpc`（各发一条即退）四种模式，全程加 --session-dir pi/sessions 隔离会话；3) 用 jq 从 json 模式输出提取 message 事件类型；4) 确认 JSONL 落在 pi/sessions/ 而非 ~/.pi/agent/sessions/，并列出 entry 类型分布。每步失败即退出并给排查提示。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 2：源码 clone 与七包分层架构地图

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~60（行数统计脚本）+ 1 张手绘分层图 |
| **核心知识点** | monorepo workspace、七包职责（pi-ai / pi-agent-core / pi-tui / pi-coding-agent / pi-storage-sqlite-node / pi-server / pi-evals）、lockstep 版本策略 |
| **技术栈** | git、npm workspaces、TypeScript |
| **前置** | 项目 1 |
| **⚠️ 风险** | GitHub 直连从本机实测超时过，clone 失败就加 gh-proxy 镜像前缀；build 步骤以仓库 README 为准；后续所有读源码项目均以本次 checkout 的 tag 为准 |
| **验收标准** | `git clone` 成功并 checkout 与本机 pi CLI 同版本的 tag（`pi --version` 为准，无精确 tag 则取最接近的 vX.Y.x 并在笔记记录偏差）；本地 build 出的 CLI `--version` 与 package.json 一致；`pi/02_repo_map/loc.txt` 的各包行数统计与自画分层图一致（断言：pi-ai 与 pi-tui 零内部依赖、pi-agent-core 只依赖 pi-ai、pi-coding-agent 汇聚三者、pi-server 在最顶层） |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「源码 clone 与七包分层架构地图」。请给我 ~60 行 bash+node 统计脚本：1) 先读 pi --version，git clone https://github.com/badlogic/pi-mono（失败自动改用 https://gh-proxy.com/ 前缀重试）并 checkout 对应版本 tag（无精确匹配取最接近的 vX.Y.x）；2) npm install（workspace）并 build；3) 遍历 packages/ 统计每个包的 src 行数写入 loc.txt；4) 解析各包 package.json 的 dependencies 生成内部依赖边列表，断言分层关系：pi-ai、pi-tui 无内部依赖，pi-agent-core 仅依赖 pi-ai，pi-coding-agent 依赖 ai+agent+tui，pi-server 依赖 coding-agent；5) 输出 build 产物的 --version 与 package.json 版本比对。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

## 🗂️ 第二阶段：pi-ai 统一 LLM 层（项目 3-5）

> **目标**：吃透「一次 LLM 调用」的统一抽象，获得接入任意 provider 的能力

### [ ] 项目 3：pi-ai SDK 直调：stream() 与消息/工具调用模型

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~80 |
| **核心知识点** | `stream()` 统一入口、流式增量事件、usage 统计、tool call 意图的结构化表示 |
| **技术栈** | `@earendil-works/pi-ai`（本机 CLI 同版本）、tsx（需 `npm i -g tsx`） |
| **前置** | 项目 1、2 |
| **验收标准** | `tsx pi/03_pi_ai_stream/stream.ts` 真机流式打印增量且末尾 usage 与响应一致（provider 用本机默认已认证 provider）；脚本内模拟一条带 toolCall 的 assistant 消息被解析为结构化对象（字段断言通过） |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「pi-ai SDK 直调」。请给我 ~80 行 TypeScript（ESM，tsx 直跑）：用 @earendil-works/pi-ai 的 stream() 直接发一轮流式请求（不经 pi CLI，用默认已认证 provider），逐增量打印文本，结束时打印 usage 并断言非空；再构造一条含 toolCall 内容块的 assistant 消息交给 pi-ai 解析，断言解析出的工具名与参数 JSON 正确；失败分支打印排查提示。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 4：Provider 注册表与 models.dev 模型目录

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~70 |
| **核心知识点** | provider registry 源码、子路径导出（`/anthropic`、`/openai-responses`、`/oauth`）、models.json（用户配置）与 models-store.json（目录缓存）合并机制 |
| **技术栈** | pi-ai 源码（项目 2 clone）、node 脚本 |
| **前置** | 项目 2 |
| **⚠️ 风险** | catalog 刷新（`pi update`）会写用户级 models-store.json——先备份、diff 完还原，见提示词 |
| **验收标准** | 枚举脚本输出的 provider 列表覆盖官方文档所列全部内置 provider；笔记 `pi/04_provider_registry/NOTES.md` 能回答「models.json 与 models-store.json 谁覆盖谁、catalog 何时刷新」（用一次备份→刷新→diff→还原的实验佐证，验收含还原检查） |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「Provider 注册表与模型目录」。pi-mono 源码在本地（与本机 pi 同版本 tag）。请给我 ~70 行 node 脚本 + 阅读指引：1) 读 packages/pi-ai 里 provider registry 相关源码，列出注册入口文件路径；2) 脚本 import pi-ai 枚举全部内置 provider 与各 provider 模型数，输出 TSV；3) 先 cp 备份 ~/.pi/agent/models-store.json，跑一次 pi update 刷新 catalog，diff 前后摘要说明刷新时机，然后还原备份并断言与原文件一致；4) 在笔记里用 3 句话讲清 models.json 与 models-store.json 的合并顺序。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 5：自定义 Mock Provider——离线可控的 agent loop

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~120 |
| **核心知识点** | provider 扩展点、剧本化响应（scripted response）、确定性测试 agent、`-e` 直载与项目级作用域 |
| **技术栈** | pi extension（TypeScript）、零网络 |
| **前置** | 项目 4 |
| **验收标准** | `pi -e pi/05_mock_provider/mock.ts -p "..." --provider mock --no-session` 全程断网（关 Wi-Fi 或代理指到空地址）完成一轮含工具调用的 loop，`~/.pi/agent` 无任何新增（扩展未安装、仅直载）；断言 transcript 中 toolCall → toolResult → 最终回复顺序与剧本一致 |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「自定义 Mock Provider」。请给我 ~120 行 TypeScript pi extension：注册一个名为 mock 的 provider，按剧本返回响应——第一次返回一个 read 工具的 toolCall，第二次根据 toolResult 返回最终文本；文件放 pi/05_mock_provider/mock.ts，用 pi -e 直载运行（不安装、零残留）。要求全程离线可用，作为后续项目的确定性测试底座。附验收命令（含断网验证与「~/.pi/agent 无新增」检查）。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

## 🗂️ 第三阶段：pi-agent-core 循环引擎（项目 6-9）

> **目标**：逐行读懂极简循环引擎，驾驭事件流、三条控制路径与 session 持久化

### [ ] 项目 6：agentLoop 精读与事件时序图

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~80（事件 dump 脚本）+ 1 张 turn 状态机图 |
| **核心知识点** | `agentLoop()`/`agentLoopContinue()`、隐式 ReAct while 循环、turn 执行单位、事件流（agent_start/end、turn_start/end、message_*、tool_execution_*） |
| **技术栈** | `@earendil-works/pi-agent-core`（同版本源码）、项目 5 的 mock provider |
| **前置** | 项目 2、5 |
| **验收标准** | dump 脚本跑一轮真实 loop 导出全部事件 JSON；自画时序图（`pi/06_agent_loop/timeline.md`）与导出事件序列逐一对得上（agent_start→turn_start→message_*→tool_execution_*→turn_end→agent_end） |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「agentLoop 精读与事件时序图」。请给我 ~80 行 TypeScript：用 pi-agent-core SDK + 项目 5 的 mock provider 跑一轮 loop，订阅全部事件并按时间戳写进 pi/06_agent_loop/events.json；打印事件类型序列；另附一份精读清单，列出 packages/pi-agent-core 5 个源文件各自职责与推荐阅读顺序。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 7：Steering / follow-up / abort 三条控制路径

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~120（3 个断言脚本） |
| **核心知识点** | steering 队列（turn 边界注入）、follow-up 队列（结束前注入）、AbortSignal 中断路径 |
| **技术栈** | pi-agent-core SDK、mock provider |
| **前置** | 项目 6 |
| **验收标准** | 三个行为各有断言脚本且全绿：steering 消息出现在下一个 turn 开头而非当前 turn 中间；follow-up 在 agent 即将结束时被注入执行；abort 后循环退出且 transcript 完整、可 resume 续跑 |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「Steering/follow-up/abort 三条控制路径」。请给我 3 个共 ~120 行 TypeScript 断言脚本（pi-agent-core SDK + mock provider）：1) steer.ts——loop 执行慢工具期间调用 steer()，断言消息在下一 turn 开头出现；2) followup.ts——在 agent 即将结束时调 followUp()，断言追加了一轮处理；3) abort.ts——中途 abort，断言退出且消息数组完整可续跑。每个脚本失败时打印实际事件序列帮助排障。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 8：工具执行管道精读——并行、顺序保真与钩子阻断

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~100 |
| **核心知识点** | 工具管道（registry→prepareArguments→schema 校验→beforeToolCall→execute→afterToolCall→归一化）、默认并行与 sequential 整批、结果按原始 call 顺序写回、截断 tool call 判错 |
| **技术栈** | pi-agent-core 源码 + SDK |
| **前置** | 项目 6 |
| **验收标准** | 断言脚本证明：3 个耗时 3s/1s/0.1s 的并行工具，结果仍按 call 顺序写回 transcript；任一工具标 sequential 后整批顺序执行；beforeToolCall 返回阻断后该工具未执行且 transcript 有被拒记录 |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「工具执行管道精读」。请给我 ~100 行 TypeScript：用 pi-agent-core SDK 注册 3 个自定义 sleep 工具（3s/1s/0.1s），跑一轮断言 toolResult 在 transcript 中按 call 顺序排列而非完成顺序；再演示 sequential 标志让整批顺序执行；再注册 beforeToolCall 钩子拦截其中一个工具，断言其 execute 未被调用。配合 5 条精读笔记指出管道各阶段在源码中的文件与函数名。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 9：Session JSONL 分叉树与 compaction 视图分离

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~90 |
| **核心知识点** | append-only JSONL、id/parentId 分叉树、`--fork`/`--resume`/`--continue`、compaction 只改 model view 不动 storage、durable history ≠ transcript ≠ model context |
| **技术栈** | pi CLI、node 脚本 |
| **前置** | 项目 1、6 |
| **验收标准** | 重建脚本从真实 session 文件恢复出消息树并断言每个 entry 的 parentId 都指向已存在 entry（只读已有 session，不修改）；`pi --fork` 后新旧两个 session 文件共享前缀 entry；在 `pi/sessions/` 撑长对话触发 compaction 后，磁盘上原消息 entry 仍全部存在（断言文件行数只增不减）且新增 compaction entry |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「Session 分叉树与 compaction」。请给我 ~90 行 node 脚本：1) 解析 ~/.pi/agent/sessions/ 下一个真实 JSONL（只读），按 id/parentId 重建树并断言无孤儿节点；2) 对比 pi --fork 前后两个 session 文件（fork 到 pi/sessions/），断言共享前缀；3) 在 pi/sessions/ 自动化撑长一个 session（循环 pi -c 追加长文本）直到出现 compaction entry，断言原消息 entry 未被删改且文件 append-only。附精读笔记：compaction 的 cut point 选择逻辑在源码哪处。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

## 🗂️ 第四阶段：pi-coding-agent 产品层（项目 10-13）

> **目标**：掌握产品内核的工具实现、上下文工程与扩展面，并与自研 mh/ 对照

### [ ] 项目 10：四内置工具 read/bash/edit/write 产品化细节

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~60（实验脚本）+ 对照笔记 |
| **核心知识点** | 4 工具的 prompt 描述与参数设计、输出截断阈值、edit 的 old_string 失败模式、与自研 mh/ 工具层对比 |
| **技术栈** | pi CLI、pi-mono 源码、本仓库 mh/（harness 线产物） |
| **前置** | 项目 2 |
| **验收标准** | 实测记录进 `pi/10_tools/NOTES.md`：edit old_string 不匹配的准确报错文案、bash 输出截断的实测阈值；一张「pi 4 工具 vs mh/ 工具」对照表（参数设计/截断/错误处理三列） |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「四内置工具产品化细节」。请给我 ~60 行 bash 实验：1) 用 pi -p 依次触发 read、bash、write 三个工具各一次并保留 session（--session-dir pi/sessions）；2) 故意让 edit 的 old_string 不匹配，抓取准确报错；3) 用超长输出命令实测 bash 截断阈值；4) 把上述结论整理进 NOTES.md，并对照本仓库 harness/ 的 mh/ 包同类工具给出三列差异表。附精读指引：4 个工具实现在 pi-mono 源码的哪个目录。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 11：Extension 全生命周期实战

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~150 |
| **核心知识点** | extension 加载机制（`-e` 直载 / `pi install -l` 项目级 / 用户级发现）、custom tool、slash command、beforeToolCall 阻断（guard）、tool_result 改写、事件 handler |
| **技术栈** | pi extension（TypeScript） |
| **前置** | 项目 8 |
| **验收标准** | 一个 extension 集齐 5 类 hook 且各有可观测效果（全部在 pi/ 学习目录内用 `-e` 直载或项目级作用域验证，用户级零残留）：自定义工具能被调用、`/hello` 命令有输出、`rm -rf` 类命令被 beforeToolCall 拦截、指定工具结果被追加水印、session 结束时事件 handler 打印统计 |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「Extension 全生命周期实战」。请给我 ~150 行 TypeScript pi extension（单文件或小目录均可）：1) 注册 custom tool `get_weather`（返回固定值）；2) 注册 slash command `/hello`；3) beforeToolCall 钩子拦截 bash 中含 `rm -rf` 的调用并返回友好拒绝；4) afterToolCall/read 工具结果追加 `[audited]` 水印；5) agent_end 事件打印本次 token/工具调用统计。开发期用 pi -e 直载调试，最后演示 pi install -l 装进学习目录的项目级 .pi/（不碰 ~/.pi/agent）。给出逐条人工+自动验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 12：Skills、AGENTS.md 与 SYSTEM 上下文工程

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~40（验证脚本）+ SKILL.md ×2 |
| **核心知识点** | SKILL.md metadata 懒加载（启动只进 system prompt 元数据，read 时才载全文）、`--skill` 直载与 `/skill:name`、AGENTS.md/CLAUDE.md 发现链（global/parent/cwd）、`.pi/SYSTEM.md` 与 `--append-system-prompt` |
| **技术栈** | pi CLI |
| **前置** | 项目 11 |
| **验收标准** | dump system prompt 证明：`--skill` 直载的 skill 只以 metadata 在场、AGENTS.md 全文包在 `<project_context>` 中；把 AGENTS.md 放在 pi/ 学习目录的父目录仍被发现（parent 级断言；global 级只读复用已有文件，不新建用户级文件）；`/skill:name` 能展开全文 |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「Skills 与 AGENTS.md 上下文工程」。请给我：1) 两个不同 frontmatter 的 SKILL.md 示例（一个 trigger 型一个命令型），用 pi --skill 直载；2) pi/ 学习目录与其父目录两级的 AGENTS.md（不写任何用户级/global 文件）；3) .pi/SYSTEM.md 定制样例（项目级）；4) ~40 行验证脚本：用 pi 的 debug/json 能力 dump 实际 system prompt，断言 skill metadata 在场而全文不在场、`<project_context>` 包住 AGENTS.md、父目录 AGENTS.md 被发现。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 13：主题、模板与扩展分发链

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~50（审阅笔记 + 配置） |
| **核心知识点** | `--theme`/`--use-theme` 主题直载、`--prompt-template` 模板直载、`pi install/remove/list/config/update` 分发链与项目级作用域、project trust 与本地配置加载边界（pi 不是 sandbox） |
| **技术栈** | pi CLI、社区 extension 1 个 |
| **前置** | 项目 11 |
| **⚠️ 风险** | 社区 extension 质量参差，安装前先读源码；统一装进 pi/ 学习目录的项目级作用域（`pi install -l`），不碰用户级；trust 只管配置加载，安全隔离需外部容器/VM（写进笔记） |
| **验收标准** | 在学习目录内 `pi list` 显示项目级安装的 extension 及来源；`--use-theme` 切换后 TUI 生效（配置 diff 佐证，零用户级写入）；一个 `--prompt-template` 直载的模板可复用展开；社区 extension 的每个 hook 调用点都标注在项目 6 的生命周期图副本上 |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「主题、模板与扩展分发链」。请给我 ~50 行内容：1) 从 pi 官方 extension 示例/社区里挑一个 star 较高的 extension，先给出源码审阅要点清单，再用 pi install -l 装进学习目录项目级作用域；2) 用 --theme/--use-theme 演示主题切换、--prompt-template 演示模板展开（全部旗标直载或项目级，不写用户级配置）；3) 验证 pi list/config 在项目级作用域下的表现；4) 笔记说明 project trust 的真实边界（为什么说 pi 默认继承用户权限、不是 sandbox）。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

## 🗂️ 第五阶段：端口、生态与终极串联（项目 14-17）

> **目标**：把 pi 当组件嵌进自己的系统，交付个人发行版

### [ ] 项目 14：RPC 模式——外部进程驱动 pi

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~130 |
| **核心知识点** | `--mode rpc` stdin/stdout JSON-RPC 协议、四端口共享同一 AgentSession、宿主进程事件流消费 |
| **技术栈** | TypeScript 或 Python 宿主、pi CLI |
| **前置** | 项目 6 |
| **验收标准** | 宿主进程通过 RPC 连发 3 条 prompt（`--session-dir pi/sessions` 隔离），收齐全部 turn/tool 事件并渲染最终回复；断言收到的事件类型序列与项目 6 时序图同构（同一断言函数复用） |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「RPC 模式外部驱动」。请给我 ~130 行 TypeScript 宿主程序：spawn `pi --mode rpc --no-session`，实现 initialize 握手、连续发送 3 条 user prompt、按协议消费全部事件流、打印最终 assistant 文本；把收到的事件类型序列与 pi/06_agent_loop/events.json 的类型序列做同构断言。附协议要点笔记（消息帧格式、id 关联）。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] ⛓️ 项目 15：pi-server 常驻架构（选做攻坚）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~80 |
| **核心知识点** | supervisor + RPC 子进程 + IPC/HTTP、多客户端共享 agent、常驻服务化 |
| **技术栈** | `@earendil-works/pi-server`（实验性） |
| **前置** | 项目 14 |
| **⚠️ 风险** | pi-server 为实验性包（npm 独立版本线），API 可能变动；跑不通则降级为「RPC 模式 + pm2/launchd 自建常驻 wrapper」，学习目标不变 |
| **验收标准** | server 启动后两个独立客户端进程同时驱动同一 agent session 且互相可见对方消息（断言第二个客户端能读到第一条消息的回复） |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「pi-server 常驻架构」。请给我 ~80 行内容：1) 启动 @earendil-works/pi-server 并弄清其 supervisor/RPC 子进程/IPC-HTTP 三件套的端口与协议（以本地源码为准）；2) 两个最小客户端脚本并发连接，客户端 B 断言能读到客户端 A 的对话内容；3) 若 API 与文档不符，给出自建常驻 wrapper 的降级方案骨架。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 项目 16：评测机制与贡献上游（选做）

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~40 |
| **核心知识点** | pi-evals 私有评测 harness 的组织方式、LLM agent 评测思路（对照 aitest 线）、开源贡献流程（issue/PR） |
| **技术栈** | git、GitHub |
| **前置** | 项目 2 |
| **⚠️ 风险** | pi-evals 不发布，只能读源码；贡献上游依赖 GitHub 可达（备选镜像只解决 clone，PR 需直连或另想办法），失败则降级为在本地 fork 上模拟完整 PR 流程 |
| **验收标准** | 产出物二选一：merged/open 状态的 PR 或 issue 链接；或本地 fork 上完成一次「branch→commit→PR 描述→self-review」的全流程演练记录 |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「评测机制与贡献上游」。请给我 ~40 行内容：1) 精读 pi-mono 里 pi-evals 包的评测用例组织方式，写半页笔记对照 aitest 线的 eval 思路异同；2) 在使用中发现一个真实的文档/类型/小 bug，给出标准 issue 模板与修复 PR 的完整 diff；3) 若 GitHub 直连不可用，给本地 fork 演练流程。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

### [ ] 🏁 项目 17：终极串联「我的超级 pi 发行版」

| 项目信息 | 详情 |
|:---|:---|
| **行数** | ~200（install.sh + 配置集 + README） |
| **核心知识点** | 全部扩展点组装：custom provider、mock provider、extension 五类 hook、skills、AGENTS.md 模板、RPC 驱动、一键 bootstrap、零侵入安装 |
| **技术栈** | 前面 16 个项目的全部产出 |
| **前置** | 项目 5、11、12、14 |
| **验收标准** | 在一个空目录（模拟新机器）跑 `pi/17_distro/install.sh` 一条命令拉起全部配置（全部走项目级作用域与旗标直载，不写 `~/.pi/agent`）；随后在该目录 `pi -p` 真机完成端到端编码任务（新建文件→故意埋 bug→让 pi 修复→跑测试通过），全程 guard 生效；验收含 `~/.pi/agent` 结构性文件（models.json/extensions/skills/settings.json）前后快照 diff 为空的断言（auth.json 时间戳类变化豁免） |

**🤖 开始提示词**：
> `我要开始 pi agent 项目「我的超级 pi 发行版」。请给我 ~200 行的 pi/17_distro/：install.sh（幂等：在目标目录写项目级 .pi/ 配置——pi install -l 装项目 5 mock provider 与项目 11 guard extension、--skill/--prompt-template/--theme 直载清单、AGENTS.md 模板；自检 pi --version 与 provider 连通性；全程不写 ~/.pi/agent）+ smoke.sh（端到端：mkdir 任务目录→让 pi 写一个带 bug 的 fizzbuzz→让 pi 自己修复→node 跑通→断言 guard 在全程生效→diff ~/.pi/agent 结构性文件快照确认为空变化）+ README 说明每件产出来自哪个项目。附验收命令。只输出代码。`

**完成日期**：________
**踩坑记录**：________

---

## 📅 周计划

| 周次 | 内容 | 项目数 |
|:---|:---|:---:|
| **第 1 周** | 项目 1-5（跑通与全景 + pi-ai 统一 LLM 层） | 5 |
| **第 2 周** | 项目 6-9（pi-agent-core 循环引擎） | 4 |
| **第 3 周** | 项目 10-13（pi-coding-agent 产品层） | 4 |
| **第 4 周** | 项目 14-17（端口、生态与终极串联） | 4 |

## 🏆 里程碑

- [ ] **完成项目 1-2** → pi 驾驭者：四种运行模式 + 七包分层地图
- [ ] **完成项目 3-5** → LLM 抽象拆解者：provider 机制吃透，离线 mock 可控
- [ ] **完成项目 6-9** → 循环引擎读码人：事件流、控制路径、session 树全吃透
- [ ] **完成项目 10-13** → 产品内核扩展者：工具、上下文工程、extension 全链路
- [ ] **完成项目 14-17** → pi 魔改者：外部系统集成 + 个人发行版交付

## 📝 每日日志

| 日期 | 项目 | 耗时 | 收获 | 踩坑 |
|:---|:---|:---:|:---|:---|
| | | | | |

## 🔧 环境配置

```bash
# 0. 已就绪（2026-10-16 实测，零安装零升级，pi 保持 0.84.3 不动）
#    pi CLI 0.84.3 全局（真机调用实测返回 ok，官方 provider 已认证）
#    Node v22.23.2 / npm 10.9.8 / pnpm（homebrew）
#    ~/.pi/agent/ 为生产配置（orca 扩展等在用）：学习期只读、不写入

# 1. 需安装（随项目触发，勿提前全装）
npm i -g tsx                                # 项目 3 起：TS 脚本直跑
git clone https://github.com/badlogic/pi-mono   # 项目 2（超时则加 https://gh-proxy.com/ 前缀）

# 2. 隔离原则（每项目通用，2026-10-16 起生效）
#    a) 跑 pi 统一加 --session-dir pi/sessions（或 --no-session），不污染默认会话目录
#    b) extension 用 pi -e <path> 直载；skill/theme/模板用 --skill/--theme/--prompt-template 直载
#    c) 验证安装/发现链时用 pi install -l 装进 pi/ 学习目录的项目级 .pi/，禁止装入用户级
#    d) 确需临时动用户级文件（如项目 4 刷新 catalog）：先备份、后还原、验收含还原检查

# 3. 每项目开工前
pi --version && echo "env ok"
```

## ⚠️ 与已有清单的关系

| 已有清单 | 关系 |
|:---|:---|
| docs/harness.md（自研 mh/，18/18 完成） | **最强相关·互补印证**：harness 线「亲手造」，本线「读懂生产级 + 学会扩」。项目 10 显式对比 pi 4 工具与 mh/ 工具层；项目 6/8/9 的 loop/管道/session 概念在 mh/ 里都有自己造过的对应物，读 pi 时可「对照复习」 |
| docs/agent.md（LangChain 视角，24/24 完成） | 视角互补：agent.md 回答「从零会做」，本线回答「真实产品怎么实现」。agents/05_agent_loop、08_session_persist、11_error_handling 与 pi 的 agentLoop/session/tool pipeline 一一对应，可跳过本线中已熟概念的通识部分 |
| docs/aitest.md / langchain.md / qa.md | 无直接重叠，无需衔接 |

## 📚 来源（2026-10-16 调研）

- [badlogic/pi-mono · GitHub](https://github.com/badlogic/pi-mono)（官方仓库，npm 已迁移 `@earendil-works` scope）
- [pi.dev](https://pi.dev)（官网：minimal agent harness）
- [What I learned building an opinionated and minimal coding agent · Mario Zechner，2025-11-30](https://mariozechner.at/posts/2025-11-30-pi-coding-agent)（作者亲述设计哲学）
- [Pi: The Minimal Agent · Armin Ronacher，2026-01-31](https://lucumr.pocoo.org/2026/1/31/pi)
- [Building Pi, and what makes self-modifying software so compelling · Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/building-pi-and-what-makes-self-modifying)（访谈：OpenClaw 底座、自修改软件）
- [pi 的设计艺术：构建生产级 Coding Agent 的架构决策 · pi-book ch02](https://zhanghandong.github.io/pi-book/ch02-packages.html)（七包分层与包划分原则）
- [Pi Agent：用最小 Harness 看懂真实 Agent 架构 · pinktalk](https://pinktalk.online/computer_sci/llm/agent/pi_agent_architecture)（loop/工具管道/事件流/session/扩展机制详解）
- [下一代 Agent 架构——Pi Agent Core 设计逻辑深度解析 · 知乎](https://zhuanlan.zhihu.com/p/2004665077618458930)（三层嵌套生命周期）
- [@earendil-works/pi-coding-agent · npm](https://www.npmjs.com/package/@earendil-works/pi-coding-agent)（npm 最新 1.2.0，本机保持 0.84.3）

## ✅ 实测状态速查（2026-10-16）

| 能力 | 计划 | 实测结论 |
|:---|:---|:---|
| pi CLI 真机调用（默认 provider） | 项目 1 | ✅ 实测通过：`pi -p` 返回 ok，exit 0（0.84.3，清单不升级） |
| 零侵入能力：`-e` 直载 / `--skill` / `--theme` / `--prompt-template` / `--session-dir` | 全线隔离 | ✅ 实测确认：全部旗标在本机 0.84.3 的 help 中逐一到场 |
| `pi install -l` 项目级作用域 | 项目 11/13/17 | ✅ 实测确认：`-l, --local  Install project-locally (.pi/settings.json)` |
| Node/pnpm 工具链 | 全线 | ✅ 实测通过：Node v22.23.2、npm 10.9.8、pnpm 在位 |
| 源码 tag 对齐（checkout 本机同版本） | 项目 2 | ⚠️ 待验证（tag 命名规则以 clone 后 `git tag` 实查为准） |
| GitHub 直连 | 项目 2/16 | ❌ WebFetch 直连实测超时 → clone 走 gh-proxy 镜像（⚠️ 待验证）；PR 需直连，项目 16 已备本地 fork 降级 |
| models.json / models-store.json 合并机制 | 项目 4 | ⚠️ 待验证（刷新 catalog 需临时动用户级文件，已写明备份→还原流程） |
| pi-server 常驻 | 项目 15 | ⚠️ 待验证（实验性包，已备 RPC wrapper 降级方案） |
| Ollama 本地模型 | 已移除 | ✅ 在跑（qwen3:4b）但清单不再依赖；离线需求由项目 5 mock provider 承担 |
