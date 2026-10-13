# Submit 拒绝恢复零 Provider 工程门禁结果

- Identity：`cpp-progress-aware-submit-rejection-recovery-gate-v1`
- 结论：`proceed_to_unseen_three_arm_formal_comparison_design`
- 全部门槛：`True`
- Evidence audit：`True`
- Inventory canonical SHA-256：`f3b70746664547aea75d0b9e699032c0f09fc4672be3f298098dd248a76cd47c`

## 结果

- Runtime v5 旧语义复现：submit 前后 command count 从 `2` 变为 `3`，repair guard 返回 `candidate_ready_requires_submit`。
- Runtime v6 Docker 案例：首次 closure 为 `recipe_execution_failed`，修复 build 与重新 stage 各执行一次，第二次 closure 为 `passed`，candidate 成功冻结。
- 脚本化 Agent 共 `4` 次请求、`0` recorded tokens；credential、Provider、Jev 和 formal effect attempt 均为 0。
- Session 保持活动，正式 replay attempt 为 0；qualification 结束后受管资源为 0。

该结果只证明已观察到的 submit-rejection 恢复死锁在 Runtime v6 中得到有界修复，并保持 CandidateVerifier、functional oracle 和 replay closure。它不估计 H2 对严格成功率、成本、token、自然失败或未见项目总体的效果。
