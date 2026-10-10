# Forge Research Status

> 面向研究负责人和新会话的当前状态入口。这里只保留当前阶段、核心证据、解释边界和下一项决策；详细工程流水见 `.claude/memory/project.md`，长期研究综合见个人知识库。

## 当前阶段

- 状态：Issue #406 的 formal identity `cpp-jev-end-to-end-canary-v7` 已完成三臂真实端到端 canary，冻结决定为 `proceed_to_formal_end_to_end_comparison_design`。
- 当前工作类型：正式数据采集完成后的结果分析与发布。v7 的 9/9 arm 均分类终结并完成 cleanup；JevGate、AlwaysAgent、RuleGate+Agent 的严格成功分别为 `3/3`、`1/3`、`1/3`。全批次使用 62 次 Agent 请求、678,547 Agent tokens；Jev 使用 3 次请求、4,162 input tokens、费用 `$0.000174804`。
- 已回答问题：在三个已知可恢复的 CMake/Make/Autotools 受控失败上，Jev 分别选择 `configure/build/dependency`，三次均通过代码绑定动作、CandidateVerifier、functional oracle、provenance 和 clean replay，完整 Agent 调用为 0。三臂生命周期、预算和指标采集已经闭合，可以进入独立正式比较设计。
- 当前研究边界：v7 每项目每臂只有一次，项目与故障来自先前资格数据；`3/3` 对 `1/3` 只是强探索信号，不支持非劣、节省比例、显著性、自然失败泛化或 Jev 相对轻量文本分类器的稳定增量。
- 当前机制定位：确定性构建事实与语义失败日志构成决策状态，Jev 只在代码枚举的 typed actions 中选择并经校准门禁直接执行或升级 Agent，任务合同、CandidateVerifier、external evaluator 和 clean replay 负责严格裁判。偏序义务状态 v1 已停止；动态预算控制仍是后续机制候选，本次 canary 未验证。
- 阶段 0 冻结问题：能否构造跨 CMake、Make、Autotools 的进展状态，使其在未见项目族和未来时间段中比轮次、token、阶段和错误类别等简单特征更能解释短期状态转移，并为后续预算动作实验提供足够的增量信息？
- 当前方向文档：`docs/research/2026-10-06-automated-compilation-innovation-landscape.md`。
- Jev 阶段 A 预注册：`benchmarks/preregistrations/cpp-typed-action-benchmark-qualification-v1.md`。
- Jev 阶段 A 资格报告：`benchmarks/reports/cpp-typed-action-benchmark-qualification-v1.md`。
- Jev RuleGate 可辨识性审计：`benchmarks/reports/cpp-typed-action-benchmark-rule-gate-audit-v1.md`。
- Jev v2 预注册：`benchmarks/preregistrations/cpp-typed-semantic-routing-pilot-v2.md`。
- Jev v2 资格报告：`benchmarks/reports/cpp-typed-semantic-routing-pilot-v2.md`。
- Jev 离线资格 candidate 预注册：`benchmarks/preregistrations/cpp-jev-offline-qualification-candidate-v1.md`。
- Jev 离线资格 formal 预注册补充：`benchmarks/preregistrations/cpp-jev-offline-qualification-v1-execution-amendment.md`。
- Jev 离线资格失败报告：`benchmarks/reports/cpp-jev-offline-qualification-v1.md`。
- Jev v4 模型目录门禁报告：`benchmarks/reports/cpp-jev-offline-qualification-v4.md`。
- Jev v5 概率合同失败报告：`benchmarks/reports/cpp-jev-offline-qualification-v5.md`。
- Jev v6 离线资格结果：`benchmarks/reports/cpp-jev-offline-qualification-v6.md`。
- Jev controller replay v2 预注册：`benchmarks/preregistrations/cpp-jev-controller-replay-qualification-v2.md`。
- Jev controller replay v2 结果：`benchmarks/reports/cpp-jev-controller-replay-qualification-v2.md`。
- Jev 端到端 canary v7 预注册：`benchmarks/preregistrations/cpp-jev-end-to-end-canary-v7.md`。
- Jev 端到端 canary v7 结果：`benchmarks/reports/cpp-jev-end-to-end-canary-v7.md`。
- Jev API 合同审计：`docs/research/2026-10-09-jev-api-contract-audit.md`。
- 三候选机制审计：`docs/research/2026-10-09-three-candidate-mechanism-audit.md`。
- 主动诊断机制审计：`docs/research/2026-10-09-active-diagnosis-mechanism-audit.md`。
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

