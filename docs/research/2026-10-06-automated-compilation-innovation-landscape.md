# 自动化编译研究方向演进：合同反馈研究与进展感知控制候选

> 日期：2026-10-07
> Tracking Issue：[#381](https://github.com/WWFXL/Forge-AutoCompiler/issues/381)
> 工作类型：结果分析、文献研究与研究设计
> 证据边界：本轮未调用 Provider、未读取 credential、未创建 formal attempt，也未写入 formal experiment evidence。

## 1. 决策摘要

Forge 的长期目标仍是让 C/C++ 仓库自动化编译同时做到：严格成功、尽快成功、使用更少的模型轮次和资源，并能独立复现结果。研究方向经历了以下调整：

1. **已停止的旧方向：合同反馈驱动修复。** 比较普通失败、结构化 verifier finding 和抽象 repair goal 是否提高失败后的严格转换率。早期小样本结果有正向信号，但扩大 fault stratum 后没有观察到稳定增量，且创新容易被解释为“提供更详细的错误信息”。该机制不再作为论文主线。
2. **当前候选方向：跨构建系统的进展状态建模与预算控制。** 研究如何把连续构建失败表示为可比较的状态，并估计不同动作的单位成本成功增益，从而决定继续、切换工具、从 checkpoint 分支、升级模型或停止。

合同继续承担两项基础职责：

1. 定义任务目标和允许操作的权威任务合同；
2. 判定 candidate、功能、来源和 clean replay 是否通过的严格裁判。

旧 C0/T1/T2 identity 和 evidence 保持只读；不修复 `lz4` checkpoint，不继续剩余 24 arms，也不创建 mechanism v2 replacement identity。

新方向目前仍是**候选研究问题**，尚未冻结为最终主线。若实现只包含“错误重复后切模型”“达到 token 阈值后停止”或固定 small-to-large cascade，它仍然只是工程调度。它能否形成论文贡献，取决于是否能提出跨 CMake、Make 和 Autotools 的确定性进展表示，并证明该表示比轮次、token 和错误类别等简单信号更能改善严格成功率与成本前沿。

当前结论是研究方向候选，不是方法效果结论。本次检索语料中没有发现直接把 Forge 式严格终点、跨构建系统进展状态和预算动作统一为一个 C/C++ 仓库自动构建控制问题的工作；这不构成“首次”声明。

## 2. 旧方向：不同反馈能否提高编译成功率

### 2.1 研究动机

真实仓库的自动化编译不是“构建命令退出码为 0”就算成功。Agent 还可能交付错误 target、遗漏动态库或头文件、使用无法证明来源的构建路径，或者只在被污染的原容器中成功。Forge 因此把成功拆成 candidate、功能、来源、external evaluator、clean replay 和 cleanup 等严格层次。

当严格 verifier 拒绝候选时，模型通常只看到原始构建日志或一个普通失败状态。原始日志很长，却不一定指出违反了哪项任务合同。旧方向的动机是：**verifier 已经掌握确定性的失败事实，如果把这些事实以有界、无答案泄漏的方式反馈给模型，是否能减少重复诊断并提高严格编译成功率？**

### 2.2 要解决的问题

旧研究试图解决三个具体问题：

1. Agent 能否区分“代码已经编译”与“提交的目标产物满足任务合同”；
2. Agent 能否依据 verifier 已确认的 target、path、artifact kind 或 provenance finding 修正候选，而不是继续盲目重试；
3. 反馈带来的模型请求、token 和验证开销，是否能换来更多严格成功。

核心 estimand 不是 JSON 格式本身，而是**合同派生的可操作反馈包暴露效应**。为了隔离反馈，实验从同一 failure checkpoint 派生分支，保持模型、工具、workspace、命令历史、环境、剩余预算和最终 evaluator 一致，只改变模型看到的反馈：

- `C0`：只说明候选验证失败；
- `T1`：增加 verifier finding、expected/actual、相关路径和有界文件集合；
- `T2`：在 T1 上增加抽象 repair goal，但不提供 shell 命令、补丁或正确答案。

最终成功必须闭合 candidate、functional oracle、provenance、external evaluator、clean replay 和 cleanup。仅重新构建成功、产物存在或 Agent 自报成功都不计为严格转换。

### 2.3 已完成的实验与结果

| 阶段 | 设计与范围 | 观察结果 | 能够说明什么 |
| --- | --- | --- | --- |
| Behavioral pilot v2 | 单个 CMake 仓库、单个 `artifact_staging_missing` controlled fault，6 个 matched pairs / 12 arms；baseline 对 treatment | baseline `3/6`，treatment `5/6`，配对差 `+2/6`；baseline 39 requests / 140,786 tokens，treatment 27 requests / 91,158 tokens | 在这个单一受控现场中，repair packet 有正向探索信号；不能外推到自然失败、其他项目或其他 fault family |
| Multi-checkpoint v3 | CMake、Make、Autotools 三个 case，各 2 pairs；仍属于同一 `artifact_staging_missing` fault family | baseline `4/6`，treatment `6/6`；case 等权 macro-average 为 `0.667` vs `1.000` | 说明早期信号不只出现在一个构建系统；仍没有覆盖不同失败机制 |
| Opaque provenance replication | provenance fault，12 pairs；独立复制与 endpoint 删失规则 | 12/12 pairs 终结，但 7/12 endpoint-censored；baseline `0/12`，treatment `6/12`；仅 5 个 eligible pairs、2/6 完整 project blocks，`primary_test=null` | 表面差异不能形成确认性效应；大量 endpoint attrition 说明可执行性和可辨识性不足 |
| Mechanism v2 三臂 formal batch | 计划 6 projects × 2 fault strata × C0/T1/T2，共 36 arms；实际完成 2 projects、4 checkpoints、12 arms | 两个 delivery/target checkpoint 均为 `1/1/1`，两个 provenance checkpoint 均为 `0/0/0`；三个 observed-complete estimate 都为 `0`。共 75 requests / 1,068,534 tokens | 在已完成项目上，反馈粒度没有改变严格结果；批次不完整，不能据此证明反馈无效或等效 |

主要仓库证据入口包括 [Behavioral pilot v2 结果](../../benchmarks/reports/cpp-verifier-checkpoint-behavioral-pilot-v2.md)、[Mechanism v2 formal 失败审计](../../benchmarks/reports/cpp-contract-driven-repair-mechanism-v2-formal-failure-audit.md) 和 [Runtime v3 三臂 qualification](../../benchmarks/preregistrations/cpp-runtime-v3-three-arm-zero-provider-qualification.md)。Multi-checkpoint v3 与 opaque provenance 的历史综合同时记录在 `docs/research/2026-09-29-automated-compilation-thesis-direction.md` 和个人知识库笔记“Forge 毕业论文方向与契约驱动修复设计”；原始冻结 evidence、ledger、marker 和记录哈希仍是实验事实的最终权威。

Runtime v3 三臂 qualification 还在 delivery/target 与 provenance 两个真实 Docker parent checkpoint 上证明了三臂可以从同源状态派生，并能闭合 evaluator、replay 和 cleanup。它是零 Provider 基础设施门禁，不是第五个效果实验。

Mechanism v2 在 checkpoint 5 `lz4:delivery_target` 的 parent capture 阶段停止：冻结 builder 要求恰有一个 target-mapped compiled artifact，而任务合同同时要求 executable `bin/lz4` 和 static library `lib/liblz4.a`。失败发生在 sequence 13 attempt 创建前，剩余 24 arms 未运行。缺失的 8 个 checkpoints 不填零；三个比较的 identification interval 都为 `[-2/3, +2/3]`，`primary_test=null`、`secondary_test=null`。

### 2.4 实验效果与结论

这些实验形成的是一条由“早期正向信号”走向“未观察到稳定增量”的证据链：

- 单一 delivery fault 的小样本 pilot 中，结构化反馈与更高转换率、更少 requests 和更少 tokens 同时出现；
- 扩展到 provenance fault 后，反馈没有克服更深层的修复困难；
- mechanism v2 已完成的四个 checkpoints 中，结果完全由 fault stratum 区分，而不是由 C0/T1/T2 区分；
- 不完整批次不能证明总体无效，但也没有提供继续把反馈机制作为主要创新所需的增量证据。

旧方向还存在独立于实验结果的创新风险：

- T1 容易被解释为更详细、结构化的错误信息，而不是独立的新修复机制；
- T2 只增加抽象 repair goal，干预强度有限；
- 合同本身主要解决“如何判断是否真的成功”，并不自然回答“怎样更快、更便宜地成功”；
- 继续修复旧实验会把成本投入到一个创新表述较弱、可解释性也有限的问题上。

因此，研究决策是保留合同作为严格裁判，永久停止 mechanism v2，不再把反馈暴露作为主要创新。旧证据可以作为探索性负结果和研究转向依据，但不支持 treatment effect、统计显著性、等效性或模型排名。

## 3. 新候选方向：进展状态建模与预算控制

### 3.1 研究动机

自动化编译最终追求的不是让 Agent 多做几轮，而是在有限资源下让更多仓库达到严格成功，并缩短成功时间、减少思考轮次、token 和费用。现有系统通常给每个任务固定流程和统一重试上限，但不同运行的状态并不相同：有的轨迹刚解决依赖并进入 configure，有的只是在重复同一错误，有的已经完成编译却卡在目标交付或 provenance。

已有证据说明固定追加计算并不总是有效。CXXCrafter 的失败项目平均耗时约 2.67 小时，远高于成功项目约 14.59 分钟；其 5/10/20 步实验也不是单调提升。GradleFixer 的失败轨迹平均约 4.1M input tokens，成功轨迹约 1.1M。BuildBench 的重复运行提高 pass@k，却仍按固定流程重新尝试。这些现象共同指向一个问题：**失败长尾消耗大量预算，而系统缺少判断“当前轨迹是否真的在接近成功”的统一状态。**

### 3.2 要解决的问题

新候选方向首先研究“状态”，其次才是“调度”。核心问题是：

> 如何把 CMake、Make 和 Autotools 的连续构建轨迹表示为可比较的进展状态，并估计继续、切换工具、从 checkpoint 分支、升级模型或停止等动作的单位成本成功增益？

一个候选表示是“构建失败前沿”：

`环境准备 -> 依赖满足 -> 配置完成 -> 编译完成 -> 链接完成 -> 目标产物有效 -> 功能通过 -> 来源合法 -> clean replay`

它需要区分：旧问题被解决且失败前沿后移的**推进**，错误文本变化但没有更接近严格终点的**横向变化**，以及重复相同问题或破坏已完成阶段的**停滞/回退**。这类状态用于解决现有实现中的五个问题：

1. 固定轮次无法区分仍在推进的任务和已经停滞的任务；
2. 原始错误文本变化不等于实际进展，容易造成无效重试；
3. 从头重启会丢失已获得的仓库、依赖和构建知识；
4. 成功案例平均时间会忽略最昂贵的失败长尾；
5. 严格 verifier 目前只负责判定终点，还没有参与估计下一单位预算的价值。

### 3.3 创新成立条件

这个方向不能仅靠阈值和路由规则成立。至少需要同时证明：

1. 存在跨 CMake、Make、Autotools 可确定重建的进展状态表示；
2. 该表示能支持可解释的动作或预算选择；
3. 相比固定 Flow，以及只使用轮次、token、错误类别的简单基线，它能改善固定预算严格成功率或 success-time-cost 前沿；
4. 这种关系在未见项目和时间隔离测试上仍然成立。

如果离线分析不能证明进展状态比简单特征提供额外预测或决策价值，应停止这个方向，而不是直接实现一个复杂 controller。

## 4. 检索方法与边界

### 4.1 检索范围

定向检索覆盖 2024-01 至 2026-10 首次公开或更新的以下主题：

- C/C++ 仓库级自动构建和编译 Agent；
- 可执行环境配置、系统包构建和编译错误修复；
- 严格成功判据、过程轨迹和重复尝试评测；
- 软件工程 Agent 的测试时计算扩展、搜索和轨迹复用；
- 预算约束模型路由、经验记忆、领域工具和早停。

使用的来源包括 arXiv API、论文 PDF、ACL Anthology、公开代码仓库，以及个人知识库中的论文解读。知识库检索遵循 `search_notes -> read_note`，本轮读取：

- `01-研究/自动化编译/2026-09-29-Forge毕业论文方向与契约驱动修复设计.md`，标题“Forge 毕业论文方向与契约驱动修复设计”；
- `01-研究/自动化编译/相关论文/2025-2026自动化编译论文索引.md`，标题“2025-2026 自动化编译论文索引”；
- `01-研究/自动化编译/相关论文/CXXCrafter-论文解读.md`，标题“CXXCrafter：论文解读与研究启发”；
- `01-研究/自动化编译/相关论文/CompileAgent-论文解读.md`，标题“CompileAgent：论文解读与研究启发”。

个人知识库是历史研究综合的来源，当前仓库和冻结 evidence 才是 Forge 代码与实验事件的权威来源。本轮没有修改知识库。

### 4.2 局限

这是一轮面向方向决策的定向检索，不是 PRISMA 式系统综述。部分 2026 工作仍是预印本；论文之间的任务、数据分布、模型、工具、预算和成功判据不同，成功率不能直接横向排序。后文将“论文报告”与“对 Forge 的推断”分开。

## 5. 自动化编译应该优化什么

### 5.1 严格成功是约束，不是唯一效率指标

Forge 的任务成功应继续使用分层终点：

- `S0`：运行有效；
- `S1`：构建命令完成；
- `S2`：目标产物有效；
- `S3`：任务级功能验收通过；
- `S4`：来源和操作合法；
- `S5`：独立 clean replay 通过。

建议把 `S0-S5` 全部通过定义为严格成功。合同 verifier、external evaluator 和 clean replay 负责测量这个结果，不负责决定论文的主要修复策略。

### 5.2 主要终点

未来比较应预先固定预算向量

`B = (wall-clock, model requests, input tokens, output tokens, provider cost, build executions)`，

并把以下指标设为主要结果：

1. **固定预算下的严格成功率** `P(S0-S5 | B)`；
2. **success-budget curve**：随着预算增加，累计达到严格成功的任务比例；
3. **严格成功的受限平均时间/成本**：失败任务在上限处删失，而不是从均值中删除。

不能只比较成功案例的平均时间或平均 token。失败长尾通常消耗最多资源；只保留成功案例会产生幸存者偏差。CXXCrafter 已报告 Top100 成功项目平均约 14.59 分钟、失败项目平均 2.67 小时，这正说明失败尾部必须进入效率评价。

### 5.3 次要过程指标

- 首次严格成功时间；
- 模型 logical requests、physical attempts 和 Agent 决策轮次，三者分开计数；
- input/output/cached tokens 和按冻结价目表复算的 Provider 费用；
- build/configure/test/replay 的次数与机器时间；
- 相同失败签名的重复次数、无状态变化动作比例；
- 模型升级、工具切换、checkpoint 分支、回滚和早停次数；
- 基础设施、Provider、方法、验证器和预算耗尽的终止分类。

“tokens 不设上限”适合避免旧可行性实验因人为 ceiling 提前失败，但不适合验证成本或预算优化。若进入新正式研究，必须用全新 identity 冻结一个足够高但有限的预算向量；这不追溯修改任何旧实验。

## 6. 2024-2026 直接相关工作

| 工作 | 论文报告的任务与结果 | 资源或过程证据 | 对本研究的缺口 |
| --- | --- | --- | --- |
| [CXXCrafter](https://doi.org/10.1145/3729386)（FSE 2025） | 752 个 C/C++ 项目中构建 587 个，约 78%；闭环含 Parser、Dockerfile Generator、Executor/Judge | Top100 中 5/10/20 步上限分别成功 69/75/74；成功平均 875.31 秒，失败平均 2.67 小时；Top100 模型费用共 $30.85 | 说明动态交互重要，但更多轮次不保证更好；没有状态相关预算分配和统一 S0-S5 终点 |
| [CompileAgent](https://arxiv.org/abs/2505.04254)（2025） | 100 个 C/C++ 项目，七种模型成功率 55%-96%；固定 Flow 调用 Shell、说明检索、网页搜索和多 Agent 讨论 | GPT-4o 完整配置报告 89%、8.38 小时、$16.53；不同策略的调用和 token 预算未完全等价披露 | 固定 Flow 和多 Agent 已有直接先例，不能作为 Forge 的主要创新 |
| [BuildBench](https://arxiv.org/abs/2509.25248v2)（TMLR，v2 2026） | 从 385 个随机样本人工筛得 148 个可编译 C/C++ 项目；OSS-Build-Agent + Claude 3.7 达到 67.6% strict、73.0% flexible success | GPT-4o 条件约 5.27 分钟、$0.34/项目，约 87K input + 1.6K output tokens；三次 GPT-4o 运行 strict 为 `53.0% ± 6.8`，pass@1 到 pass@3 为 54.7% 到 65.5% | 已经报告成功、时间、费用和重复尝试，但仍采用固定流程/上限，没有按运行状态决定把预算给哪个项目或哪条轨迹 |
| [Repo2Run](https://arxiv.org/abs/2502.13681v4)（2025） | 420 个含测试的 Python 仓库，报告 86.0% 环境构建成功率 | 迭代 Docker image、测试和 Dockerfile | 是环境配置强基线，但领域、终点和 C/C++ Forge 不同 |
| [GradleFixer](https://arxiv.org/abs/2510.08640v3)（EACL 2026） | AndroidBuildBench 含 1,019 个失败，184 个测试实例；领域工具 Agent 报告 81.4% pass@1 | 成功轨迹平均约 10.6 LLM calls、1.1M input tokens；失败轨迹约 4.1M input tokens。小模型 + 专用工具可超过大模型 + 通用 Shell | 证明失败长尾和工具抽象很重要；“增加领域工具”已有直接先例，C/C++ 研究需落在跨构建系统状态控制或动态工具选择 |
| [EnConda-Bench](https://arxiv.org/abs/2510.25694)（2025） | 把环境配置拆为错误识别、描述、修复建议和执行；Repo2Run + Claude-4 的过程指标较强，但 Pass@1 仍为 22.9 | 输出 token 增加通常改善错误描述，却不稳定改善 Pass@1 | 过程指标已有先例；新贡献需让过程信号实际改变预算动作，而不只是多报告几张表 |
| [EvoConfig](https://arxiv.org/abs/2601.16489)（2026 预印本） | 专家诊断、多 Agent 自反馈和动态修复优先级；EnvBench 报告 78.1%，比 Repo2Run 高 7.1 个百分点 | 强调执行后细粒度诊断和优先级调整 | 与“动态优先级”相邻；Forge 必须明确预算约束、严格终点和可辨识的控制动作 |
| [ComBench](https://arxiv.org/abs/2603.27333)（2026 预印本） | 200 个可复现 C/C++ 仓库级真实编译错误；GPT-5 compile success 146/200，但 semantic correctness 仅 82/200 | 同时评价 compile success、semantic correctness 和 exact match | 进一步证明“编译通过”不能替代语义/任务正确；支持保留合同裁判，但不是修复机制证据 |
| [PhantomRun](https://arxiv.org/abs/2602.20284)（MSR 2026） | 从四个嵌入式项目 4,000+ CI build failures 研究自动修复，报告最高约 45% | 使用日志、源码、历史修复和多 CI/build-system 适配层 | 历史修复和领域适配已有先例；跨项目迁移仍受项目族和工具链限制 |
| [EvidenT](https://arxiv.org/abs/2605.08621)（2026 预印本） | 219 个 RISC-V 系统包失败中修复 118 个（53.88%），所适配 agentic baseline 为 20.55% | 每个包最多三轮，维护 iteration-aware evidence，使用外部 Build Service | 证据保留、外部构建和迭代历史不能单独作为创新；尚未回答在全局预算下何时继续、分支或停止 |

### 6.1 现有实现机制对比

论文成功率掩盖了系统实现上的差异。以下矩阵只比较论文或公开实现明确描述的机制；“未充分报告”不表示系统一定没有该能力。

| 系统 | 控制循环 | 跨轮状态 | 主要工具/动作 | 成功裁判 | 资源策略 |
| --- | --- | --- | --- | --- | --- |
| CXXCrafter | Parser -> Dockerfile Generator -> Executor/Judge -> 失败反馈 | 当前完整 Dockerfile、相关历史和最近日志 | 仓库解析、文档/依赖提取、Docker build | 指令与日志的 LLM Judge，主结果另有人工复核和部分产物检查 | 默认固定 10 步；统一比较 5/10/20 步 |
| CompileAgent | CompileNavigator -> Shell -> ErrorSolver -> 再执行 | MasterAgent 会话与工具结果 | 文件导航、说明提取、网页搜索、Shell、多 Agent 讨论 | Shell outcome 与人工预编译 target files 匹配 | 固定 Flow；逐条件 token/调用上限未充分报告 |
| OSS-Build-Agent | 说明检索 -> 单命令执行 -> 错误修复循环 | 检索轨迹、命令与执行结果 | LLM-assisted retrieval、Shell/执行 Agent | 专家目标文件名列表的 strict/flexible success | 固定最大轮次；另以重复完整运行计算 pass@k |
| Repo2Run | Docker image 构建 -> unit tests -> Dockerfile 修订 | 当前 Dockerfile 与 build/test feedback | Docker、Shell、测试 | 整条 build/test pipeline 通过 | 固定迭代流程，未形成跨任务预算调度 |
| GradleFixer | Agent 读写 -> 专用 Gradle 动作 -> rebuild | workspace、工具结果和模型上下文 | `run_build`、`run_gradle`、`change_java_version` | Android build 成功 | 主实验不限制 LLM calls；消融固定 30 calls |
| EvoConfig | 专家诊断 -> 多 Agent 修复 -> 自反馈调整优先级 | 诊断和修复优先级 | 环境配置、专家诊断、多 Agent 协作 | 环境可执行 | 动态调整修复优先级，但未把时间/token/费用统一成预算控制 |
| EvidenT | Evidence Controller -> Repair Orchestrator -> Build Service | 最近 build feedback、累计 repair history、缓存分析 | 定位、artifact inspection、package/source 修复、外部 build | 外部 Build Service clean build | 每包最多三轮；没有跨任务资源再分配 |
| Forge 当前基础 | Compile Session -> compiler Agent -> candidate/evaluator/replay | session ledger、failure checkpoint、candidate 与 replay evidence | 受限 Shell、candidate submit、functional/provenance/replay evaluator | S0-S5、external evaluator、clean replay、cleanup | 预算字段已可冻结，但当前没有根据构建进展联合选择模型、工具、分支和停止 |

这张表显示，Forge 的差异化资产是严格、外部化的终点和可恢复构建状态；缺失的研究机制是利用这些状态进行资源控制。若只复制某个系统的固定循环、增加一组工具或增加轮次，无法形成新的主张。

以上数值均属于各论文自己的协议，不能当作 Forge 基线或模型排名。公开实现可参考 [CXXCrafter Community Edition](https://github.com/seclab-fudan/CXXCrafter-Community-Edition)、[Repo2Run](https://github.com/bytedance/Repo2Run) 和 [EnConda-Bench](https://github.com/TencentYoutuResearch/EnConda-Bench)。

## 7. 可迁移的新型 AI 技术

### 7.1 测试时计算扩展与搜索

- [CodeMonkeys](https://arxiv.org/abs/2501.14723) 同时扩大单轨迹迭代和并行轨迹，在 SWE-bench Verified 报告 57.4%，总预算约 $2,300。它证明并行采样可以换取成功率，也直接暴露成本问题。
- [SWE-Search](https://arxiv.org/abs/2410.20285) 用 MCTS、Value Agent 和候选判别器搜索软件修复轨迹，相对其基线平均提升 23%；其价值估计和搜索开销不一定适合构建 Agent。
- [Thinking Longer, Not Larger](https://arxiv.org/abs/2503.23803) 用长思维链、过程奖励和 beam search 扩大 SWE Agent 的测试时计算；论文同时观察到最难任务在更高预算下可能下降，说明“更多计算”不是单调收益保证。
- [Satori-SWE](https://arxiv.org/abs/2505.23604) 用选择与变异进行进化式测试时扩展，目标是减少盲目采样。
- [SWE-Replay](https://arxiv.org/abs/2601.22129) 在已采样轨迹的关键中间步骤分支，报告相对 naive scaling 最多降低 17.4% 成本、提高 3.8 个百分点 resolve rate。

对 Forge 的启发不是直接复制树搜索，而是利用已有 failure checkpoint 和严格 verifier，比较“从头重复采样”与“从有进展的构建状态继续/分支”。风险是 SWE-Replay 已经覆盖一般软件工程轨迹复用；若只把同一方法搬到编译任务，创新不足。

### 7.2 预算约束模型路由

- [RouteLLM](https://arxiv.org/abs/2406.18665) 学习强弱模型路由，在特定质量目标下报告最高 3.66 倍成本节省；它也显示训练/评测分布不匹配会使路由接近随机。
- [Adaptive LLM Routing under Budget Constraints](https://aclanthology.org/2025.findings-emnlp.1301/) 将路由建模为 contextual bandit，并用 multi-choice knapsack 处理不同预算。

这些工作主要根据**初始 query**选择模型。自动化编译更适合根据**运行中构建状态**选择下一动作：相同仓库在 configure、compile、link、artifact、provenance 阶段的难度和最优工具不同。这是可迁移方法与 Forge 研究问题之间最重要的差别。

### 7.3 经验记忆和工作流归纳

- [ExpeL](https://arxiv.org/abs/2308.10144) 从训练任务轨迹抽取自然语言经验，并在新任务中检索使用；论文发表于 AAAI 2024。
- [Agent Workflow Memory](https://arxiv.org/abs/2409.07429) 从过去轨迹归纳可复用 workflow，在 WebArena 上同时提高成功率并减少成功步骤数。

自动化编译可把“CMake 找包失败 -> 检查 config/module mode”“Autotools 缺 generated configure -> 先 bootstrap”等模式形成经验，但必须按项目族、时间和仓库切分，防止把同仓库历史修复或 benchmark ground truth 泄漏到测试任务。记忆内容还会随依赖源和工具链版本失效，因此不适合作为第一主线。

### 7.4 预算感知与早停

- [BAGEN](https://arxiv.org/abs/2606.00198) 把预算作为 Agent 的控制信号；其回放实验中，早停可节省失败轨迹 28%-64% tokens，但训练后的预算区间覆盖率仍不超过 47%。这是 2026 预印本证据。
- [Disentangling Task Difficulty from Run-Level Failure in Agent Failure Prediction](https://arxiv.org/abs/2610.05572) 区分“任务本来就难”和“当前这次运行正在失败”。该 2026-10-04 预印本发现，早期 run-level 判别约为 AUROC 0.50-0.55；固定 token 总预算下，task-level allocation 优于单纯 abort，只有 within-task AUROC 达到约 0.84-0.93 时早停才有收益。

这意味着 Forge 不应先把“预测当前轨迹会失败并提前停止”单独设为主创新。更稳妥的顺序是：先用任务和 checkpoint 的确定性特征分配预算，再把“重复失败签名、没有产物/依赖/阶段进展”作为可解释的停机或切换信号。

### 7.5 领域专用工具

GradleFixer 的直接证据很强：工具越贴近领域动作，成功率越高，失败轨迹 token 浪费越少。但它也使“给 Agent 增加专用工具”失去独立新颖性。Forge 可以把 typed build actions 用作预算控制器的低成本动作，例如 target graph inspection、dependency candidate lookup、configure/build/verify 和 replay；研究问题应是**何时选择这些动作**，而不是“是否有工具”。

## 8. 尚未解决的研究问题

综合直接相关工作和可迁移技术，本次语料中仍存在六个空白：

1. **预算仍多为固定上限。** 多数编译系统设统一轮次或重试数，难以把资源从已停滞任务转给仍在推进的任务。
2. **总体成功与效率分开报告。** 论文常给成功率、总费用或成功案例平均时间，但很少估计完整 success-time-cost 前沿。
3. **运行状态没有成为统一控制信号。** 日志、诊断、产物和历史会进入 prompt，却很少决定模型、工具、分支和停止动作。
4. **失败长尾昂贵。** CXXCrafter 和 GradleFixer 都显示失败任务远比成功任务消耗更多时间或 token。
5. **重复尝试有效但分配粗糙。** BuildBench 的 pass@k 和 SWE 测试时扩展说明重复采样能提高覆盖，但 naive restart 浪费已获得的仓库/构建知识。
6. **严格成功与控制策略脱节。** 严格 verifier 能拒绝伪成功，却没有被用于估计“继续投入一单位预算还有多大边际价值”。

## 9. 候选创新方向评分

评分采用 1-5 分，5 分最好。“论文成立性”综合考虑可辨识性、相关工作重合和可证伪性；分数是本次审查判断，不是实验结果。

| 优先级 | 候选方向 | 新颖性 | Forge 匹配 | 最小验证可行性 | 预算友好 | 论文成立性 | 主要风险 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 进展感知、预算约束自适应控制 | 4 | 5 | 4 | 5 | 4 | 需要足量开发轨迹校准策略；不能让 controller 训练集泄漏到测试项目 |
| 2 | verifier-guided checkpoint 分支与轨迹复用 | 3 | 5 | 3 | 3 | 3 | 与 SWE-Replay/SWE-Search 相邻，完整树搜索成本高 |
| 3 | C/C++ 跨构建系统 typed tool routing | 3 | 4 | 4 | 4 | 3 | GradleFixer 已证明 Tool Bridging，单纯换领域不足 |
| 4 | 跨仓库经验记忆与技能迁移 | 3 | 3 | 2 | 4 | 2 | 数据泄漏、经验过时和项目族偏差难控制 |
| 5 | 单独研究运行失败预测/早停 | 2 | 4 | 3 | 5 | 2 | 早期 within-task 信号可能不足，容易省成本同时损害成功率 |
| 6 | 合同反馈或合同裁判作为主创新 | 2 | 5 | 5 | 4 | 2 | 裁判价值明确，但容易被解释为更严格评测或更详细错误信息 |

第 1 项目前是优先审计的候选，不是已冻结的主线。下一步还需与“跨构建系统 typed action abstraction”和“带项目族、时间隔离的跨仓库经验迁移”做机制级比较。第 6 项继续作为统一 oracle 和支撑性贡献。

## 10. 候选方法：进展感知预算控制器

### 10.1 状态

在第 `t` 个决策点构造不含答案泄漏的状态：

- 构建阶段：environment/configure/compile/link/artifact/functional/provenance/replay；
- 规范化诊断签名：错误类别、关键 target/path、退出状态和日志哈希；
- 进展增量：已解决 finding、新暴露的下游失败、依赖/工具链变化、target/artifact coverage 变化；
- 轨迹历史：重复签名次数、无效动作、最近成功阶段和 checkpoint；
- 资源：已用/剩余时间、模型请求、tokens、费用和 build executions；
- 不确定性：候选动作是否有历史支持、当前状态是否超出开发分布。

合同 finding 可供控制器计算状态，但默认不把更多 finding 文本直接投影给修复模型。这样主要干预是预算动作，而不是错误信息详细程度。

### 10.2 动作

最小版本只需要五类动作：

1. 继续当前模型和策略；
2. 调用一个低成本 typed build tool；
3. 切换修复策略或从最近 checkpoint 分支；
4. 在剩余预算足够时升级模型；
5. 停止并记录预算耗尽/低边际价值终态。

第一阶段不实现完整 MCTS。先交付一个确定性、可解释的策略，再根据轨迹数据判断是否需要 contextual bandit 或学习式 value model。

### 10.3 可证伪主张

建议的主研究问题是：

> 在相同项目、exact commit、初始环境、工具集合和预算向量下，进展感知控制器是否比固定 Flow 在不降低固定预算严格成功率的前提下，降低受限平均时间、模型请求和费用；或者在相同成本下提高严格成功率？

建议采用两臂而不是恢复旧三臂。两臂获得相同模型池、工具池和总预算；区别只在资源调度是否读取运行中进展：

- `F0`：固定阶段 Flow 与预先确定的模型/工具/升级时序，不根据当前进展改变调度；
- `A1`：相同可用模型与工具，由进展感知控制器分配继续、切换、分支、升级和停止动作。

若最小版本只使用单一模型，则两臂都关闭模型升级，只比较继续、工具切换、checkpoint 分支和停止；模型路由留到后续增量，避免一次引入过多机制。

首要比较是在预注册预算点上的 strict success。效率和 success-budget curve 是有序次要终点。若 A1 只降低费用但明显降低严格成功率，则主张失败；不能用加权 utility 掩盖成功率下降。

### 10.4 机制消融

只有主比较显示值得继续时，再依次评估：

- `A1 - escalation`：去掉模型升级；
- `A1 - branching`：去掉 checkpoint 分支；
- `A1 - stagnation`：去掉重复签名/进展判定；
- `A1 - typed routing`：只保留通用 Shell。

这些消融回答“收益来自哪里”，不与主实验同时扩成大量 arms。

## 11. 最小验证路线

### 阶段 0：状态与计量资格门禁

类型：基础设施。零 Provider、零 formal attempt。

- 从现有只读轨迹验证状态字段能否确定性重建；
- 固定 logical request、physical attempt、tokens、费用、build execution 和 wall-clock 的计量口径；
- 验证相同轨迹重复提取产生相同状态签名；
- 验证 controller 看不到 hidden arm label、ground-truth patch 或 evaluator 答案。

完成标准：状态 schema、签名算法和预算账本在代表性 CMake/Make/Autotools 轨迹上闭合。

### 阶段 1：离线可行性分析

类型：结果分析，不作因果效果解释。

- 描述成功与失败轨迹的资源分布、重复签名和阶段迁移；
- 估计“按项目/checkpoint 静态分配”与“运行中早停”各自可能节省的预算上界；
- 用 project-family 和时间切分检查状态特征是否过拟合具体项目。

完成标准：证明至少存在可重复识别的停滞/进展状态；否则停止该方向。

### 阶段 2：零 Provider 控制面 qualification

类型：基础设施。

- 用确定性 scripted model 覆盖继续、工具切换、分支、升级拒绝、预算耗尽和 cleanup；
- 在相同 parent checkpoint 上验证 F0/A1 除 controller 决策外同源；
- 闭合 candidate、functional、provenance、external evaluator、clean replay 和 cleanup。

完成标准：控制器不改变任务身份和 oracle，且任何预算/状态异常 fail closed。

### 阶段 3：新 identity 的小规模 canary

类型：需要新的科研决策、预算和明确授权的数据收集。

- 冻结开发集/测试集、项目/checkpoint、模型快照、价目表、预算点和停止规则；
- 先运行少量配对任务检查状态覆盖、成本和终点 attrition；
- canary 只判断正式实验是否可执行，不估计 treatment effect。

### 阶段 4：正式比较

只有 canary 通过后建立全新 formal identity。旧 mechanism v1/v2 evidence 不导入新比较。正式规模、最小有意义效应和多重比较规则必须根据阶段 1-3 的数据另行冻结。

## 12. 主要风险与停止条件

- **数据不足：**若开发轨迹不足以校准状态/策略，先扩大非正式开发语料，不能在正式测试集上调阈值。
- **分布泄漏：**同仓库、相邻 commit 和历史 ground-truth repair 必须按项目族/时间隔离。
- **预算不可比：**不同模型、缓存、并发和 Provider 价格必须版本化；墙钟与 token 不合并成任意单一分数。
- **控制器开销：**router/value model 的 token 和时延必须计入总预算；不能把控制成本当作免费。
- **成功率受损：**早停节省成本但降低 strict success 时，主张不成立。
- **基础设施混杂：**网络、Provider、Docker 和 evaluator 故障保留在分母并按预注册分类。
- **相关工作重合：**若后续检索发现同任务、同状态动作和同严格终点的直接方法，应缩小或更换主张。

## 13. 下一项决策

下一项工作不是直接实现 controller，而是完成一次**创新机制审计**。应对以下三个候选做直接比较：

1. 跨构建系统的失败前沿/进展状态表示；
2. 跨 CMake、Make、Autotools 的 typed action abstraction；
3. 带项目族和时间隔离的跨仓库构建经验迁移。

每个候选都需要回答：相对最新论文新增了什么机制，是否只是场景迁移或工程组合，最小可证伪实验是什么，Forge 现有资产能否支持，以及什么结果会使方向被放弃。只有进展状态候选通过这轮审计后，才进入阶段 0 的状态与计量资格门禁设计，并冻结：

1. 状态签名最小字段和“有进展/停滞”的可执行定义；
2. F0/A1 可使用的模型和工具集合；
3. 预算向量及主要预算点；
4. 开发项目与最终测试项目的隔离规则；
5. 严格成功、受限平均时间/成本和 success-budget curve 的有序分析规则。

这些审计和设计决策完成前，不应创建新 formal identity、读取 credential 或调用 Provider。

## 参考资料

- Yu et al. [CXXCrafter: An LLM-Based Agent for Automated C/C++ Open Source Software Building](https://doi.org/10.1145/3729386). FSE 2025.
- Hu et al. [CompileAgent: Automated Real-World Repo-Level Compilation with Tool-Integrated LLM-based Agent System](https://arxiv.org/abs/2505.04254). 2025.
- Zhang et al. [BuildBench: Benchmarking LLM Agents on Compiling Real-World Open-Source Software](https://arxiv.org/abs/2509.25248v2). TMLR, 2026 version.
- Hu et al. [Repo2Run: Automated Building Executable Environment for Code Repository at Scale](https://arxiv.org/abs/2502.13681v4). 2025.
- Son et al. [Automating Android Build Repair: Bridging the Reasoning-Execution Gap in LLM Agents with Domain-Specific Tools](https://doi.org/10.18653/v1/2026.eacl-long.195). EACL 2026.
- [Process-Level Trajectory Evaluation for Environment Configuration in Software Engineering Agents](https://arxiv.org/abs/2510.25694). 2025.
- [EvoConfig: Self-Evolving Multi-Agent Systems for Efficient Autonomous Environment Configuration](https://arxiv.org/abs/2601.16489). 2026.
- Li et al. [ComBench: A Repo-level Real-world Benchmark for Compilation Error Repair](https://arxiv.org/abs/2603.27333). 2026.
- Fu et al. [PhantomRun: Auto Repair of Compilation Errors in Embedded Open Source Software](https://arxiv.org/abs/2602.20284). MSR 2026.
- Zhao et al. [EvidenT: An Evidence-Preserving Framework for Iterative System-Level Package Repair](https://arxiv.org/abs/2605.08621). 2026.
- Ong et al. [RouteLLM: Learning to Route LLMs with Preference Data](https://arxiv.org/abs/2406.18665). 2024.
- Panda et al. [Adaptive LLM Routing under Budget Constraints](https://doi.org/10.18653/v1/2025.findings-emnlp.1301). Findings of EMNLP 2025.
- Antoniades et al. [SWE-Search: Enhancing Software Agents with Monte Carlo Tree Search and Iterative Refinement](https://arxiv.org/abs/2410.20285). 2024.
- Ehrlich et al. [CodeMonkeys: Scaling Test-Time Compute for Software Engineering](https://arxiv.org/abs/2501.14723). 2025.
- Ma et al. [Thinking Longer, Not Larger: Enhancing Software Engineering Agents via Scaling Test-Time Compute](https://arxiv.org/abs/2503.23803). 2025.
- Zeng et al. [Satori-SWE: Evolutionary Test-Time Scaling for Sample-Efficient Software Engineering](https://arxiv.org/abs/2505.23604). 2025.
- Ding and Zhang. [SWE-Replay: Efficient Test-Time Scaling for Software Engineering Agents](https://arxiv.org/abs/2601.22129). 2026.
- Zhao et al. [ExpeL: LLM Agents Are Experiential Learners](https://arxiv.org/abs/2308.10144). AAAI 2024.
- Wang et al. [Agent Workflow Memory](https://arxiv.org/abs/2409.07429). 2024.
- Lin et al. [BAGEN: Are LLM Agents Budget-Aware?](https://arxiv.org/abs/2606.00198). 2026.
- EsfandyariDoulabi et al. [Disentangling Task Difficulty from Run-Level Failure in Agent Failure Prediction](https://arxiv.org/abs/2610.05572). 2026.
