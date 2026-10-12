# C++ 进展感知结构化 Harness H0/H1 v3 确认性复现预注册候选

## 状态与披露

本文件在任何 v3 Provider observation 之前冻结。v2 结果已经观察：H0/H1 strict 为 `16/27` 与 `22/27`，Provider cost 为 `$1.619287` 与 `$0.707752`，但预算证据不完整使正式决定为 `stop_progress_aware_harness_as_primary_mechanism`。这些历史结果只用于披露和设计预算，不进入 v3 estimate。

当前 identity 为未授权 candidate：0 credential、0 Provider、0 model token、0 Docker、0 formal attempt、0 evidence write。

## RQ 与假设

RQ：在相同 9 个项目族、但未进入 v2 H0/H1 arms 的 checkpoint 深度上，Runtime v4 进展感知结构化 Harness 相对 Runtime v3 能否保持严格成功率非劣，并降低 Provider 成本？

- H1a：H1-H0 strict success 差值的 task-cluster 单侧 95% bootstrap 下界不低于 `-0.10`。
- H1b：H1 的 Provider 总费用相对 H0 至少降低 20%。
- H1c：CMake、Make、Autotools 中 H1 strict 计数均不低于 H0。

只有 H1a、H1b、H1c 同时成立且所有证据硬门禁通过，才支持“同项目族跨状态深度复现”。

## 样本与分配

项目族、exact commit、target、reference recipe 和 source archive 继承 v2。正式 checkpoint 由 v2 正式深度机械变换：`1 -> 3`、`2 -> 1`、`3 -> 2`。该规则产生 CMake、Make、Autotools 各三个 checkpoint，每个系统均覆盖 state 1、2、3，且与 v2 Q1/Q2 checkpoint 集合不相交。

每个 checkpoint 三次重复，共 27 个配对和 54 个正式 arms。schedule 继承 v2 的冻结顺序；奇数 block 为 H0 后 H1，偶数 block 为 H1 后 H0。Q1 canary 使用三个额外 checkpoint，共 6 arms，不进入正式分析。

项目族与 Issue #430/v2 重合，历史结果已知，因此不主张未见项目泛化。选择规则不读取历史 arm outcome，v3 不池化任何历史 observation。

## Treatment、模型与预算

- H0：`h0_runtime_v3`。
- H1：`h1_runtime_v4`。
- Provider/profile/actual model：DeepSeek `deepseek-flash`，非流式、thinking 关闭、模型重试为 0。
- 每臂 `max_model_requests=24`、`max_recorded_tokens=300000`、`max_recorded_tokens_per_response=100000`、`max_agent_steps=64`、`max_tool_calls=48`、`max_commands=32`。
- 60 个 Provider arms 最多 1,440 requests；停止阈值总和 18,000,000 tokens；授权上界 24,000,000 tokens；费用上界 `$28.80`。

响应完成后必须先完整计入 usage。累计达到 T 后不得发起下一请求；单响应超过 R、usage 缺失或不一致均 fail closed，并使正式实验失败。

## 阶段门禁

1. Q0：9/9 零 Provider reference strict，检查 CandidateVerifier、functional oracle、provenance、clean replay 和 cleanup。
2. Q1：6/6 canary arms 分类闭合；H0 snapshot/compaction 必须为 0，H1 必须等于 completed request 数。
3. Q2：仅在 Q0/Q1 通过后执行；27/27 pairs 和 54/54 arms 必须存在且分类终结。

所有 arm 均保留失败、超时、预算耗尽、usage incomplete 和合同违规。禁止 retry、replacement、backfill、删除失败 observation 或结果后修改阈值。

## 指标与分析

主要指标为 strict success 和 Provider cost。次要指标为 recorded tokens、请求数、diagnostic commands、预算耗尽、墙钟、工具调用、命令数与 harness instrumentation。

以项目为 cluster，使用固定 seed 的 10,000 次 bootstrap 计算 H1-H0 strict 差值单侧 95% 下界。分系统报告 strict 计数。墙钟只作描述，不在本设计中声明显著加速。

替代通过路径要求 strict 差值下界大于 0、点估计至少 `+0.10`，且 H1 费用增幅不超过 10%。该路径仍受全部硬门禁和分系统不退化约束。

## 结论边界

正向结果只支持当前 9 个项目族、受控 checkpoint、`deepseek-flash`、固定预算和严格 Forge 终点下的跨状态复现。它不证明单一 Harness 组件的因果贡献，不评价 Jev、动态预算 controller、自然失败、开放世界或通用 Agent Harness。

负向或证据不完整结果将停止进展感知 Harness 作为当前主要机制，不用新的同设计 identity 挽救。
