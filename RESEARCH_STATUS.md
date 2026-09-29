# Forge Research Status

> 面向研究负责人和新会话的当前状态入口。这里只保留当前阶段、核心证据、解释边界和下一项决策；详细工程流水见 `.claude/memory/project.md`，长期研究综合见个人知识库。

## 当前阶段

- 状态：Stage C v8 workspace remediation 结果冻结与只读审计已完成，进入报告审阅与下一轮研究决策。
- 本结果的 release 身份：`main@6682d86cb30cc4e8d7b240bca8922606077a4808`，对应已合并 PR #348。
- 当前工作类型：结果分析。
- 当前目标：审阅脱敏 JSON/Markdown 冻结报告及科学解释边界，决定扩大确认性样本、设计独立 replication，或停止当前机制路线。

## 已核验结果

- 固定顺序：`theora -> json-c -> libjpeg-turbo -> oatpp`。
- 四项任务均为 strict success、S0-S5 通过、bitwise reproducible 且 cleanup 完成。
- `libjpeg-turbo` 首次提交被 pre-freeze verifier 以 `target_mapping_invalid` 拒绝，在同一 attempt 修复后第二次提交成功；其余任务一次提交成功。
- 完整账本：37 requests，260,873 input tokens，19,115 output tokens，279,988 total tokens。Token 总量不是终止条件。
- 原始 evidence：16 files / 631,570 bytes。
- Batch marker：`passed`；canary report：`completed`，`strict_success_count=4`，`total_recorded_tokens=279988`。
- Issue #351 的确定性只读审计已重新验证完整文件集合、逐文件 SHA-256、token 闭合、marker/result 一致性和四条 ledger；原始 evidence 未修改。

## 证据身份

- 原始 evidence：`.compile-sessions/benchmark-evidence-stage-c-v8-workspace-remediation-canary-authorized-v1`
- Authorized manifest SHA-256：`df3a8c7ac1e13567b99ec5b7c77d341b6df20f35236cf767e76c06af46835a61`
- Canary report SHA-256：`d6e6f440bacaacb43ca31b1d6899180b272038a7cea151d641a1e00771efca70`
- Reachability report SHA-256：`c418a6de746c021192bc521116a2f85a5e26b7ad45f1ead6e9e949a41aa8d078`
- Evidence inventory SHA-256：`afe607e075509eee1999a65f4c485b0995959a1f026bf22f3f6ff7673d6b14a7`，已按原 `sha256sum` 行算法复算一致。
- 四条 `ExperimentLedger.verify_path()` 哈希链均已重新验证；sequence 和 previous-event 链连续，各由唯一末尾 `experiment.completed` 封口，completion 的 `result_sha256` 与实际结果文件一致。
- 脱敏 JSON 报告：`benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.json`，SHA-256 `43d995ff5f6ae414f0ce87405265c4dd63ccf837657eb7c852c2cdd5bd4a11a4`。
- 中文 Markdown 报告：`benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.md`，SHA-256 `d7c26f5977721369fc8d787a1718b3c0643a9e6cba597dc96e1979c2a860364d`。

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
- 审阅 Issue #351 的结果冻结材料，并通过中文 PR 提交评审。

禁止：

- 重跑、retry、replacement、backfill 或续跑 Stage C v8 identity。
- 修改、移动、删除或重新生成原始 evidence。
- 读取 Provider 凭据、调用模型或创建新的正式 attempt。
- 在完成设计与授权前启动下一轮实验。

## 当前工作区与知识库状态

- Issue #351 跟踪 Stage C v8 结果冻结与只读审计；当前工作分支为 `yiwei/351-stage-c-v8-result-freeze`。
- 当前主干基线为 `main@50626ec1875dba28dd52bd7f0a559be3c100e3b4`；Stage C v8 结果的 release 身份仍保持 `6682d86cb30cc4e8d7b240bca8922606077a4808`。
- 个人知识库写入回执显示已创建 `01-研究/自动化编译/2026-09-28-Forge-Stage-C-v8结果与后续会话交接.md`，并更新 `自动化编译研究索引.md`。
- 2026-09-29 已通过 MCP 搜索并精确回读上述交接笔记，确认索引可检索、原文可读取；笔记 SHA-256 为 `572eaa18dc54f35f9b74368fb22e0fada3e1e769460d3738e709c5390cb0e5c7`。

## 下一项决策

1. 审阅脱敏聚合报告、来源完整性和科学解释边界。
2. 根据审计结果决定下一轮是扩大确认性样本、设计独立 replication，还是停止当前机制路线。
3. 若继续实验，先冻结新的研究问题、样本、identity、预算和停止规则，再单独授权执行。

任何下一轮 Provider、正式 attempt 或 evidence 写入，都需要新的冻结 identity、预算、停止规则和用户明确授权。
