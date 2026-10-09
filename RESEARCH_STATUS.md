# Forge Research Status

> 面向研究负责人和新会话的当前状态入口。这里只保留当前阶段、核心证据、解释边界和下一项决策；详细工程流水见 `.claude/memory/project.md`，长期研究综合见个人知识库。

## 当前阶段

- 状态：Issue #382 的阶段 0 离线资格审计已完成；当前偏序进展状态机制未通过预注册门槛，按停止规则放弃，不进入 controller 或预算动作实验设计。旧“合同反馈驱动修复”不再作为毕业论文主线，mechanism v2 永久停止。
- 当前工作类型：结果分析与研究交接。状态 extractor、人工重建和隔离比较已经闭合；当前等待选择新的可证伪研究机制，没有新的主线或实验 identity 获准。
- 已回答问题：由执行证据形成的 v1 偏序构建义务能够确定性区分推进、横向变化、停滞和回退，但在本次未见项目族与未来时间隔离测试中，相对轮次、预算、构建系统、动作和错误类别没有达到预注册的增量信息门槛。
- 合同定位：任务合同、CandidateVerifier、external evaluator 和 clean replay 继续作为统一裁判与支撑性基础设施，不再把 C0/T1/T2 feedback projection 作为主要创新。
- 冻结研究问题：能否构造跨 CMake、Make、Autotools 的进展状态，使其在未见项目族和未来时间段中比轮次、token、阶段和错误类别等简单特征更能解释短期状态转移，并为后续预算动作实验提供足够的增量信息？
- 当前方向文档：`docs/research/2026-10-06-automated-compilation-innovation-landscape.md`。
- 三候选机制审计：`docs/research/2026-10-09-three-candidate-mechanism-audit.md`。
- 阶段 0 预注册：`benchmarks/preregistrations/cpp-cross-build-progress-state-qualification-v1.md`。
- 阶段 0 结果：`benchmarks/reports/cpp-cross-build-progress-state-qualification-v1.md`。
- 历史方向与审计：`docs/research/2026-09-29-automated-compilation-thesis-direction.md`、`docs/research/2026-09-29-contract-driven-repair-design-audit.md`。

## 文献定位

本轮定向检索覆盖 CXXCrafter、CompileAgent、BuildBench、Repo2Run、GradleFixer、EnConda-Bench、
EvoConfig、ComBench、PhantomRun、EvidenT，以及 SWE-Replay、EET、FailFast、XRepoSkill、SetupX、
BootstrapAgent、SWE-Skills-Bench、VibeMemBench 等轨迹控制、动作接口和经验迁移工作。

已确认不能单独作为新贡献的表述：

- 用 LLM/Agent 自动编译 C/C++，或在固定 Workflow 中加入 Agent；
- 多 Agent 讨论、原始日志反馈、迭代修复和证据历史；
- 独立 verifier、任务规格、分层成功判据和 clean replay；
- 增加领域专用工具、更多推理轮次或更多并行采样；
- 只报告成功率、成功案例平均时间、token 或费用。

机制审计后的可保留空白进一步缩小为：本次语料中尚未发现使用**跨构建系统、由可执行证据构成、允许回退的偏序
构建义务状态**，并验证其相对轮次、预算、阶段和错误类别的增量决策价值。过程评价、早停、checkpoint 分支、
domain-specific tools 和跨仓库经验迁移都已有直接先例。本次检索不是系统综述，不能声称全球首次。

## Forge 已有证据

- Forge 已具备 Compile Session、failure checkpoint、严格 candidate/functional/provenance 判定、external evaluator、ledger 和 clean replay，可作为新控制策略的统一执行与测量基础。
- Stage C v8 四任务 strict、S0-S5、bitwise 和 cleanup 均为 4/4；37 requests / 279,988 tokens。它是工程 canary，不是方法比较。
- 历史 behavioral v2 为单 CMake controlled fault，baseline 3/6、treatment 5/6；multi-checkpoint v3 为同一 fault family，baseline 4/6、treatment 6/6。两者只支持探索性假设。
- Opaque provenance replication 为 12/12 pairs 终结、7/12 endpoint-censored；baseline 0/12、treatment 6/12，只有 5 个 eligible pairs，`primary_test=null`。
- Runtime v3 三臂 qualification 在 delivery/target 与 provenance 两个真实 Docker parent checkpoint 上闭合 candidate、oracle、external evaluator、clean replay 和 cleanup。它只证明基础设施可执行。
- Mechanism v2 唯一 formal batch 在 12/36 arms、4/12 checkpoints 后因 `lz4` target-mapped artifact 基数不兼容永久失败。冻结 evidence 为 70 files / 689,742 bytes，inventory SHA-256 `5c885b2a...b9d11`，75 requests / 1,068,534 total tokens，失败后 0 managed resources。
- Mechanism v2 的两个完整项目中，delivery/target 三臂均成功，provenance 三臂均为 0；其余 8 checkpoints 不填零，三个比较的识别区间均为 `[-2/3, +2/3]`，`primary_test=null`、`secondary_test=null`。
- 当前证据链表现为：单一 delivery fault 的早期 pilots 有正向探索信号；扩大到 provenance 后可辨识性不足；mechanism v2 已完成的四个 checkpoints 由 fault stratum 而非反馈条件区分。它支持停止该主线，不支持“反馈无效”或等效性结论。
- 进展状态 v1 使用 6 个开发项目族/100 个决策点和 12 个未来未见项目族/309 个决策点；两组均观察到四类转移。12 点人工重建的 216 个 obligation 字段、24 个诊断字段和转移标签一致率均为 1.0。
- `progress_state` 相对 `simple_combined` 的项目族宏平均 log loss 差值为 `-0.0016` nat，bootstrap 95% 区间为 `[-0.1033, 0.1143]`，仅 7/12 项目族改善；Make 改善 `-0.1390`，CMake 恶化 `+0.0133`，Autotools 恶化 `+0.1059`。最小改善、区间和跨系统三项门槛失败。

