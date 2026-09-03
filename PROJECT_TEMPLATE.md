# hands-on-XXX 项目模版（复刻指南 / 生成提示词）

> 用途：把 `hands-on-kubernetes` 的设计与结构泛化成模版，用于复刻其它领域的
> hands-on 系列项目（如 hands-on-fintech、hands-on-llm、hands-on-rust 等）。
> 既可以作为人类开发者的规范文档，也可以整篇作为提示词交给 AI 生成新项目。
> 使用时把全文中的 `{{DOMAIN}}` 替换为目标领域，`{{TOOLCHAIN}}` 替换为该领域
> 的核心工具链（如 K8s 之于本模版的 kind/kubectl）。

---

## 一、项目哲学（决定所有设计的四条原则）

1. **每个实验必须真实可执行**。这是整个系列的灵魂：读者 clone 下来、装好前置
   工具、按顺序跑脚本，就应该能在自己的机器上看到与文档描述一致的输出。
   不写"伪代码实验"、不写"原则上可以跑"的步骤。凡是在当前环境无法完整演示
   的行为（如某功能依赖云厂商驱动），要在 README 里**诚实标注预期结果**
   （"在本环境它会一直 Pending，这正是教学点"），而不是假装成功。

2. **脚本即学习重点**。每个实验的核心是一个分步演示脚本（`xxx.sh`），它把
   该主题的完整生命周期（创建→观察→破坏→验证→清理）串成可重复执行的步骤。
   读者逐行读脚本就是在学这个主题。脚本不是辅助材料，是主教材。

3. **每个实验四件套、结构完全一致**。读者做完第 1 个实验后，就知道其余
   实验的目录里有什么、怎么跑、去哪读原理。结构的一致性本身就是学习成本的
   降低。

4. **原理与实操分离但同处一地**。README 讲"为什么"（概念、机制、易错点），
   manifests 讲"声明什么"，脚本讲"怎么做"，架构图讲"长什么样"。四种视角
   互相印证，但都放在同一个实验目录内，不做跨目录跳转。

---

## 二、仓库整体结构

```
hands-on-{{DOMAIN}}/
├── README.md                # 系列总目录：简介、环境要求、实验列表、学习路线
├── LICENSE                  # MIT（开源必备）
├── .gitignore               # .DS_Store / __pycache__ / 构建产物 / 工具会话文件
├── PROJECT_TEMPLATE.md      # 本模版（可选，复刻下一代项目用）
├── scripts/
│   └── load_resources.sh    # 公共脚本：解决国内网络/镜像源等环境问题（按需）
└── labs/                    # 所有实验，编号 + 主题命名
    ├── 00_setup_tools/      #   工具安装（轻量，只装工具不初始化环境）
    ├── 01_setup_env/        #   环境初始化（创建后续所有实验依赖的沙箱环境）
    ├── 02_topic_a/          #   每个实验一个目录，结构见下节
    ├── ...
    └── NN_topic_z/
```

### 命名与编号约定

- 实验目录：`NN_short_name/`（两位数字 + 下划线 + 小写主题名，如 `09_hpa`、
  `22_secrets_vault`）。编号决定学习顺序，**插入新实验只能追加到末尾或整体重排**，
  不要在中间挖号。
- 主脚本与实验同名的短名：`labs/09_hpa/hpa.sh`。
- 总 README 的实验列表用表格：编号 | 实验名（链接到该实验 README）| 一句话主题。

### 学习路线设计（决定实验排序）

把 25~35 个实验分成 4~6 个阶段，总 README 里明确标出，例如 K8s 版：
基础（工作负载/网络/配置）→ 进阶（调度/网络策略/服务网格）→ 专项（存储/安全/
可观测性）→ 平台工程（包管理/GitOps/扩展开发）。排序原则：

1. 最小可运行单元最先（如 Pod）；
2. 每个实验只引入一个新概念层；
3. 后面实验可以复用前面实验建的资源，但**清理要干净**（不依赖残留状态）；
4. 依赖外部重型组件的实验（服务网格、Operator）放在后段。

