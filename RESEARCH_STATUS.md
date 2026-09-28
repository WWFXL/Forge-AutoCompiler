# Forge Research Status

> 面向研究负责人和新会话的当前状态入口。这里只保留当前阶段、核心证据、解释边界和下一项决策；详细工程流水见 `.claude/memory/project.md`，长期研究综合见个人知识库。

## 当前阶段

- 状态：Stage C v8 workspace remediation 真实 canary 已完成，进入结果冻结与只读审计。
- 本结果的 release 身份：`main@6682d86cb30cc4e8d7b240bca8922606077a4808`，对应已合并 PR #348。
- 当前工作类型：结果分析。
- 当前目标：从冻结 evidence 生成脱敏、可审阅的 JSON/Markdown 聚合报告，核对账本、结果、哈希和科学解释边界。

## 已核验结果

- 固定顺序：`theora -> json-c -> libjpeg-turbo -> oatpp`。
- 四项任务均为 strict success、S0-S5 通过、bitwise reproducible 且 cleanup 完成。
- `libjpeg-turbo` 首次提交被 pre-freeze verifier 以 `target_mapping_invalid` 拒绝，在同一 attempt 修复后第二次提交成功；其余任务一次提交成功。
- 完整账本：37 requests，260,873 input tokens，19,115 output tokens，279,988 total tokens。Token 总量不是终止条件。
- 原始 evidence：16 files / 631,570 bytes。
- Batch marker：`passed`；canary report：`completed`，`strict_success_count=4`，`total_recorded_tokens=279988`。

## 证据身份

- 原始 evidence：`.compile-sessions/benchmark-evidence-stage-c-v8-workspace-remediation-canary-authorized-v1`
- Authorized manifest SHA-256：`df3a8c7ac1e13567b99ec5b7c77d341b6df20f35236cf767e76c06af46835a61`
- Canary report SHA-256：`d6e6f440bacaacb43ca31b1d6899180b272038a7cea151d641a1e00771efca70`
- Reachability report SHA-256：`c418a6de746c021192bc521116a2f85a5e26b7ad45f1ead6e9e949a41aa8d078`
- 交接记录中的 evidence inventory SHA-256：`afe607e075509eee1999a65f4c485b0995959a1f026bf22f3f6ff7673d6b14a7`；结果冻结审计需按原记录算法再次核对。
- 四条 `ExperimentLedger.verify_path()` 哈希链在交接记录中均为连续，并由唯一 immutable `experiment.completed` 封口；正式聚合报告需再次只读验证。

## 解释边界

当前结果可以支持：

- v8 workspace remediation 在这四个固定任务的唯一授权 canary 中完成了端到端工程闭合。
- pre-freeze verifier 在 `libjpeg-turbo` 上产生了可观察的同 attempt 修复路径。
- 这四个任务的候选、external evaluator、bitwise replay 和 cleanup 均达到冻结验收条件。

当前结果不能支持：

- treatment effect、统计显著性或总体成功率。
- Provider 或模型的普遍能力排名。
- 将四任务 canary 外推到未观测项目、其他环境或其他实验 identity。
- 用 v8 结果覆盖 Stage C v5 的预注册主要结果，或改写 v6/v7 的失败终态。

## 当前允许与禁止

允许：

- 只读核验原始 evidence、ledger、marker、result 和 report。
- 生成脱敏的版本化 JSON/Markdown 聚合报告。
- 审计结果一致性、测量边界和允许的科学表述。
- 通过中文 Issue、分支和 PR 提交结果冻结材料。

禁止：

- 重跑、retry、replacement、backfill 或续跑 Stage C v8 identity。
- 修改、移动、删除或重新生成原始 evidence。
- 读取 Provider 凭据、调用模型或创建新的正式 attempt。
- 在完成设计与授权前启动下一轮实验。

## 当前工作区与知识库状态

- Issue #349 跟踪 Codex 科研协作契约、Skill 和本状态入口。
- 本轮开始时，唯一已有未提交改动是 `.claude/memory/project.md` 中的 Stage C v8 会话交接条目；必须保留并随当前文档分支处理。
- 个人知识库写入回执显示已创建 `01-研究/自动化编译/2026-09-28-Forge-Stage-C-v8结果与后续会话交接.md`，并更新 `自动化编译研究索引.md`。
- 2026-09-28 的 MCP 搜索与精确读取均持续超时；写入成功与索引可检索是两个状态，当前尚未完成最终索引回读验证。

## 下一项决策

1. 在不改写 evidence 的前提下完成 Stage C v8 结果冻结与只读审计。
2. 审阅脱敏聚合报告及科学解释边界。
3. 根据审计结果决定下一轮是扩大确认性样本、设计独立 replication，还是停止当前机制路线。

任何下一轮 Provider、正式 attempt 或 evidence 写入，都需要新的冻结 identity、预算、停止规则和用户明确授权。
