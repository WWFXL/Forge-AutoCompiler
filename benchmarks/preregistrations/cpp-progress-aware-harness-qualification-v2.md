# `cpp-progress-aware-harness-qualification-v2` 零 Provider 预注册

## 身份与目的

- Tracking Issue：#433；
- 分支：`yiwei/433-progress-aware-harness-qualification`；
- 类型：v1 基础设施失败后的独立工程资格门禁；
- 目的：在冻结离线源码 archive 下验证 Runtime v4 与严格 clean replay 的完整闭包；
- 研究效应：不估计 H1 对真实模型的成功率、成本或动态预算效果。

## 固定差异

v1 的 checkpoint、三条动作、脚本模型、预算、CandidateVerifier 和 evaluator 全部不变。唯一差异是把
`cmake-cxxopts-state-1/checkpoint/workspace.tar.gz` 作为 exact-source archive，绑定 SHA-256
`96bed50fe9c3f1a3ce6925d6828d252ac215fad7e48f35a34efd1d19a4b5ad77`，使 clean replay 不访问 GitHub。

## 唯一 attempt

Runner 使用新的 create-once evidence root。开始后无论成功、失败、异常或部分终结，该 identity 均封口；禁止
retry、replacement 或 backfill。v1 evidence 永久只读，不能因 v2 结果修改其失败状态。

## 门槛与决定

v1 的 8 项门槛继续适用，并要求 source archive 在 Session、repro bundle 和 replay snapshot 三处哈希一致，replay
脚本包含 `tar -xf`、不包含 `git fetch`，最终 S0-S5 strict success。

- 全部门槛通过：`proceed_to_h0_h1_provider_comparison_design`；
- 任一门槛失败：`stop_before_h0_h1_provider_comparison`。

全程 credential reads = 0、Provider requests = 0、Jev calls = 0。通过只授权下一阶段设计，不自动授权 Provider。