三候选审计曾保留**跨构建系统、由可执行证据构成、允许回退的偏序构建义务状态**，但阶段 0 没有验证出其相对
简单特征的预注册增量价值。后续主动诊断审计又确认，竞争假设、主动测试、信息增益、成本动作选择和停止已有直接
先例；把它们用于构建系统主要是场景迁移。过程评价、早停、checkpoint 分支、domain-specific tools 和跨仓库经验
迁移也已有直接先例。本次检索不是系统综述，不能声称全球首次或排除所有更窄的机制空白。

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
- 主动诊断资产审计覆盖阶段 0 的 30 条 session、18 个项目族和 409 个决策点。264 个 `diagnostic` 动作中有 256 条逐字不同的 Shell 命令；每个状态只观察原策略选择的一个动作，且 manifest 没有独立根因标签，因此不能估计替代探针的信息价值或反事实效果。
- Jev 阶段 A 使用 CMake/Make/Autotools 各 8 个 project family，按 exact commit 时间严格切为 6 个 design、6 个 calibration、12 个 evaluation；每项目构造 5 个状态、每状态 3 个代码绑定动作。48 个 reference build/oracle closure 和 720 次候选动作执行全部闭合，360/360 state/action pair 的 categorical replay 一致，旧 409 点目录覆盖为 409/409。
- Attempt 1 在 `libuv` functional oracle 因 `-std=c11` 隐藏 `pthread_rwlock_t` 后停止并冻结失败记录；Amendment 1 只将该 oracle 改为 `-std=gnu11`，不复用部分 outcome，attempt 2 从全新目录完整重跑并通过。
- 资格通过不等于研究问题可辨识。冻结 RuleGate 只读 `phase_facts` 与候选动作族，在 CMake、Make、Autotools 各 40/40 状态、evaluation 60/60 状态上均为 top-1 安全率 100%、直接执行覆盖 100%、错误率 0%；48 个状态还有两个合格动作。阶段 B 要求同风险下比 RuleGate 多 10 个百分点覆盖，最大可能提升为 0，因此不调用 Jev。
- Jev v2 使用 6 个未进入 v1 的 project family，CMake/Make/Autotools 各 2 个；每项目构造缺失编译输入、失效构建状态和错误 target 三类故障，向路由器暴露完全相同的 phase facts 与动作顺序。12/12 reference closure、144/144 action branch 有界终结，72/72 pair 的 categorical replay 一致；由 strict success 与冻结成本重建的最优动作中，`dependency`、`configure`、`build` 各为 6/18，并各覆盖全部 6 个 project family。
- v2 RuleGate 固定选择 `build`，top-1 与 route-acceptable coverage 均为 `0.3333`，通过 75%/90% 难度门槛；LOPO TF-IDF/逻辑回归为 17/18（`0.9444`），以 1 个样本低于 95% 停止线。唯一错误是 held-out `numactl` 的缺失 `libnuma.c` 状态被判为 `build`。v2 按规则进入 Jev 离线资格，但文本基线已接近饱和，不能据此预期 Jev 会有明显准确率增益。
- Issue #393 已核对 TypeSafe 官方 Quick start、API、Models、Confidence、Choice、State、Python SDK、RetryPolicy 和 Jev 1.13 jaggedness。SDK mock 验证了 `/v1/systemone`、Bearer 鉴权、固定模型、request ID、usage、Choice 概率与 confidence；529 错误在 `max_retries=0` 下只有一次物理请求。Candidate、v2 和阶段 A 相邻回归为 21 passed、2 个显式 Docker gate skipped。
- Issue #395 formal manifest canonical SHA-256 为 `e98b6b3e3a485ca26f3185491f460cc5a6b447f64d7a15d5fac9fcf72daf6616`。零 Provider outcome collection 在 `zstd` calibration replicate 1 的 `missing_compile_input` 处失败关闭；failure evidence 共 20 files，inventory canonical SHA-256 为 `b1c52c54b5ccae8b6e21a841df480fdaba3415d333ee007a937688eba75633fb`。未读取 `jev-apikey.txt` 内容，未创建 Provider evidence。
- Issue #399 v4 的 `/v1/models` 只列出 `jev-latest` 和 `jev-preview`，目录门禁因未显式列出 `jev-1.13.0` 而在 0 模型请求下失败；后续 v5 证明固定版本可以直接调用，因此 v4 是 availability 假阴性，不是模型能力结果。
- Issue #400 v5 成功调用固定 `jev-1.13.0` 并保存 12 个 design 响应；第 13 个响应因序列化概率和超出原 `1e-6` 容差而失败关闭。13 次请求、11,826 input tokens、1,212 output tokens、费用 `$0.000496692` 均被保留，v5 不续跑。
- Issue #401 v6 将原始概率和容差预先冻结为 `0.005`，保存原始值并归一化后分析。Design round 1 为 10/18 top-1、18/18 安全路由、17/18 顺序一致；唯一获准的 prompt 修订后，design round 2 为 18/18 top-1、安全路由和顺序一致。
- v6 calibration 为 18/18 top-1，零观察错误阈值为 `0.6747568477098429`；evaluation 为 18/18 top-1、18/18 顺序一致、18/18 校准后直接执行和 0 次错误，CMake/Make/Autotools 各 6/6。Macro-F1 为 `1.0`、multiclass Brier 为 `0.0003222222`、ECE 为 `0.0072222222`。
- 同一 evaluation 上，固定 `build` RuleGate 为 6/18，TF-IDF/逻辑回归为 17/18。Jev 通过预注册门槛，但 prompt 已明确编码三类受控故障语义，且轻量文本基线接近饱和，不能将 18/18 解释为通用模型优势。
- Issue #403 的 controller replay v1 在首个 `choice_probability_mismatch` 场景按协议失败并永久停止。控制器实际安全升级，但故障夹具概率和为 0.9，先触发 `probability_contract_invalid`；只读全矩阵诊断为 324/324 升级、0 错误直接动作、0 executor 调用，不能替代新的 formal identity。
- Issue #404 v2 只修正故障夹具可辨识性，不修改控制器、阈值、父样本或通过门槛。正式回放复现正常路由 18/18，18/18 调度均等待严格验证，324/324 故障以冻结理由升级，错误直接动作和故障 executor 调用均为 0；CMake/Make/Autotools 各 6 个状态，v1/v6 evidence inventory 前后不变。
- Issue #406 的 v1-v6 依次暴露父常量、workspace、宿主权限、build-system identity、artifact role 和公开头文件 staging 问题，均保持只读。v7 零 Provider qualification 为 3/3 strict；正式 canary 中 JevGate 为 3/3 strict、0 Agent 请求，AlwaysAgent 为 1/3 strict、39 请求/440,480 tokens，RuleGate+Agent 为 1/3 strict、23 请求/238,067 tokens。Jev 三次请求均直接执行且严格通过，总费用 `$0.000174804`。

