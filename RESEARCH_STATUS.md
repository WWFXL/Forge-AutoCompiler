# Forge Research Status

> 面向研究负责人和新会话的当前状态入口。这里只保留当前阶段、核心证据、解释边界和下一项决策；详细工程流水见 `.claude/memory/project.md`，长期研究综合见个人知识库。

## 当前阶段

- 状态：Issue #379 已完成 mechanism v2 唯一 formal batch 的只读失败审计。该 identity 在完成 12/36 arms、4/12 checkpoints 后因 `lz4` checkpoint target-mapped artifact 基数不兼容而永久失败；禁止续跑、重跑、replacement、backfill 或 evidence 修改。
- 当前工作类型：结果分析与基础设施失败审计。版本化报告冻结不完整 batch、预注册缺失数据边界和 checkpoint builder 根因；它不产生新的实验 observation，也不构成 treatment effect 证据。
- 研究目标：围绕自动化编译形成范围适中、可验证、可复现的毕业论文贡献；Forge 的 Agent Workflow Node 与 Multi-Agent 视为研究基础设施，CXXCrafter 视为相关工作之一。
- 首选方向：面向自动化编译的契约驱动修复，组合可恢复失败状态、确定性候选验证反馈和分层正确性判定。
- 当前主问题候选：在相同编译失败状态、模型、工具和预算下，C0 普通失败、T1 合同 finding、T2 finding + 抽象 repair goal 三种反馈暴露是否产生不同的严格候选转换率，并减少重复或无效动作？
- 方向文档：`docs/research/2026-09-29-automated-compilation-thesis-direction.md`。
- 设计审计：`docs/research/2026-09-29-contract-driven-repair-design-audit.md`。

## 文献定位

本次定向检索覆盖 CXXCrafter、CompileAgent、BuildBench、ComBench、EnConda-Bench、GradleFixer、EvidenT、
Repo2Run、EvoConfig、PhantomRun、跨 ISA Build-bench、Exact Feedback、SpecHarness 和 FDE-Bench。

已确认不能单独作为创新的表述：

- LLM 自动编译 C/C++、Workflow 中嵌入 Agent、多 Agent 构建诊断；
- 原始日志反馈后的迭代修复、证据保留、领域受限工具；
- 独立 verifier、规格权威、deterministic feedback、clean replay；
- 过程级或分层指标、完整文件与 patch 的一般比较。

本次检索不是严格系统综述。arXiv API 曾出现 timeout/429；因此只能表述为“本次检索语料中未发现直接
覆盖 Forge 候选组合”，不能声称全球首次。

## Forge 已有证据

