# 固定 Agent continuation 资格 v1 失败审计

**决定：`supersede_with_fresh_v2_identity_after_session_refresh_repair`。**

## 实际发生了什么

Q0 按协议在第一个 `cmake-spdlog-state-1` 停止。Reference configure、build 和 artifact-stage 三条命令均返回 0，`lib/libspdlog.a` 正确生成，Runtime v3 CandidateVerifier 与 functional oracle 也通过。外部 evaluator 的 S0 通过，但 S1 以 `command_missing`、`supporting_command_invalid` 和 `artifact_stage_missing` 失败，S2-S5 因此没有执行。cleanup 成功，未留下受管资源。

## 根因

Q0 执行每条 reference 命令时重新加载了权威 Session，但传给 `_direct_candidate` 的仍是恢复 checkpoint 后的旧内存 Session。`AgentWorkflowCandidateService` 捕获该旧对象；CandidateVerifier 随后运行 functional oracle，并通过 `record_command` 保存 smoke 命令。该保存把旧对象写回 `session.json`，覆盖了权威 Session 中已经记录的 configure、build 和 artifact-stage 命令。

因此，`workflow.log` 仍完整记录四条成功命令，冻结 candidate 也正确引用前三个 command ID，但最终 `session.json` 只剩 smoke 命令。外部 evaluator 据此正确地在 S1 拒绝 candidate。

## 结论边界

这是 runner 的 Session 权威刷新缺失，不是 spdlog、checkpoint、CandidateVerifier 或固定 Agent continuation 的负结果。v1 未运行任何 Agent arm，未读取 credential，未调用 Provider；其余 8 个 Q0 case、Q1 和 Q2 都未观察，不能记为失败或零。

v1 identity 与 evidence 永久只读，不重跑、不补齐、不 backfill。修复只能进入独立 v2：在 CandidateVerifier 接收 Session 前重新加载权威 Session，并增加 functional oracle 保存后命令历史仍完整的回归；全新 v2 Q0 通过 9/9 后才能进入 Provider canary 和正式 Agent continuation。

## Evidence

- Release revision：`e1c669574670d97e31df107ead3b89cc3fda3efc`；
- Manifest canonical SHA-256：`46ec8c9953d906422d119d18e438abdae7a12d518b6c3b414187a0c22c23539e`；
- Evidence：252 files / 5,790,620 bytes；
- Inventory canonical SHA-256：`66c9e4678bdedc09db02bce8621cf2d140a2b1e4238923ea9bf504b8e753665f`；
- Raw root：`.compile-sessions/benchmark-evidence-agent-continuation-qualification-v1`。