## 当前研究决策

- 保留合同作为严格裁判，不再把合同 feedback exposure 当作主要修复机制。
- 不修复 `lz4` checkpoint，不继续 mechanism v2 剩余 24 arms，不建立 replacement identity。
- 旧 C0/T1/T2 evidence 永久只读，可作为探索性负结果和研究转向依据，不能解释为 treatment effect。
- 三候选机制审计后的唯一优先候选已完成资格审计并失败；当前偏序进展状态机制按预注册永久停止。typed action 仍只作为支撑动作层；此前审计的跨仓库经验迁移没有形成足够的新机制。
- Issue #382 只读资格审计已完成；不得结果后调整切分、阈值、义务、诊断模式或模型来挽救 v1。
- Issue #385 主动诊断候选按 `abandon_active_diagnosis_as_novel_mechanism` 停止；不把已有 hypothesis/EIG/POMDP/cost-aware testing 组合重新表述为 Forge 新机制。
- Issue #389 阶段 A 的 `proceed_to_jev_offline_qualification` 只表示 benchmark 可执行门槛通过；后续零 Provider RuleGate 审计覆盖该进入决定，当前最终决定为 `stop_jev_provider_qualification_and_redesign_benchmark`。
- 不在已被 RuleGate 完全解出的阶段 A v1 上调用 Jev 或实现 controller；该停止决定保持不变，v6 使用的是另一个具有异最优动作标签的受控故障 benchmark。
- 当前 v1 的 evaluation split 已被 RuleGate 审计暴露，不能在修订动作或状态后继续作为确认性模型评测集。Issue #391 v2 使用了 6 个新项目族，但它是受控故障难度 pilot，不是时间后移的确认性模型评测；后续 Provider 评测必须另行冻结项目族与时间隔离，或把 v2 锁定为一次性 evaluation 并使用完全独立的 design/calibration 数据。
- Issue #391 v2 已按冻结规则通过零 Provider 难度门禁，决定为 `proceed_to_jev_offline_qualification`；该决定只授权规划独立的 Jev 离线资格 identity，不把 #391 转成 Provider 实验，也不允许修改或重跑 v2 outcome。
- Issue #393 candidate 只冻结后续 Provider 实验的前置合同，不是 formal Provider attempt。使用固定 `jev-1.13.0`，同一请求包含动作正序与逆序 Choice，SDK retry 为 0，总预算候选为 72 请求、1,000,000 input tokens、0.042 美元。
- Issue #393 的 evaluation 做到项目族隔离，但不满足全局 commit 时间后移，且 v2 标签对研究者可见；后续结果只能解释为冻结受控故障 holdout，不能支持跨时间、自然失败总体或开放世界泛化。
- Issue #395、#399、#400 与 #401 均已消费且永久只读，禁止重跑、续跑、补齐、替换或覆盖 evidence。v4/v5 的基础设施失败和 v6 的正向资格结果必须同时保留。
- v6 决定为 `proceed_to_controller_replay_qualification`，Issue #404 v2 决定为 `proceed_to_end_to_end_canary`，Issue #406 v7 已进一步决定 `proceed_to_formal_end_to_end_comparison_design`。下一阶段必须使用新的未见项目族、独立 identity 和预注册联合判据；不得复用 v7 canary 样本估计 treatment effect。
- 项目族与时间隔离属于所有候选的评测纪律，不单独构成经验迁移的新机制。
- 动态预算控制仍属于整体机制候选，但尚未独立验证；正式语义路由比较完成前不直接实现或宣称其有效。模型路由、typed tools、checkpoint 分支和早停也不能各自表述为通用创新。
- 新实验必须重新冻结有限预算向量、开发/测试项目隔离、严格成功、删失效率指标、最小有意义效应和分析顺序；旧 identity 的“无 token ceiling”不沿用为成本研究设计。