- Behavioral v2：同一个 CMake checkpoint，baseline 3/6、treatment 5/6，配对差 `+2/6`。仅为单 provider、单仓库、单 controlled fault 的探索性机制结果。
- Multi-checkpoint v3：CMake/Make/Autotools 三个 case，baseline 4/6、treatment 6/6，case 等权 macro-average 为 0.667 vs 1.000。三个 case 仍同属 `artifact_staging_missing` fault family。
- Opaque provenance replication：12/12 pairs 终结，但 7/12 endpoint-censored；baseline 0/12 conversion，treatment 6/12 conversion 且六次 clean replay 通过。只有五个 eligible pairs 和 2/6 完整 project blocks，`primary_test=null`。
- Stage C v8：四任务 strict、S0-S5、bitwise、cleanup 均 4/4；37 requests / 279,988 tokens。`libjpeg-turbo` 有一次 `target_mapping_invalid -> 同 attempt 修复 -> 成功`。这是工程 canary，不是 Forge/CXXCrafter 或 baseline/treatment 对照。
- 生产 verifier 已能生成确定性、有界、结构化的 delivery、artifact、target mapping 和 functional-oracle findings；candidate verification、external evaluator 与 clean replay 保持独立。
- Runtime v3 三臂 qualification：delivery/target 与 provenance 两个真实 Docker parent checkpoint 均派生 C0/T1/T2；六个 arm 的 candidate、functional oracle、provenance、external evaluator v3、clean replay 和 cleanup 全部闭合，最终复跑为 `2 passed in 75.93s`，运行前后 0 managed orphan。该结果只证明基础设施可执行，不是 treatment evidence。
- Availability qualification：绑定 `main@09d7ff36` 与 execution manifest `cf21d2c...7839` 的唯一 `deepseek-flash` request 在首个 attempt 通过；39 input / 19 output / 58 total tokens，exact response 与 model identity 匹配，0 tool side effects、0 managed resources。Marker SHA-256 为 `8527d64a...8bee`；这只证明固定端点在该时点完成往返。
- Formal execution failure：manifest `3a843799...5829f` 在 clean-main preflight 后启动；sequence 1（`rnnoise-0.1.1:delivery_target / T2`）以 5 requests / 44,561 input / 8,423 output / 52,984 total tokens 达到 strict endpoint，S0-S5、clean replay 与 cleanup 均通过。随后 `_update_claimed_marker` 的 mapping/keyword 调用合同不一致导致 attempt 与 batch marker 无法封口，schedule 在 sequence 2 前停止。冻结 evidence 为 9 files / 66,466 bytes，inventory SHA-256 `24019a37...2fb5`，失败后 0 managed resources。该单 arm 不支持 treatment effect。
- Mechanism v2 candidate：从零派生 36 个新 opaque clone IDs 与 36 个新 evaluation IDs，和 v1 均为零重叠；任务、condition 顺序、预算、停止规则与分析规则不变。执行前的 Marker repair 四类终态门禁与双 stratum Docker lifecycle gate 通过；v1 sequence 1 永久排除于 v2 分析。该 qualification 只证明新身份基础设施当时可执行。
- Mechanism v2 clean-main preflight：`main == origin/main == 70b257c840f4065285c047ba6207ffe99f8dcb36`，candidate canonical `40ea4706...e25f0d`、image `sha256:adbef4a...758b1`、v1 inventory `24019a37...2fb5`、新 evidence absence 和 0 managed resources 全部闭合；credential 未读取。
- Mechanism v2 release-bound identity：PR #370 四项 CI 全绿并 squash-merge 为 `main@646ff59a67b27038b241358261bc92adcb100eb6`；canonical `9ce0b7eb...e08197`，clean-main preflight 继续确认冻结镜像、v1 inventory、新 evidence absence 和 0 managed resources，credential 未读取。
- Mechanism v2 availability qualification：PR #372 四项 CI 全绿并 squash-merge 为 `main@12681ffb0fd2997e2f572f3355e02b50a1b79744`；manifest canonical `71d2f5e2...41065`。唯一 `FORGE_READY` request 在首个 attempt 通过，39 input / 119 output / 158 total tokens，1054 ms，exact response 与 actual model 匹配，0 tool side effects、0 managed resources。Marker SHA-256 为 `73a505f3...21ee`；这只证明固定端点在该时点完成往返。
- Mechanism v2 formal execution：PR #378 合并为 `main@fe36cf137dbaa3a0dd29793ae67e74e97a631c61`，manifest canonical SHA-256 为 `491d877c...3609`。唯一 batch 完成 12 arms / 4 checkpoints 后，在 checkpoint 5 `lz4:delivery_target` 构造阶段以 `FormalFatalError` 封口；sequence 13 与 checkpoint 5 evidence 均未创建。冻结 evidence 为 70 files / 689,742 bytes，inventory SHA-256 `5c885b2a...b9d11`；75 requests / 907,258 input / 161,276 output / 1,068,534 total tokens，0 endpoint censor，失败后 0 managed containers / 0 capture images。
- Mechanism v2 不完整结果：两个完整项目的 delivery/target 中 C0/T1/T2 均为 1，provenance 中三臂均为 0，所以三个 observed-complete project score 均为 0。剩余 8/12 checkpoints 不填零，三个比较的 best/worst identification interval 均为 `[-2/3, +2/3]`；`primary_test=null`、`secondary_test=null`，不计算 p 值，也不能据此判断存在或不存在有意义效应。

## 设计审计结论

