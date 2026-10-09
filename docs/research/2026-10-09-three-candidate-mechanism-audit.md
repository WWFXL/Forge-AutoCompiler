# 自动化编译三个候选方向的创新机制审计

> 日期：2026-10-09
> Tracking Issue：[#381](https://github.com/WWFXL/Forge-AutoCompiler/issues/381)
> 工作类型：结果分析、文献研究与研究设计
> 文献截止：2026-10-09
> 权限边界：未调用 Provider、未读取 credential、未创建 formal identity 或 formal attempt，未写入或修改任何冻结 experiment evidence。

## 1. 审计结论

本轮审计比较三个候选是否具备区别于 2024–2026 最新工作的独立机制，而不只是在 CMake、Make、
Autotools 场景中重新组合已有 Agent 技术。

| 候选 | 机制审计结论 | 可保留的研究增量 | 主要重合或风险 | 当前定位 |
| --- | --- | --- | --- | --- |
| 跨构建系统失败前沿/进展状态 | **有条件通过** | 用可执行证据构造跨构建系统的偏序状态，显式表示已证实、待满足和被破坏的构建义务；用状态转移而不是错误文本变化判断推进、横向变化、停滞和回退 | EnConda-Bench 已做过程评价；FailFast、EET 和 run-level failure prediction 已研究早停；SWE-Replay 已研究中间状态分支 | 唯一值得进入下一轮冻结决策的主线候选 |
| 跨构建系统 typed action abstraction | **独立主线不通过** | 若作为支撑机制，可研究同一语义动作在三个构建系统中的共同前置条件、后置证据和失败类型，并让动作策略跨系统迁移 | GradleFixer 已直接验证 Tool Bridging；SWE-agent、ALIGN 和 ToolRosella 已覆盖专用接口或自动接口生成 | 作为进展状态控制器的动作层，不单独主张主要创新 |
| 带项目族和时间隔离的跨仓库经验迁移 | **当前延后** | 只有“版本漂移下的经验准入、失效和负迁移控制”仍可能形成更窄问题 | XRepoSkill、SetupX、EET、BootstrapAgent 已覆盖跨仓库规则、可执行经验、经验早停和可复用启动知识；隔离本身只是评测纪律 | 不进入当前最小主线；数据与实现成本过高 |

因此，建议把毕业论文候选进一步收紧为：

> **面向严格可验证自动化编译的跨构建系统进展状态表示，以及该表示对预算动作选择的增量价值。**

这里的首要研究对象是状态表示，不是复杂 controller。只有离线、零 Provider 的状态资格审计证明该表示
比轮次、token、构建阶段和错误类别等简单信号提供额外信息，才值得另开 tracking Issue 设计 F0/A1
控制实验。新主线仍未冻结，本报告只完成机制筛选。

## 2. 审计方法与判定标准

### 2.1 文献范围

审计沿用创新版图中的直接工作，并补充截至 2026-10-09 与三个候选最接近的论文：

- 过程状态与控制：[EnConda-Bench](https://arxiv.org/abs/2510.25694)、
  [SWE-Replay](https://arxiv.org/abs/2601.22129)、
  [EET](https://arxiv.org/abs/2601.05777)、
  [Fail-Fast, Restart-Smart](https://arxiv.org/abs/2608.03222) 和
  [Disentangling Task Difficulty from Run-Level Failure](https://arxiv.org/abs/2610.05572)；
- 动作与接口：[SWE-agent](https://arxiv.org/abs/2405.15793)、
  [ALIGN](https://arxiv.org/abs/2505.21055)、
  [GradleFixer](https://doi.org/10.18653/v1/2026.eacl-long.195) 和
  [ToolRosella](https://arxiv.org/abs/2603.09290)；
- 经验与技能：[Agent Workflow Memory](https://arxiv.org/abs/2409.07429)、
  [CTIM-Rover](https://arxiv.org/abs/2505.23422)、
  [Structurally Aligned Subtask-Level Memory](https://arxiv.org/abs/2602.21611)、
  [Memory Transfer Learning](https://arxiv.org/abs/2604.14004)、
  [SetupX](https://arxiv.org/abs/2605.26186)、
  [BootstrapAgent](https://arxiv.org/abs/2605.15815)、
  [SWE-Skills-Bench](https://arxiv.org/abs/2603.15401)、
  [VibeMemBench](https://arxiv.org/abs/2609.23570) 和
  [XRepoSkill](https://arxiv.org/abs/2609.36807)。

本次是面向方向决策的定向检索，不是系统综述。“未发现直接覆盖”不能写成全球首次。论文事实以公开摘要
和正文为依据；Forge 是否具备支撑资产属于本报告的工程判断。

历史研究决策还按 `search_notes -> read_note` 核对了个人知识库中的
`01-研究/自动化编译/2026-09-29-Forge毕业论文方向与契约驱动修复设计.md`（标题“Forge 毕业论文方向与契约驱动修复设计”）
和 `01-研究/自动化编译/相关论文/2025-2026自动化编译论文索引.md`（标题“2025-2026 自动化编译论文索引”）。
它们用于确认旧方向和既有检索边界；当前代码、实验事件和停止决策仍以仓库与冻结 evidence 为准。

### 2.2 通过条件

一个候选只有同时满足以下条件才通过：

1. **机制可区分：**能够指出相对最近工作的新增状态、动作或学习机制，而不只是换到 C/C++ 构建场景；
2. **问题具体：**机制针对现有方法中可观察、可复现的问题；
3. **干预可隔离：**最小实验能够保持模型、工具、任务和预算可比，只改变被研究机制；
4. **结果可证伪：**预先说明什么结果会停止该方向；
5. **资产可承载：**Forge 已有能力足以完成低成本资格审计，不必先建造另一套完整系统。

项目族隔离、时间切分、严格 evaluator、预算计量和 clean replay 是所有候选的研究纪律。它们提高结论可信度，
但本身不计为候选机制的新颖性。

## 3. 候选一：跨构建系统失败前沿与进展状态

### 3.1 最近工作已经覆盖什么

EnConda-Bench 已把环境配置轨迹拆成规划、感知驱动诊断、反馈修复和执行，并同时评价过程能力与最终可执行性。
因此，“增加过程指标”不是新机制。

EET 从历史问题中提炼结构化经验，在 patch generation 和 selection 阶段按置信度提前终止；
Fail-Fast 使用轨迹前缀和 dense fail-to-pass supervision 预测失败，再通过保留 diff 的重启恢复部分工作；
SWE-Replay 从历史轨迹的关键中间步骤分支，避免每次从头采样。因而“检测失败后早停”“保留中间状态”
和“从 checkpoint 分支”也都已有直接先例。

最新的 run-level failure prediction 审计还表明，聚合 AUROC 可能主要来自任务难度，而不是同一任务内部的
运行失败信号。其公开实验中，早期 within-task AUROC 约为 0.50–0.55；在固定 token 预算回放中，
task-level allocation 优于 abort-only，早停需要约 0.84–0.93 的 within-task AUROC 才开始有益。
这直接否定了把“训练一个失败预测器”作为 Forge 当前最小主线的合理性。

### 3.2 可新增的机制

可保留的增量不是预测“这次会不会失败”，而是定义一个**可验证构建前沿**。在决策点 `t`，状态不压缩为
单一阶段编号，而表示为：

```text
S_t = (V_t, O_t, X_t, D_t, B_t)

V_t: 已由执行证据证实的构建义务
O_t: 根据任务合同仍待满足的义务
X_t: 先前成立但被后续动作破坏或失效的义务
D_t: 当前阻塞前沿的规范化诊断
B_t: 已用和剩余的预算向量
```

构建义务形成偏序，而不是所有项目共享一条刚性流水线。候选公共义务包括：

- 工具链与依赖可用；
- 构建入口或生成后的 build graph 可用；
- 合同目标已物化；
- 交付集合和 target mapping 合法；
- 功能 oracle 通过；
- build provenance 合法；
- clean replay 闭合。

CMake、Make、Autotools adapter 只负责把系统特有观测映射为这些义务的证据，并显式标记
`not_applicable`；它不能把未经执行验证的模型判断写成已证实状态。状态转移
`Delta_t = S_{t+1} - S_t` 用于区分：

- **推进：**新增已证实义务，且没有破坏更早义务；例如从 configure 失败进入真正的 compile 失败；
- **横向变化：**诊断变化，但已证实和待满足义务没有变化；
- **停滞：**状态签名在消耗预算后重复；
- **回退：**原已证实义务进入失效集合，或已通过层次被破坏。

控制器若后续存在，只消费状态及转移来选择动作。它不是创新定义的一部分。可检验的机制主张是：

> 与轮次、token、构建系统、当前 command role 和错误类别相比，可验证构建前沿能否在未见项目族和未来时间段上，
> 更好地区分下一预算单位会推进、横移、停滞还是回退，并由此支持更好的预算动作选择？

### 3.3 是否只是场景迁移或工程组合

以下实现都只属于工程组合：

- 把 `dependency/configure/build/artifact_stage` 编码成一个整数阶段；
- 错误签名重复两次后停止；
- token 达阈值后切换模型；
- 在 CMake、Make、Autotools 前加三个手写分支；
- 使用 learned failure score 复制 FailFast 或 EET；
- 使用文件访问量或推理长度复制 SWE-Replay 的分支点选择。

只有“从系统特有观测到公共构建义务的可验证映射”“非单调偏序状态”和“相对简单状态基线的增量决策价值”
同时成立，才超出场景迁移。严格 S0–S5 终点用于标注结果，不应被包装成新的状态机制。

### 3.4 解决的具体问题

1. 固定 retry/step 上限不能区分仍在解除上游阻塞的轨迹与真正重复的轨迹；
2. 新出现的下游错误常表示推进，基于错误变化的分类器可能把它误判为恶化；
3. 单一阶段编号不能表示回退，也不能表示一个项目同时有多个已满足或待满足义务；
4. pooled failure prediction 容易把项目难度当成运行进展，无法直接支持同一任务内部的继续或切换决策；
5. 原始日志和 Agent 自报缺少跨构建系统可比性，不能稳定成为预算分配信号。

### 3.5 最小可证伪实验

先做零 Provider 的离线机制筛选，不直接实现 controller：

1. 从只读开发轨迹中选择 CMake、Make、Autotools 的非终态决策点；项目族和时间切分在看结果前固定；
2. 由两条独立路径重建状态：确定性 extractor 与人工审计 rubric。人工只核对可见执行证据，不读取隐藏答案；
3. 以实际执行的下一 action block 为条件，预测该动作后的四类状态转移，以及是否到达更深严格层次；
4. 与四组递增基线比较：轮次/已用预算、构建系统与 command role、错误类别、前三者组合；所有模型都接收相同的 action type，避免把动作差异误写成状态增量；
5. 在 family-held-out、time-forward 测试集上报告状态重建一致性、四类转移区分和校准，不用随机行切分；
6. 只有增量价值通过预先冻结的最小有意义效应，才另行设计同预算 F0/A1 干预。

离线相关性不能估计未选择动作的反事实结果，也不能证明 controller 会提高严格成功率；它只负责尽早证伪
“状态没有比简单特征提供更多信息”。
若通过，后续最小干预应固定相同模型、工具和总预算，只改变调度是否读取该状态，并把 controller 自身成本计入总成本。

### 3.6 Forge 资产支持度

Forge 已有资产足以支持资格审计，但还不支持直接宣称方法成立：

- `BuildCommandRecord` 已记录 command role、exit code、timeout、duration 和日志路径；
- Compile Session 已记录构建系统、命令、产物和 replay；
- Agent Workflow 已有 request、step、tool、command、token 和 wall-clock 预算账本；
- failure checkpoint 能绑定消息、环境和剩余预算；
- CandidateVerifier 与 external evaluator 提供 candidate、function、provenance、replay 的可执行证据；
- 历史 CMake/Make/Autotools 轨迹可只读用于 extractor qualification。

主要缺口是：尚无规范状态 schema、构建义务 extractor、状态失效规则、target coverage 观测和面向该问题的
family/time 切分。现有 `command_role` 是 Agent 声明的逻辑阶段，不足以充当权威进展事实。历史 evidence 的任务分布
也不平衡，只能用于资格审计，不能自动变成新方法效果数据。

### 3.7 放弃条件

出现以下任一结果，应停止该方向：

- 同一轨迹重复提取不能得到相同状态，或人工审计无法达到预先冻结的一致性要求；
- 公共义务必须依赖大量项目专用例外，实际退化成三个构建系统各自的状态机；
- 在 family-held-out、time-forward 测试上不优于简单组合基线；
- 增量主要来自 hidden evaluator answer、项目身份或未来信息泄漏；
- 状态能解释历史轨迹，却不能改变任何可执行动作选择；
- 后续 F0/A1 中只节省成本但明显降低固定预算 strict success。

## 4. 候选二：跨构建系统 typed action abstraction

### 4.1 最近工作已经覆盖什么

SWE-agent 已证明 agent-computer interface 会显著影响软件工程 Agent 行为。ALIGN 进一步自动生成增强环境描述和
逐步观测的接口。ToolRosella 把异构代码仓库转换为标准化、可调用并经过测试的工具。

最直接的重合是 GradleFixer。它用 `run_build`、`run_gradle` 和 `change_java_version` 取代通用 Shell，
把高层知识映射为受限、API-like 动作；论文还比较了不同工具组合，并把收益归因于缩小动作空间和减少命令合成错误。
因此，“把 CMake/Make/Autotools 命令封装成工具”只是把 Tool Bridging 移植到另一个构建领域。

### 4.2 仍可保留的支撑机制

如果该方向降级为主线的动作层，可定义跨系统的 Build Action IR：

```text
Action = (intent, subject, preconditions, parameters,
          expected_observation, side_effect_scope, reversibility)
```

例如 `configure_project`、`inspect_targets`、`build_contract_target`、`stage_contract_artifacts` 和
`verify_candidate` 表达共同语义；CMake、Make、Autotools adapter 负责实现，并返回统一的后置证据或
`unsupported/not_applicable`。关键区别是动作具有可检查的前置条件和后置事实，而不只是给 Shell 命令换一个函数名。

它解决两个支撑问题：控制器不能在原始 Bash 字符串上稳定比较动作；同一高层意图在三个构建系统中的具体命令不可直接复用。
但动作 IR 本身仍然不回答何时选择动作，也不自动产生研究贡献。

### 4.3 场景迁移风险

以下结果说明它只是工程接口：

- action 参数仍要求模型提供完整 Bash；
- 每个 adapter 暴露完全不同的 action 和错误类型；
- 公共接口只能覆盖 `run_build` 这类最低共同能力；
- 性能比较只有 typed tools 对 unrestricted Shell，没有 GradleFixer 式 per-system wrapper 强基线；
- 所有效果来自禁止危险动作，而不是跨系统语义可迁移。

能够把它与 GradleFixer 区分开的唯一强主张是：**在两个构建系统上形成的动作选择规律，能通过同一 IR 迁移到未见的第三个系统，
并且优于为该系统单独设计的 wrapper 或提示。** 这个门槛较高，也不是 Forge 当前最小研究路径。

### 4.4 最小可证伪实验

若未来独立研究，应采用 leave-one-build-system-out 的三轮比较：

1. 三个条件共享模型、任务合同、预算和 evaluator：通用 Shell、per-system typed wrappers、公共 Action IR；
2. action schema 和选择策略只在两个构建系统的开发任务上确定，第三个系统只允许实现预先冻结语义的 adapter；
3. 主要终点是 held-out build system 的 strict success；次要终点是非法/无效动作、达到下一进展状态的成本和 adapter 专用分支数量；
4. 公共 IR 必须与 per-system wrappers 比较，不能只击败 Shell。

这项实验需要真实 Agent 行为，零 Provider conformance gate 只能证明 adapter 执行一致，不能证明跨系统迁移。

### 4.5 Forge 资产与缺口

Forge 已有六类 `command_role`、严格 Shell policy、构建系统识别、target contract 和统一 evaluator，可以承载 action
执行与后置检查。但当前唯一执行工具仍是任意 Bash，role 是调用者声明；仓库没有 CMake File API、Make database、
Autotools metadata 的统一 target/capability adapter，也没有 action precondition/effect ledger。

最大技术风险来自 Make 和 Autotools 的可观测性差异。为了达到跨系统统一而不断添加 system-specific escape hatch，
会直接破坏研究主张。

### 4.6 放弃条件

- 公共动作无法覆盖代表性任务，或超过预先冻结比例的动作必须回退任意 Shell；
- shared IR 不优于 per-system wrappers，优势只存在于对 Shell 的比较；
- held-out build system 没有迁移收益；
- adapter 专用参数、分支和异常类型持续增长，使公共 action 只剩名称相同；
- 工具带来的固定执行或验证成本抵消成功率与无效动作收益。

审计结论是：typed action 可以服务于进展状态控制，但当前不应与状态表示并列为论文主创新。

## 5. 候选三：项目族和时间隔离的跨仓库经验迁移

### 5.1 最近工作已经覆盖什么

该方向的文献空间已经明显拥挤：

- Agent Workflow Memory 从历史轨迹归纳可复用 workflow；
- Structurally Aligned Memory 把存储、检索和更新对齐到功能子任务，解决整条 episode 粒度过粗；
- Memory Transfer Learning 发现高层 insight 更易迁移，低层 trace 会产生负迁移；
- EET 用去重后的历史问题构建经验库，并报告零仓库重合的成本结果；
- SetupX 用带 applicability signals、自然语言建议、可执行 atoms 和 telemetry 的 XPU 跨仓库迁移 setup 修复，
  还用 snapshot speculative execution 回滚失败尝试；
- XRepoSkill 比较同一 issue 的成功/失败轨迹，从分歧处生成规则，为规则附加可执行 predicate，在其他轨迹上验证，
  并要求行为在多个仓库重复出现后才进入可迁移 skill；其评测仓库不与学习轨迹池重合；
- BootstrapAgent 把仓库 setup、诊断、验证和修复知识固化为可 clean replay 的 `.bootstrap` contract；
- SWE-Skills-Bench 发现 49 个技能中 39 个没有 pass-rate 增益，版本不匹配的指导会使性能下降；
- VibeMemBench 表明直接注入经过执行验证的经验可以有小幅正向结果，但现有 memory system 在 12 个 solver/system
  组合中有 11 个未超过 matched memory-off，主要损失发生在经验构造和呈现阶段；
- CTIM-Rover 也报告 episodic memory 因噪声和干扰没有超过无记忆 Agent。

因此，“检索其他仓库的成功轨迹”“抽取经验规则”“用 executable action”“要求跨仓库出现”都不再是空白。
项目族隔离和时间切分能防泄漏，但属于评测设计，不是方法机制。

### 5.2 可能剩余的窄机制

若未来重启，应把问题改为**版本漂移下的构建经验准入**。一个经验项至少包含：

```text
E = (applicability predicate, source family/time/environment,
     typed action sequence, verified frontier delta, invalidators)
```

检索命中不等于允许执行。系统需要根据当前工具链、依赖解析、构建系统能力和任务合同检查 applicability；
对过时或冲突经验拒绝准入；对不确定经验从可恢复 checkpoint 中试用，并只在产生已验证的正向状态转移后保留。

这个组合与 XRepoSkill 的 predicate、SetupX 的 signals/atoms/telemetry/snapshot、SWE-Skills-Bench 的版本冲突观察高度相邻。
除非研究重点落在可操作的 temporal invalidation 机制及其负迁移效应，而不是一般 memory RAG，否则仍然只是工程组合。

### 5.3 解决的具体问题

1. 同样的错误文本可能对应不同工具链、依赖版本和构建入口，语义相似检索会给出错误动作；
2. 成功轨迹中的行为可能只是伴随因素，不能据此归因其对成功有贡献；
3. 同仓库历史、相邻 commit 或未来修复容易泄漏 benchmark 答案；
4. 经验在当前模型已经能解决的任务上可能造成干扰，形成负迁移；
5. 依赖源和工具链变化会使过去正确的经验过期。

### 5.4 最小可证伪实验

最低可信比较必须同时包含：

1. 按项目族隔离训练与测试，并按修复或轨迹发生时间做 forward split；测试任务的未来 commit、patch、日志和同族镜像不得进入经验库；
2. 四个条件：无经验、naive similarity retrieval、XRepoSkill/SetupX 风格的 predicate-aware 强基线、带 temporal invalidation 的候选机制；
3. 单独构造版本匹配和版本漂移 strata，固定相同 Agent、预算、工具和 evaluator；
4. 主要终点为 strict success，次要报告负迁移率、经验采纳覆盖率、错误准入、tokens、时间和检索/验证成本；
5. 对“从不注入”的保守策略做覆盖率约束，防止通过拒绝所有经验伪造低负迁移。

只与无记忆 baseline 比较不够，因为最新工作已经给出更强的经验抽取、predicate 和执行验证方法。

### 5.5 Forge 资产与缺口

Forge 的 exact commit、不可变 image identity、ledger、strict evaluator、checkpoint 和 clean replay 适合验证经验是否真的
产生可复现正向转移。但当前没有足够大的跨仓库历史语料、稳定的项目族 taxonomy、版本化依赖解析快照、经验失效标签或
独立的 temporal test cohort。旧 experiment identity 是为其他 estimand 采集的只读 evidence，不能直接改造成经验训练集或新比较分母。

因此，该方向需要先进行大规模数据建设，成本明显高于进展状态资格审计，也更容易被最新工作覆盖。

### 5.6 放弃条件

- 收益只出现在同仓库、相邻 commit、同项目族或随机切分中；
- 相对 predicate-aware 强基线没有增益；
- temporal gate 通过几乎不注入经验来降低负迁移；
- 检索和验证成本抵消 token/时间收益；
- 版本漂移 stratum 中错误准入没有下降，或 strict success 下降；
- 需要读取未来 patch、hidden evaluator 结果或测试仓库历史才能选择经验。

审计结论是：当前不应把跨仓库经验迁移作为主线。它最多是进展状态和 typed action 已稳定后的一项扩展。

## 6. 三候选的最小决策矩阵

评分采用 1–5 分，5 分最好；这是文献与资产审计判断，不是实验结果。

| 候选 | 相对最新工作的新颖性 | 可隔离性 | Forge 资产匹配 | 最小实验成本 | 负结果解释力 | 决策 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 可验证构建前沿/进展状态 | 4 | 4 | 4 | 4 | 5 | 有条件通过；先做零 Provider 状态资格审计 |
| 跨构建系统 Action IR | 2 | 3 | 3 | 3 | 4 | 作为支撑层；不单独立项为主创新 |
| 时间有效的跨仓库经验 | 2 | 3 | 2 | 1 | 3 | 延后；当前不投入数据与系统建设 |

“进展状态”通过的是进入下一轮问题冻结的资格，不是方法有效性。当前仍不能声称：

- 状态表示已经能够稳定重建；
- 它优于简单特征；
- 它能改善 strict success、时间、tokens 或费用；
- typed action 或经验迁移对 Forge 有正向效果；
- Forge 整体优于任何现有自动化编译系统。

## 7. 下一项研究决策

研究负责人需要决定是否把以下问题冻结为下一阶段唯一候选：

> 在不读取隐藏答案的前提下，由可执行构建证据形成的跨构建系统偏序状态，是否比轮次、预算、阶段和错误类别
> 更能解释未见项目族与未来时间段中的短期状态转移，并足以支持后续预算动作实验？

若批准，下一步仍是基础设施与结果分析，而不是 controller 实现：

1. 为零 Provider 状态资格审计新开独立 tracking Issue；
2. 冻结最小构建义务、证据来源、失效规则和 `not_applicable` 语义；
3. 冻结开发/测试项目族与时间切分、简单特征基线、最小有意义效应和放弃规则；
4. 只读提取历史开发轨迹并验证状态可重建性；
5. 审计通过后，再决定是否设计 F0/A1 和新的 formal identity。

任何 Provider、credential、formal attempt、formal evidence 或旧 evidence 变更仍需新的实验身份、预算、停止规则和明确授权。