## 解释边界

当前证据可以支持：

- 合同裁判能提供比 Shell exit code 更严格、可复现的自动化编译终点；
- 固定 Flow、动态交互和重复尝试在既有论文中通常比一次性生成更强，但更多轮次并不保证单调收益；
- 失败轨迹可能主导时间和 token 成本，因此预算分配是有实际依据的研究问题；
- Forge 现有只读轨迹足以重建 v1 进展状态并执行项目族/时间隔离的 observed-action 资格审计；
- 在固定语料、特征、模型和门槛下，v1 进展状态没有足够的独立转移信息来支持后续预算动作实验。
- Forge 现有轨迹能描述已执行的诊断过程，但缺少同状态替代动作结果与独立根因，不能支持主动诊断动作价值估计。
- Forge 已能执行跨三种构建系统的闭集候选动作 outcome matrix，并在隔离副本中获得可重复标签；这是 benchmark 基础设施证据。
- 当前 v1 的确定性阶段事实已经完全决定安全推进动作，语义日志没有可测的增量决策空间，不能用于评价 Jev 相对 RuleGate 的提升。
- v2 在相同阶段事实下形成了跨三种构建系统的异最优动作标签，证明语义失败日志相对 coarse RuleGate 有决策信息；它支持测试 Jev 的动作判断，不支持 Jev 已有效。
- Forge 已具备与官方 Jev API 对接的确定性请求/响应适配和失败关闭 mock，且可以在不读取真实 credential 的情况下验证模型版本、概率、confidence、usage、request ID、顺序与零 retry 合同。
- 固定 `jev-1.13.0` 在 v6 的一次性受控故障 evaluation 上正确选择 18/18 个最低成本安全动作，正反候选顺序 18/18 一致；项目族隔离校准以 18/18 覆盖获得 0 次观察错误。
- v6 的正式模型调用满足 72 请求、1,000,000 input tokens 和 `$0.042` 的冻结预算上限，实际为 72 请求、83,210 input tokens 和 `$0.00349482`。
- 冻结 v6 响应可通过最小控制器复现 18/18 路由；控制器只执行代码绑定候选，不能生成 Shell 或宣告终态成功，并在 324/324 个冻结故障回放中升级 Agent、零故障 executor 调用。
- v7 canary 证明同一控制器可在真实 Shell 和严格终点下闭合三种构建系统；Jev 的 `configure/build/dependency` 三次直接执行均严格成功，并在该三项目 canary 中避免完整 Agent 调用。