- 历史 behavioral、opaque provenance 与 Runtime v3 使用三套不同反馈合同，不能直接合并为一项确认性实验。
- 主 estimand 是“合同派生的可操作反馈包暴露效应”，不表述为纯格式效应。研究负责人已选择 C0/T1/T2 三臂；主要比较为 C0 vs T1，次级比较为 T1 vs T2，C0 vs T2 作支持性比较。
- 已冻结 6 个项目 × 每项目 2 个 checkpoint × 3 个反馈臂，共 36 arms；candidate delivery/target 与 build provenance 两个 stratum 分别报告。C0 vs T1 的最小有意义效应为 `+1/3`，T1 vs T2 为 `+1/6`，采用 project-level exact sign-flip 与 fixed-sequence gatekeeping。
- 36 arms 定位为固定样本毕业论文机制研究，不是功效充分的总体确认性实验；真实效应 `+1/3` 时，12-checkpoint 设计的估计功效仅约 `0.16--0.20`。
- Opaque replication 的高 endpoint attrition 要求新 identity 预先冻结 availability qualification、无响应 retry 语义和早停规则。
- 旧 opaque replication runner 在当前树仍导入已移除的 `resolve_command_role`，聚焦测试于 collection 阶段失败；冻结结果不受影响，新门禁必须使用独立 adapter，不能改写历史 runner。
- Issue #352 的独立 qualification adapter 已满足该缺口，并把当前 Runtime v3、CandidateVerifier、P2、external evaluator v3、compile operations 与 compiler tool surface 的 SHA-256 纳入 authority identity；历史 runner、manifest、report 和 evidence 均未修改。
- Issue #353 的结果盲可辨识性审计显示：12-checkpoint / 36-arm 设计在真实绝对效应 `+1/3` 时，双侧 exact paired test 的估计功效仅约 `0.16--0.20`；在中等 discordance 假设下达到约 80% 功效需约 36 个 checkpoint / 108 arms。因此推荐把 36 arms 定位为固定样本的毕业论文机制研究，而非功效充分的确认性总体效应实验。
- Issue #353 candidate 已确定性生成 6-project / 12-checkpoint / 36-arm schedule；每个 stratum 恰好使用 C0/T1/T2 六种排列各一次，三个项目先运行 delivery/target、三个先运行 provenance。三臂使用 opaque clone/evaluation identity，external evaluator 输入不含 arm label。
- PR #354 四项 CI 全绿并 squash-merge；Issue #355 release-bound identity 以 `main@a63f328b0cd2771ec656414e697ebbb831391ed9` 和父 candidate canonical SHA-256 `fc1ec9ad...00f8f` 为权威输入，原样继承全部科学字段。
- PR #356 四项 CI 全绿并 squash-merge 为 `main@25b358814e4749031cc7fd3d83139a79d884f7a4`；authorized manifest canonical SHA-256 为 `840eac32...0a0a0`，clean-tree 非模型 preflight 为 `ready=true`，全部执行计数为 0。
- PR #358 四项 CI 全绿并经用户确认 squash-merge 为 `main@d55f39b03179f59b0b3b89bb8648a168ec54f7bd`；availability candidate canonical SHA-256 为 `e0583ddb...9f00`，仍为 0 Provider observation。
- PR #366 四项 CI 全绿并 squash-merge 为 `main@b5acc18c13057e7ba1deee078c628ad907647679`；failure audit 固定旧 evidence inventory `24019a37...2fb5`，marker repair 绑定 frozen runner SHA-256 `5bb1797d...e358`。
- Issue #367 mechanism v2 candidate 当前 canonical SHA-256 为 `40ea4706...e25f0d`；全部真实执行授权为 false，历史 availability、checkpoint、arm、ledger、result、token 和 outcome 均不导入。
- PR #368 四项 CI 全绿并 squash-merge 为 `main@70b257c840f4065285c047ba6207ffe99f8dcb36`；Issue #367 自动关闭。Issue #369 release-bound candidate 绑定该 exact release 与父 canonical，当前 canonical SHA-256 为 `9ce0b7eb...e08197`，真实执行权限仍全部为 false。

## 解释边界

当前证据可以支持：

- Forge 已具备开展候选研究所需的 checkpoint、候选合同、独立 evaluator、ledger 和 clean replay 基础；
- Runtime v3 当前实现可在两个候选 fault strata 上形成 state-matched C0/T1/T2，并以确定性 continuation 闭合严格工程终点；
- 探索性结果支持“结构化合同拒绝反馈可能促进候选转换”这一待验证假设；
- 当前最适合把分层评测作为支撑性贡献，把 matched-state 契约反馈作为主要机制问题。
- Mechanism v2 的两个完整项目呈现相同的分层描述：delivery/target 三臂均成功，provenance 三臂均为预算耗尽零 outcome；冻结 checkpoint builder 与 `lz4` 双 compiled target 合同存在可复现的基数不兼容。

当前证据不能支持：

- 结构化合同反馈的确认性总体效应、统计显著性或自然失败外推；
- Forge 整体优于 CXXCrafter、CompileAgent 或其他自动构建系统；
- Provider 或模型的普遍能力排名；
- verifier、matched-state、独立 authority 或分层评测的通用首创性；
- 将 Stage C v8 canary 当作方法比较，或用它覆盖历史实验终态。
- 从 2/6 个完整项目的零差推断 C0/T1/T2 无效、等效或不存在有意义效应；对不完整 mechanism v2 batch 运行主要或次级 exact test。

## 当前允许与禁止

允许：