---

## 三、单个实验的目录结构（四件套）

```
labs/NN_xxx/
├── README.md          # 教程文档（GitHub 直接渲染，内嵌双主题 SVG 架构图）
├── xxx.sh             # 主演示脚本 —— 学习重点，放在实验根目录
├── manifests/         # 声明式配置（K8s YAML / 配置文件 / chart 等）
│   └── ...
└── images/            # 架构图三件套（Archify 生成），每张图 1~2 组：
    ├── xxx.architecture.json  # 图源：Typed JSON IR（人工/AI 编写、可 diff）
    ├── xxx.html               # 交付的交互版：自包含单文件，缩放/聚焦/路径追踪
    └── xxx.svg                # 双主题矢量版：README 内嵌，跟随系统深浅色
```

图源类型按内容选择五种之一：`architecture`（组件/边界）、`workflow`
（流程/泳道）、`sequence`（调用时序）、`dataflow`（数据管线）、`lifecycle`
（状态机）。每个实验 1~2 张，一节一图，不凑数。

例外情况：

- 实验有**多个平行的声明文件**或**真实代码**（如自定义 controller 的 `.py`），
  代码放实验根、声明文件进 `manifests/`；
- 纯工具安装类实验（00）可以只有 README + 脚本，没有 manifests/images；
- 多文档 YAML 需要分步 apply 时，给每个文档打 `tier` 标签
  （`tier=app` / `tier=policy` / ...），脚本用 `kubectl apply -l tier=x` 分阶段
  创建——这是"分步演示"的关键手法。

### 各文件的设计规范

#### README.md（教程文档）

统一的章节结构（编号到二级标题；标题措辞可调，顺序不变）：

```markdown
# NN · 主题名：一句话副标题

> 引言 blockquote：从上一实验的痛点切入，3~4 行说清本篇解决什么

## 1. 为什么需要它
   （2~4 段，讲清楚概念解决什么问题）

## 2. 总览：核心机制一图看懂
   ![总览图](images/xxx.svg)
   （内嵌双主题 SVG + 一段"怎么看这张图"+ 心智模型一句话 +
    🌐 交互版链接：GitHub Pages 在线 / 本地打开 images/xxx.html）

## 3. 快速开始
   （./xxx.sh 的分步用法，每步一行注释说明在看什么）

## 4. 核心概念
   （2~5 个小节，每节一个机制，关键的配专属图；多用表格与对比；
    术语首次出现给英文原文；"易错点"单独成段）

## 5. YAML 关键字段
   （带"为什么"注释的代码块 + 易踩的坑清单）

## 6. 文件结构
   （目录树：README / 脚本 / manifests/ / images/ 三件套，逐文件注释）

## 7. 面试要点
   （4~5 个问答式考点）

## 8. 总结
   （3~5 句话收束主线 + 一句"下一篇"引导）
```

写作风格约定：

- 中文正文，命令/字段/术语保留英文；
- **一节一图**：图内嵌在讲它的那一节，不集中堆在文末；每张图配
  "怎么看"的两三句话；
- 每个结论都给出验证方法（"你可以用 `xxx` 命令亲眼看到"）；
- 敢写"这不是故障，是预期行为"——诚实预期是这个系列的特色；
- 长度 80~150 行，超过就拆成两个实验。

#### 主演示脚本 xxx.sh

统一的骨架（所有实验完全一致，只换内容）：