当前证据不能支持：

- 进展感知预算控制优于固定 Flow，或任何具体节省比例；
- 所有可能的进展状态表示都无效，或 v1 在更广项目总体、其他模型和新轨迹上必然无增量；
- 任何未选择动作的反事实效果、动作选择改进或 controller treatment effect；
- 主动诊断对自动化构建没有产品或 benchmark 价值，或世界范围不存在更窄的构建诊断机制空白；
- 结构化合同反馈的总体效应、统计显著性、无效或等效；
- Forge 整体优于 CXXCrafter、CompileAgent、BuildBench 或其他系统；
- Provider/模型能力排名，或 verifier、路由、搜索、领域工具的通用首创性；
- 从成功案例均值推断总体时间/成本，或把 canary/qualification 当作 treatment evidence。
- v6 之外自然失败、开放世界、跨时间数据上的 Jev 准确率或校准迁移，以及任何通用模型排名；当前 evaluation 是 6 个项目族、三类受控故障。
- Jev controller 在未见项目族上的严格成功率非劣、完整 Agent 调用减少、token/费用/墙钟节省比例或 treatment effect；v7 虽有真实 Shell 和端到端对照，但样本已参与先前资格且每格仅一次。
- Jev 相对规则或轻量文本分类器具有稳定的实质增量；当前 TF-IDF/逻辑回归已达到 17/18，且 prompt 修订编码了三类故障语义。
- v2 在自然发生的真实失败总体中也有相同准确率、标签分布或可迁移性；当前只是 6 个项目、三类受控故障的资格 pilot。
- Issue #393 的 SDK mock 本身不能说明真实 API 能力；真实 API 可达、固定模型执行和离线选择结果由 v5/v6 单独证明，但仍不能说明 controller 能节省成本。
- Issue #395 的数据资格失败不能说明 Jev 选择正确或错误，也不能用于估计 calibration/evaluation 指标；唯一正式结论是当前 zstd fault fixture 不合格且 Provider 阶段被正确阻断。

## 当前允许与禁止

允许：

- 只读核验论文、公开实现、仓库报告、manifest、ledger 和冻结 evidence；
- 编写、审阅和发布 Issue #381 的版本化研究综述与状态交接；
- 对进展状态、typed action abstraction 和跨仓库经验迁移做文献与机制比较；
- 发布并审阅 Issue #382 和 #385 的版本化报告，保持失败结果与冻结输入可重建；为下一研究问题重新做文献与机制审计。
- 只读核验 Issue #389/#391/#393/#395/#399/#400/#401/#403/#404/#406 的 manifest、报告与冻结 evidence，并发布 Issue #406 的结果交接。
- 为 `AlwaysAgent`、`RuleGate+Agent`、`JevGate+Agent` 设计独立正式比较，预先冻结未见项目族、时间隔离、Provider、预算、停止规则、最小效应和严格成功/成本联合判据。

禁止：

