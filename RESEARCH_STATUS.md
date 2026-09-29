# Forge Research Status

> 面向研究负责人和新会话的当前状态入口。这里只保留当前阶段、核心证据、解释边界和下一项决策；详细工程流水见 `.claude/memory/project.md`，长期研究综合见个人知识库。

## 当前阶段

- 状态：毕业论文方向、设计审计、Runtime v3 三臂零 Provider qualification 和 Issue #353 未授权 candidate identity 均已完成；36-arm 固定样本设计等待代码审阅与 release revision 冻结。
- 当前工作类型：实验设计与基础设施。Runtime v3 candidate submission 基础设施门禁和确定性执行计划已闭合，本阶段未创建正式 observation。
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

## 解释边界

当前证据可以支持：

- Forge 已具备开展候选研究所需的 checkpoint、候选合同、独立 evaluator、ledger 和 clean replay 基础；
- Runtime v3 当前实现可在两个候选 fault strata 上形成 state-matched C0/T1/T2，并以确定性 continuation 闭合严格工程终点；
- 探索性结果支持“结构化合同拒绝反馈可能促进候选转换”这一待验证假设；
- 当前最适合把分层评测作为支撑性贡献，把 matched-state 契约反馈作为主要机制问题。

当前证据不能支持：

- 结构化合同反馈的确认性总体效应、统计显著性或自然失败外推；
- Forge 整体优于 CXXCrafter、CompileAgent 或其他自动构建系统；
- Provider 或模型的普遍能力排名；
- verifier、matched-state、独立 authority 或分层评测的通用首创性；
- 将 Stage C v8 canary 当作方法比较，或用它覆盖历史实验终态。

## 当前允许与禁止

允许：

- 只读核验论文、仓库报告、manifest、ledger 和冻结 evidence；
- 实现并运行使用确定性本地模型的零 Provider、零正式 attempt、独立 evidence 目录 qualification；
- 起草新的候选 protocol/preregistration，但不能把候选文档写成已授权实验。

禁止：

- 重跑、retry、replacement、backfill 或改写任何历史 experiment identity；
- 修改、移动、删除或重新生成冻结 evidence；
- 在新 identity、样本、预算、停止规则和明确授权前读取 Provider 凭据、调用模型或创建正式 attempt。

## 当前工作区与知识库状态

- 当前工作分支：`yiwei/352-runtime-v3-qualification`；基线 HEAD `47b34eb1`，当前 qualification 改动尚未提交或 push，本阶段不执行发布操作。
- Stage C v8 原始 evidence 保持只读，权威结果入口为 `benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.md`。
- Runtime v3 qualification 入口为 `benchmarks/preregistrations/cpp-runtime-v3-three-arm-zero-provider-qualification.md`；它是基础设施门禁记录，不是 formal experiment evidence。
- 候选预注册决策包入口为 `docs/research/2026-09-29-contract-driven-repair-preregistration-decision.md`；研究负责人已冻结其推荐方案，但它不是执行授权。
- 未授权 identity 入口为 `benchmarks/manifests/cpp-contract-driven-repair-mechanism-v1-candidate.json`；release revision 为 `null`，所有 credential、Provider、Docker、formal attempt、formal evidence 和 model token 授权均为 false。
- 2026-09-29 已按 `search_notes -> read_note` 核对个人知识库中的毕业论文方向与契约驱动修复主笔记；本轮不修改知识库。

## 下一项工作

Issue #353 的 manifest、const Schema、preregistration 与 plan-only runner 已完成并通过零执行门禁。下一项工作
是审阅并提交当前 qualification + candidate 变更，形成可冻结的 release revision；随后派生独立 create-once
authorized identity，再由研究负责人明确授权 availability qualification 和 36-arm formal collection。

candidate 通过审阅仍不等于执行授权。任何下一轮 Provider、credential、formal attempt 或 formal evidence
写入都需要合并后的 release revision、独立授权 identity 和明确执行授权。