```bash
#!/usr/bin/env bash
# =============================================================================
# {{实验标题}} 演示脚本
# 覆盖: 步骤1 -> 步骤2 -> ... （与 README 实操章节一一对应）
# 用法: ./xxx.sh [step]     不带参数依次执行全部; 传 step 名只执行该步骤
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"        # 统一切到实验根目录, manifests/ 相对路径生效

# ---------- 全局配置（演示用的名字/标签/版本集中在此）----------
NS="demo-xxx"
MANIFEST="manifests/xxx.yaml"

step() { echo; echo "=====> [$1] $2"; }   # 步骤标题打印

# ---------- Step 1: xxx ----------
do_apply()   { step "apply" "..."; kubectl apply -f "${MANIFEST}"; ... }

# ---------- Step 2: xxx ----------
do_observe() { step "observe" "..."; ... }

# ---------- ... 按需增加, 每个函数一个可独立执行的步骤 ----------

# ---------- 清理（必须最后有, 且删干净本实验创建的一切）----------
do_clean()   { step "clean" "删除本演示创建的所有资源"; kubectl delete -f ... ; }

# ---------- 入口: 按参数分发 ----------
main() {
    local target="${1:-all}"
    case "${target}" in
        apply)   do_apply ;;
        observe) do_observe ;;
        clean)   do_clean ;;
        all)     do_apply; do_observe; do_clean ;;
        *) echo "未知步骤: ${target}" >&2; echo "可用: apply | observe | clean | all" >&2; exit 1 ;;
    esac
}
main "$@"
```

脚本质量线：

- `set -euo pipefail`；命令失败要让脚本停而不是静默继续；
- 等待资源就绪用 `kubectl wait` / `rollout status` 带 timeout，不裸 sleep；
- 每条命令上有简短中文注释说明"这一步在看什么"；
- 演示"失败路径"（如预期报错）时用 `|| true` 并在注释里说明为什么预期失败；
- 涉及大镜像/外网资源时，注释里给出预载命令（指向根 scripts/ 的公共脚本）；
- `clean` 之后集群应回到实验前状态（`kubectl get all` 无残留）。

#### manifests/

- 一个主题一个大 YAML（多文档），或按 tier 拆分；
- 每个字段尽量带一句"为什么"的注释（教学清单的注释密度远高于生产清单）；
- 演示密码用 `changeme` / `demo-password` 等明显的占位值，并注释
  "生产应使用 Secret/外部密钥管理"。

#### images/（Archify 架构图三件套）

每张图 = 图源 JSON + 交互 HTML + 双主题 SVG，三者同源、可复现。

