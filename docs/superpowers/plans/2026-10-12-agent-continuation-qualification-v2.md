# 固定 Agent continuation 资格 v2 实施计划

1. 建立 Issue #430、独立堆叠分支和 `cpp-agent-continuation-qualification-v2` identity。
2. 只读核对 v1 failure audit；在 CandidateVerifier 前刷新权威 Session，并增加 oracle 保存后命令历史完整的回归。
3. 冻结 v5 parent inventory、12 个 checkpoint 用途、9 个 target contract、reference recipe、oracle、Agent 模型、预算、停止规则和 Q2 门槛。
4. 实现单一 create-once runner：`validate`、`plan`、`q0`、`q1`、`q2`、`audit`、`report`；用静态测试验证 manifest、schedule、门禁顺序、预算守恒、token fail-closed、Session 刷新和判定逻辑。
5. 提交并推送 release；执行 Docker preflight。
6. 执行 Q0。若 9/9 strict 失败，封口并停止。
7. Q0 通过后检查 credential 仅以环境变量存在性为边界，执行 Q1。若接线门禁失败，封口并停止。
8. Q1 通过后顺序执行 Q2 的 27 个 arms；每个 arm 只允许一次物理 attempt，已完成前缀可继续，running 且无 result 的 arm 禁止重试。
9. 审计 create-once evidence、生成 inventory 和版本化报告；更新 `RESEARCH_STATUS.md` 与工程交接。
10. 提交、推送并创建堆叠 PR。只有资格通过后，下一阶段才允许设计 direct/escalate/stop matched outcome matrix；本阶段不实现 controller。