## 当前研究决策

- 保留合同作为严格裁判，不再把合同 feedback exposure 当作主要修复机制。
- 不修复 `lz4` checkpoint，不继续 mechanism v2 剩余 24 arms，不建立 replacement identity。
- 旧 C0/T1/T2 evidence 永久只读，可作为探索性负结果和研究转向依据，不能解释为 treatment effect。
- 三候选机制审计后的唯一优先候选已完成资格审计并失败；当前偏序进展状态机制按预注册永久停止。typed action 仍只作为支撑动作层；此前审计的跨仓库经验迁移没有形成足够的新机制。
- Issue #382 只读资格审计已完成；不得结果后调整切分、阈值、义务、诊断模式或模型来挽救 v1。
- 项目族与时间隔离属于所有候选的评测纪律，不单独构成经验迁移的新机制。
- 当前不得设计固定 Flow `F0` 与进展感知预算控制 `A1`。模型路由、typed tools、checkpoint 分支和早停不能各自表述为创新。
- 新实验必须重新冻结有限预算向量、开发/测试项目隔离、严格成功、删失效率指标、最小有意义效应和分析顺序；旧 identity 的“无 token ceiling”不沿用为成本研究设计。

## 解释边界

当前证据可以支持：

- 合同裁判能提供比 Shell exit code 更严格、可复现的自动化编译终点；
- 固定 Flow、动态交互和重复尝试在既有论文中通常比一次性生成更强，但更多轮次并不保证单调收益；
- 失败轨迹可能主导时间和 token 成本，因此预算分配是有实际依据的研究问题；
- Forge 现有只读轨迹足以重建 v1 进展状态并执行项目族/时间隔离的 observed-action 资格审计；
- 在固定语料、特征、模型和门槛下，v1 进展状态没有足够的独立转移信息来支持后续预算动作实验。

当前证据不能支持：

- 进展感知预算控制优于固定 Flow，或任何具体节省比例；
- 所有可能的进展状态表示都无效，或 v1 在更广项目总体、其他模型和新轨迹上必然无增量；
- 任何未选择动作的反事实效果、动作选择改进或 controller treatment effect；
- 结构化合同反馈的总体效应、统计显著性、无效或等效；
- Forge 整体优于 CXXCrafter、CompileAgent、BuildBench 或其他系统；
- Provider/模型能力排名，或 verifier、路由、搜索、领域工具的通用首创性；
- 从成功案例均值推断总体时间/成本，或把 canary/qualification 当作 treatment evidence。

## 当前允许与禁止

允许：

- 只读核验论文、公开实现、仓库报告、manifest、ledger 和冻结 evidence；
- 编写、审阅和发布 Issue #381 的版本化研究综述与状态交接；
- 对进展状态、typed action abstraction 和跨仓库经验迁移做文献与机制比较；
- 发布并审阅 Issue #382 的版本化报告，保持失败结果与冻结输入可重建；为下一研究问题重新做文献与机制审计。

禁止：

- 修改、移动、删除、重新生成、续跑、重跑、replacement 或 backfill 任何历史 experiment identity/evidence；
- 修复后继续 mechanism v2，创建 sequence 13/checkpoint 5 evidence，或把旧结果导入新比较；
- 对不完整 mechanism v2 执行 primary/secondary test 或声称 treatment effect；
- 在新 identity、项目、预算、停止规则和明确授权冻结前读取 credential、调用 Provider、创建 formal attempt 或写 formal experiment evidence。
- 对进展状态 v1 做结果后调参、改切分、改标签或改阈值，或据此直接实现 controller/F0/A1。

## 权威入口

- Mechanism v2 formal manifest：`benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-formal-execution.json`。
- Mechanism v2 冻结 evidence：`.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent`。
- Mechanism v2 失败审计：`benchmarks/reports/cpp-contract-driven-repair-mechanism-v2-formal-failure-audit.md`。
- Runtime v3 qualification：`benchmarks/preregistrations/cpp-runtime-v3-three-arm-zero-provider-qualification.md`。
- Stage C v8 审计：`benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.md`。
- 2026-10-06 已按 `search_notes -> read_note` 核对个人知识库论文索引、CXXCrafter 和 CompileAgent 解读；本轮不修改知识库。
- 2026-10-07 已按 `search_notes -> read_note` 核对个人知识库笔记“Forge 毕业论文方向与契约驱动修复设计”；本轮不修改知识库。
- 2026-10-09 已按 `search_notes -> read_note` 核对个人知识库“2025-2026 自动化编译论文索引”和旧方向设计原文；本轮不修改知识库。
- Issue #382：`https://github.com/WWFXL/Forge-AutoCompiler/issues/382`。
- 进展状态 v1 manifest canonical SHA-256：`9340a10f005a9a90f980ac45356e8c13d00f35a7b095e30a68ccde610944ee6d`。
- 进展状态 v1 JSON 报告 SHA-256：`b4b682d8699bdbcf5e768736e525ac13109675db64971a23c3007dafa2442a4d`。

## 下一项工作

完成 Issue #382 报告的代码评审与发布后，研究负责人需要选择新的研究问题。候选必须提出相对现有工作的新增机制和
最小可证伪实验；不得把 v1 调参、typed action 工程层、简单阈值/cascade/早停或仅增加项目族/时间隔离重新包装为主线。
当前不实现 controller，不创建新 formal identity。