**作者写 JSON（Typed IR），工具负责校验与渲染**——不要手写坐标/样式。
以 [Archify](https://github.com/tt-a1i/archify) 为例的完整管线：

```bash
cd archify/   # archify 仓库根
# 1. 选类型（architecture/workflow/sequence/dataflow/lifecycle），读对应
#    schemas/*.schema.json + 一个 examples/ 示例，然后编写图源 JSON：
#    meta.quality_profile="showcase"、meta.locale="zh-CN"、节点 ≤ 12、
#    一条主路径、自动路由优先（不要预先手调 via/labelAt）；
node bin/archify.mjs validate <type> <图源>.json --quality showcase --json
# 2. 按 diagnostics 修：只改被诊断的对象，一次一个；9 项检查全过即冻结；
node bin/archify.mjs deliver <type> <图源>.json <输出>.html --quality showcase --json
# 3. deliver 会原子提交自包含 HTML 并出具 SHA-256 回执；
node bin/archify.mjs visual-check <输出>.html --json
# 4. 浏览器证据（1440/1600/1920/2048 视口零溢出）通过后再人工视觉复核。
```

布局经验（实测沉淀）：

- 画布要"宽扁"（宽高比 ≥ 1.6），竖向长条会在 1440×900 视口垂直溢出；
- 多节点扇出时优先**删低价值边**（语义已被端点 sublabel/tag 隐含的），
  再考虑路由控制；标签放不进窄间隙就把它挪进节点的 sublabel/tag；
- workflow 用 schema v2（逻辑列 + 自动布局），泳道 ≤ 3，节点加宽用
  `width` 字段解决长副标签；不能通行的 route 预设直接删掉交给自动路由；
- 交互页 Export 菜单可导出**双主题 SVG**（跟随系统深浅色）与 4400 级
  全图 PNG；README 内嵌 SVG、仓库同时保留 HTML 供交互；
- 仓库开启 GitHub Pages（master / root）后，每个实验的
  `labs/NN_xxx/images/xxx.html` 自动获得在线地址，README 里放链接即可
  （Jekyll 还会把 README.md 渲染成目录首页）。

---

## 四、跨实验的公共设施

- `scripts/load_resources.sh`：集中解决"环境拉不到外部资源"的公共问题
  （K8s 版是镜像预载：宿主机从镜像源拉取 → save → 灌入所有节点）。
  特征：无参数时处理默认列表、幂等可重复执行、被多个实验的注释引用。
- 根 README 承担"环境要求 + 国内/海外网络说明 + 公共脚本用法"，
  各实验 README 只写自己特有的前置。

### 镜像预载 playbook（实测沉淀）

网络受限环境下最常用的套路，按优先级：

1. **节点内直接拉**（最可靠）：`docker exec <node> ctr -n k8s.io images pull
   <镜像源>/<image>` 再 `ctr images tag` 成 Pod 里用的正式名。多架构镜像在
   宿主机 `docker save` 可能产出空壳 tar，节点内 pull 可绕过；
2. **宿主机拉+灌入**：`docker pull <镜像源>/<image>` → `docker tag` →
   `docker save | docker exec -i <node> ctr images import -`（公共脚本即此封装）；
3. **常用镜像源映射**：docker.io→`docker.m.daocloud.io`（library/ 前缀要补）、
   registry.k8s.io→`k8s.m.daocloud.io`、quay.io→`quay.m.daocloud.io`、
   ghcr.io→镜像普遍不可达（换自建源或改实现）；
4. 预载后 Pod 仍 ImagePullBackOff 时，删 Pod 强制重建（kubelet 有退避缓存）；
5. 拉取偶发 EOF/中断会留下**损坏的本地缓存**（元数据在、blob 空），表现为
   反复 pull "up to date" 但运行失败——`docker rmi` 后重拉。

---

## 五、环境对抗与版本漂移（实测教训沉淀的规则）

1. **版本能探测就不要写死**：装好的 CLI 决定实际部署的组件版本，脚本应在
   运行时探测（如 `istioctl version --client --short`）再用它推导镜像 tag。
2. **引用上游清单先核对三件事**：装在哪个 namespace、部署什么镜像 tag、
   等待 rollout 用哪个对象——上游改版后这些常与文档不符（例：snapshot-controller
   v8.2.0 的清单装在 kube-system 且镜像是 v8.0.1）。
3. **CRD/策略字段对着已安装版本验证**：用 `kubectl explain` 核 schema，
   不要凭记忆写字段名（例：Kyverno 1.19 的 exclude 嵌套、Instrumentation 是
   v1alpha1、CSI 卷字段是 volumeAttributes 而非 attributes）。
4. **CLI flag 会随版本废弃**：脚本里用了非基础 flag（如 --sleep-forever）的，
   在目标 CLI 的两个大版本上各测一次。
5. **演示里永远不要用假 registry/假端点**：镜像永远拉不到的"演示"等于没有
   演示。差异化演示用真实存在的值（不同真实 tag、不同真实端口）。
6. **"预期的失败"必须可复现**：声称会 Pending/被拒绝的演示，要在默认环境
   真实触发一次（例：maxSkew=1 在均匀调度下任何副本数都不会拒绝——须制造
   "拓扑域进不去"的条件才会）。触发不了就改设计，或在 README 如实标注。
7. **网络不可达的环节给出替代路径**：哪个组件装不上、用哪个镜像源替换、
   哪些步骤不受影响可以继续——写成 README 小节，而不是让读者卡死。

---

## 六、开发工作流（做一个新实验的顺序）

1. **定主题与预期学习目标**（读者做完能回答的 3 个问题）；
2. **写 manifests**（声明先行）；
3. **写脚本**，在真实环境里逐步跑通、边跑边修；
4. **写 README**，把跑通过程中的真实输出粘进"实操演示"；
5. **编写 Archify 图源并走完渲染管线**（validate → deliver →
   visual-check → 导出双主题 SVG，见第三节 images/ 规范），README 内嵌
   SVG 并链接交互版；
6. **自检清单**：
   - [ ] `bash -n` 通过；脚本从任意 cwd 调用都正确
   - [ ] `./xxx.sh clean` 后无残留资源
   - [ ] README 文件树与磁盘实际一致；图片链接可解析
   - [ ] 涉及外网资源的步骤有预载/镜像替代说明
   - [ ] "预期结果"章节描述的与实际发生的一致
   - [ ] 引用的上游清单已核对 namespace/镜像 tag/等待对象（见第五节第 2 条）
   - [ ] CRD/策略字段已用 kubectl explain 对已安装版本验证
   - [ ] 声称"会失败/被拒绝"的演示在默认环境真实触发过一次
7. **真机全流程跑一遍是硬门槛，不是可选项**：在干净环境（重建的沙箱、
   无预置残留状态）下按脚本顺序完整执行，核对每步实际输出与 README 一致。
   静态检查（语法/渲染/lint）全部通过不构成"可执行"的证据——本项目实测
   32 个实验静态全绿，仍抓出 12 处只有运行才能暴露的 bug。

## 七、质量与维护约定

- 每个 PR/commit 只做一件事；commit message 英文、祈使句、正文列要点；
- 不引入个人绝对路径、真实凭据；
- 版本能钉死的钉死（CLI 版本、清单 tag），钉不死但要写"如何探测实际版本"；
- 已知环境限制（某功能本地沙箱演示不了）在 README 建表说明，不隐藏；
- 工具会话文件（`.zcode/` 等）、构建产物一律 gitignore。

---

## 八、AI 生成提示词（把下面这段连同本文件喂给 AI 即可量产新实验）

```
你要创建一个名为 hands-on-{{DOMAIN}} 的教学项目。严格遵循随附的
PROJECT_TEMPLATE.md 中的结构与规范。请按以下步骤工作：

1. 先给出实验列表规划（25~35 个，编号+主题+一句话目标，分 4~6 个学习阶段），
   00 是工具安装、01 是环境初始化，供我确认；
2. 我确认后，逐个实验生成四件套：README.md（按模版章节结构，中文，
   编号章节、内嵌双主题 SVG、诚实预期）、主演示脚本（分步 case 分发骨架 +
   set -euo pipefail + 完整 clean）、manifests/（带教学注释）、以及
   images/ 下的 Archify 图三件套（图源 JSON 通过 showcase 校验后
   deliver 出交互 HTML，再导出双主题 SVG 内嵌进 README）；
3. 所有命令必须是你确信在 {{TOOLCHAIN}} 当前稳定版上可执行的；
   不确定的 API/flag 要先验证再写；
4. 每生成 5 个实验停下，输出自检清单结果（bash -n / 语法检查 /
   清单与文档一致性 / CRD 字段对已安装版本核对），等我确认后继续；
5. 涉及"预期失败"的演示，写明它在默认环境下真实触发的前提条件；
   引用上游清单/CLI flag 时按模版第五节的核对清单逐条确认；
6. 全部完成后生成根 README（实验表格+学习路线）和 .gitignore。
不要生成 LICENSE 和 git 操作，等我指令。
```

---

## 九、复刻时的领域映射参考

| 本模版（K8s） | 复刻到其它领域时的对应物 |
|---|---|
| kind 集群 | 领域的本地沙箱（fintech：本地账本/区块链测试链；LLM：本地推理运行时） |
| kubectl | 领域核心 CLI |
| manifests/*.yaml | 领域的声明式配置（合约、流水线定义、拓扑文件） |
| images/ Archify 图三件套 | 保留：JSON 图源 + 交互 HTML + 双主题 SVG 的组合与工具无关（任何 diagram-as-code 工具皆可套用此三件套与校验管线） |
| 演示脚本串联"创建→观察→破坏→验证→清理" | 保留这个生命周期骨架，换领域动词（如 fintech：开户→记账→对账→冲正→清退） |
| load_images.sh 解决镜像拉取 | 解决该领域最普遍的环境阻塞（包源、测试数据、模拟服务） |
| "诚实预期"章节 | 保留：任何本地环境演示不了的生产行为都明说 |