- 只读核验论文、仓库报告、manifest、ledger 和冻结 evidence；
- 实现并运行使用确定性本地模型的零 Provider、零正式 attempt、独立 evidence 目录 qualification；
- 实现、审阅 release-bound identity，并运行不读取 credential、不创建容器或 evidence 的非模型 preflight。
- 派生、审阅 availability qualification 候选 amendment，并运行同样的非模型 preflight。
- 对 Issue #377 的失败 formal evidence 做只读核验；实现、测试、提交、推送、PR、CI 与合并 Issue #379 的版本化失败审计和状态交接。
- 对失败 formal evidence 做只读核验；实现不修改冻结 runner 的独立 marker repair；提交、推送、PR、CI 与合并 Issue #365 的审计和工程修复。
- 实现、测试、Docker qualification、提交、推送、PR、CI 与合并 Issue #367 的独立 36-arm candidate；运行不读取 credential、不创建 formal attempt 或 formal evidence 的非模型 preflight。
- 实现、测试、提交、推送、PR、CI 与合并 Issue #369 的 exact release-bound identity；运行相同的零 credential、零 Provider preflight。
- 实现、测试、提交、推送、PR、CI 与合并 Issue #371 的 availability execution identity；合并后在 clean main 检查 `DEEPSEEK_API_KEY` presence，调用 `deepseek-flash` 执行唯一 logical request，并写入、只读审计唯一 create-once marker。
- 对 Issue #371 的 create-once marker 做只读核验，提交、推送、PR、CI 与合并 Issue #373 的版本化 JSON/Markdown 审计和状态交接。

禁止：

- 重跑、retry、replacement、backfill 或改写任何历史 experiment identity；
- 修改、移动、删除或重新生成冻结 evidence；
- 对 manifest `3a843799...5829f` 的 batch 做续跑、重跑、replacement、backfill、marker 手工修补或新增 evidence；在新的科研决策与独立 identity 合并前调用 Provider；禁止把单个 T2 arm 或 qualification 当作 treatment evidence。
- 对已消费的 v2 availability identity 做 rerun、retry、replacement、backfill、marker 修改或新增 evidence；禁止修改 v1 evidence 或把 v1 sequence 1 导入 v2。
- 对 Issue #377 mechanism v2 batch 做 continuation、rerun、retry、replacement、backfill、schedule extension、marker 修补或 sequence 13/checkpoint 5 补写；禁止把两个完整项目的描述性零差解释为 treatment effect。

## 当前工作区与知识库状态

- 当前 formal 发布基线：PR #378 已合并为 `main@fe36cf137dbaa3a0dd29793ae67e74e97a631c61`；该 release 创建的唯一 batch 已永久失败并保持只读。
- Stage C v8 原始 evidence 保持只读，权威结果入口为 `benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.md`。
- Runtime v3 qualification 入口为 `benchmarks/preregistrations/cpp-runtime-v3-three-arm-zero-provider-qualification.md`；它是基础设施门禁记录，不是 formal experiment evidence。
- 候选预注册决策包入口为 `docs/research/2026-09-29-contract-driven-repair-preregistration-decision.md`；研究负责人已冻结其推荐方案，但它不是执行授权。
- 父 candidate 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-candidate.json`；新 release-bound identity 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-authorized.json`。当前只授权身份实现，availability、formal collection、credential、Provider、Docker Session、formal attempt、formal evidence 和 model token 授权均为 false。
- Issue #357 availability candidate 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-availability-candidate.json`；它绑定 authorized implementation release，但 availability execution 与 formal collection 仍均未授权。
- Issue #359 availability execution 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-availability-execution.json`；通过 marker 的版本化只读审计为 `benchmarks/reports/cpp-contract-driven-repair-mechanism-v1-availability-audit.md`，formal collection 仍在该 identity 中关闭。
- Issue #363 formal execution 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-formal-execution.json`；原始 evidence 位于 `.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v1-authorized`，保持只读。Issue #365 审计入口为 `benchmarks/reports/cpp-contract-driven-repair-mechanism-v1-formal-failure-audit.md`。
- Issue #367 独立 candidate 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-candidate.json`；预注册入口为 `benchmarks/preregistrations/cpp-contract-driven-repair-mechanism-v2-candidate.md`。Candidate 本身保持不可执行，其派生 formal identity 的已消费 evidence 独立冻结。
- Issue #369 release-bound 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-authorized.json`；它绑定 PR #368 merge commit 和父 candidate，全部 Provider/credential/formal 权限继续为 false。
- Issue #371 availability execution 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-availability-execution.json`；该 identity 已消费，formal collection 权限保持 false。Issue #373 只读审计入口为 `benchmarks/reports/cpp-contract-driven-repair-mechanism-v2-availability-audit.md`。
- Issue #377 formal execution 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v2-formal-execution.json`；原始 evidence 位于 `.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent` 并保持只读。Issue #379 权威审计入口为 `benchmarks/reports/cpp-contract-driven-repair-mechanism-v2-formal-failure-audit.md`。
- 2026-09-29 已按 `search_notes -> read_note` 核对个人知识库中的毕业论文方向与契约驱动修复主笔记；本轮不修改知识库。

## 下一项工作

审阅 Issue #379 冻结报告后，在“修复 checkpoint builder 并建立全新独立 identity”与“停止 formal collection”之间作出科研决策。任何修复与新 collection 都必须使用新的 tracking Issue、独立 evidence root、预算、停止规则和明确授权；不得导入或修改当前失败 batch。