- 修改、移动、删除、重新生成、续跑、重跑、replacement 或 backfill 任何历史 experiment identity/evidence；
- 修复后继续 mechanism v2，创建 sequence 13/checkpoint 5 evidence，或把旧结果导入新比较；
- 对不完整 mechanism v2 执行 primary/secondary test 或声称 treatment effect；
- 在新 identity、项目、预算、停止规则和明确授权冻结前读取 credential、调用 Provider、创建 formal attempt 或写 formal experiment evidence。
- 对进展状态 v1 做结果后调参、改切分、改标签或改阈值，或据此直接实现 controller/F0/A1。
- 在当前 v1 上调用 Jev/通用 LLM、调整 RuleGate、继续阶段 B-D 或实现 controller；当前 evaluation 已暴露且 RuleGate 饱和。
- 把阶段 A 的 100% replay 一致率解释为模型效果、成本收益或语义路由成功。
- 修改、重跑、replacement、backfill Issue #391 v2 的项目、故障、动作、成本、阈值、outcome 或报告；在 #391 identity 下读取 credential、调用 Provider 或实现 controller。
- 重跑、续跑、补齐、替换或覆盖 `cpp-jev-offline-qualification-v1/v4/v5/v6`，或把任一失败 identity 的部分响应导入其他 identity。
- 重跑、续跑、替换或覆盖 `cpp-jev-controller-replay-qualification-v1/v2`，或删除 v1 失败 evidence；后续端到端实验不得复用 v6 或 replay identity。
- 重跑、续跑、替换或覆盖 `cpp-jev-end-to-end-canary-v1` 至 `v7`，或把 qualification/canary 结果解释为正式 treatment effect。
- 在新的正式比较 identity、未见项目族、Provider、预算、停止规则和授权冻结前执行真实动作或调用 Provider。

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
- Issue #382 结果 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/384`；基于 PR #383 的研究审计分支，CI 与评审状态以 PR 为准，不在本阶段合并。
- Issue #385：`https://github.com/WWFXL/Forge-AutoCompiler/issues/385`。
- Issue #385 主动诊断机制审计：`docs/research/2026-10-09-active-diagnosis-mechanism-audit.md`。
- Issue #385 审计 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/386`；基于 `yiwei/382-progress-state-qualification`，依赖 PR #384，CI 与评审状态以 PR 为准，不在本阶段合并。
- Issue #395：`https://github.com/WWFXL/Forge-AutoCompiler/issues/395`。
- Issue #395 formal manifest：`benchmarks/manifests/cpp-jev-offline-qualification-v1.json`。
- Issue #395 冻结 failure evidence：`.compile-sessions/benchmark-evidence-jev-offline-qualification-v1`。
- Issue #395 失败报告：`benchmarks/reports/cpp-jev-offline-qualification-v1.md`。
- Issue #389：`https://github.com/WWFXL/Forge-AutoCompiler/issues/389`。
- Issue #389 分支：`yiwei/389-typed-action-benchmark`，基线 `eb03a873`，实现提交 `87a36c32`；中文 PR #390 已创建并回读，以 `yiwei/387-thesis-research-bar` 为 base，通过 `Closes #389` 关联 Issue。CI 与评审状态以 PR 为准，本阶段不合并。
- Jev 阶段 A JSON 报告 SHA-256：`bdbf2bca0f76c978630d58f618202cc9fb61d968ed287dd74a2f29f5292151d6`。
- RuleGate 可辨识性 JSON 报告 SHA-256：`7ca7e47846ce77001dcf12c99e2615e74e6d2f0803f8ea5e04439db331c5e8c6`。
- Issue #391：`https://github.com/WWFXL/Forge-AutoCompiler/issues/391`；分支 `yiwei/391-semantic-routing-pilot`，结果盲执行 revision `b8b68b1a5457e0097c3d4d1a8213595c73178ece`。
- Jev v2 JSON 报告 SHA-256：`ea2e126e81cfca374900436fa670015b28b3cc3f9d8c83e746ae2c92d2badfed`；Markdown SHA-256：`6220d059fa03e182f7e86c62b2688d91893c1ddbf43b163fd3a9fe8409b95e63`。
- Issue #393：`https://github.com/WWFXL/Forge-AutoCompiler/issues/393`；分支 `yiwei/393-jev-offline-qualification`，基线 `8c36e2ea`。
- Jev 离线资格 candidate manifest canonical SHA-256：`920ee99c3b63218436fdbfdcb86ead0d4bfecb02c833d1652244b9b92a40b583`；后续真实 Provider 执行已通过独立 v4-v6 identities 完成并保留失败链。
- Issue #399：`https://github.com/WWFXL/Forge-AutoCompiler/issues/399`；v4 JSON 报告 SHA-256 `85e62c6fa8b6f4c1d9dc1eabd2808b12ec5cc2d30e5ceb6d16ec9604b6a82909`。
- Issue #400：`https://github.com/WWFXL/Forge-AutoCompiler/issues/400`；v5 JSON 报告 SHA-256 `42512a051c99cbf46279ceb395adc947f9eb27c029e770a7355cd713f8d41327`。
- Issue #401：`https://github.com/WWFXL/Forge-AutoCompiler/issues/401`；v6 manifest canonical SHA-256 `4d17426ecee591584bdfd6d1520c454d3e402d5da894ae54ec7c0841ba067eee`。
- Jev v2-v6 结果 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/402`；以 `yiwei/395-jev-offline-execution` 为 base，依赖 PR #396，CI 与评审状态以 PR 为准。
- Jev v6 冻结 evidence：`.compile-sessions/benchmark-evidence-jev-offline-qualification-v6`；JSON/Markdown 报告 SHA-256 分别为 `7a9d440acd0dc1b51eea7470563fc263b518fffd428b2e4bd6c3967ab696b2c6`、`cf40eb89063e1757bf78c7d3dca3458afdec2c2f240537e4fab07338483b9bc3`。
- Issue #403：`https://github.com/WWFXL/Forge-AutoCompiler/issues/403`；v1 failure evidence 位于 `.compile-sessions/benchmark-evidence-jev-controller-replay-qualification-v1`，inventory canonical SHA-256 为 `e11cf5aa77587606ec70e5454cbe8b9c2574a34f6c1249660096e5c469863538`。
- Issue #404：`https://github.com/WWFXL/Forge-AutoCompiler/issues/404`；v2 manifest canonical SHA-256 为 `309b02edf34db238e318e2b5f9fbe945692e0d946edb181f76028f1c5bd4ce28`。
- Jev controller replay v2 evidence：`.compile-sessions/benchmark-evidence-jev-controller-replay-qualification-v2`；inventory canonical SHA-256 为 `8a07709058f998b7820677b86754027b17c8e015da2579c41c96783edc80699c`；JSON/Markdown 报告 SHA-256 分别为 `71a8102a5ca89ea194d77d7d853cf413e5c45d3438f4933bdc70e226f27bdfb7`、`ae27029ccd57a346420563fe2d99c057608bdc15a9febcba2b36b99daad5bb4f`。
- Jev controller replay 结果 PR：`https://github.com/WWFXL/Forge-AutoCompiler/pull/405`；base 为 `yiwei/401-jev-offline-v6`，依赖 PR #402，通过 `Closes #403` 与 `Closes #404` 关联失败链和最终结论；backend unit 与 frozen benchmark CI 全绿。
- Issue #406：`https://github.com/WWFXL/Forge-AutoCompiler/issues/406`；v7 manifest canonical SHA-256 为 `60355130979a192f256b47411a2c4b2ca51754a72e091d5d7b0753e871f853cb`。
- Jev 端到端 canary v7 evidence：`.compile-sessions/benchmark-evidence-jev-end-to-end-canary-v7`，28 files / 385,384 bytes，inventory canonical SHA-256 `837f0d2702c5e2c959522a51abcd15ea56b079c198a130c2a7454960c9f293d9`；JSON/Markdown 报告 SHA-256 分别为 `2fdbf0d64c3254b4e4dedc39c2f59b525febb0b0ad0d5dd25ed20e2858597ef4`、`13dd8346e7d85844958e4a48d0d3134c8bb9377ed2bce2bddb598144df16080c`。
- 进展状态 v1 manifest canonical SHA-256：`9340a10f005a9a90f980ac45356e8c13d00f35a7b095e30a68ccde610944ee6d`。
- 进展状态 v1 JSON 报告 SHA-256：`b4b682d8699bdbcf5e768736e525ac13109675db64971a23c3007dafa2442a4d`。

## 下一项工作

Issue #406 v7 已得到三臂真实端到端 canary 的关键结论。下一项工作是设计独立正式比较：使用未见项目族和时间隔离的 exact commit，
保持 `AlwaysAgent`、`RuleGate+Agent`、`JevGate+Agent` 的强模型、工具、初始状态、总预算和严格裁判一致，预注册严格成功非劣与
成本下降的联合判据、最小有意义效应、聚类分析和停止规则。

动态预算控制在该正式语义路由比较得到可重复结果前保持候选状态；不能把 v7 的 `3/3`、0 Agent 请求或观察到的时长差直接写成
成功率提升或成本节省结论。
