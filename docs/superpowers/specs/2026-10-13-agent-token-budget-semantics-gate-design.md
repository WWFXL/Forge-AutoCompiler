# Agent Token 预算语义与证据一致性门禁设计

> 日期：2026-10-13
> Tracking Issue：[#436](https://github.com/WWFXL/Forge-AutoCompiler/issues/436)
> 工作类型：工程修复与零 Provider 基础设施门禁

## 1. 阻塞问题

`cpp-progress-aware-harness-comparison-v2` 的 8 个 H0 arm 在最后一次 Provider 响应完成后，实际累计 recorded tokens 超过单臂 300,000 停止阈值。Runtime 已把响应写入 `model.request_completed`，但 `AgentWorkflowBudgetTracker.consume()` 在检测越界后保留越界前 snapshot。因此 raw events 和费用包含最后响应，`node_result.usage` 却遗漏它，预注册硬门禁 `cost_and_budget_complete` 失败。

精确 Token 只能在响应完成后取得。单纯把停止阈值解释成不可越过的严格上限，与实际 Provider 计费时点不一致。

## 2. 新预算合同

新合同显式配置两个值：

- `max_recorded_tokens`：累计 Token 的请求准入停止阈值 `T`；
- `max_recorded_tokens_per_response`：一次已完成响应允许的最大 recorded tokens `R`。

派生授权硬上限为 `T + R`。运行时遵循以下顺序：

1. 只有权威累计用量小于 `T` 时，才允许发起下一次模型请求。
2. 响应完成后，先验证 usage metadata，再把实际用量完整提交到 tracker 和事件账本。
3. 提交后累计用量达到或超过 `T`，终态为 `budget_exhausted:recorded_tokens`；不执行该响应中的工具调用，也不发起下一次请求。
4. 单响应实际用量超过 `R`，完整计量后终态为 `budget_contract_violation:recorded_tokens_per_response`。
5. 响应缺少完整、非负且内部一致的 input/output/total Token 时，终态为 `usage_incomplete`；不得继续请求，也不得估算或补零。
6. `remaining_budget.recorded_tokens` 最低为 0。实际累计用量保留 overshoot，不截断到 `T`。
7. model request、agent step、tool call、command 和 wall clock 继续使用原有请求前严格门禁。

当 `max_recorded_tokens_per_response` 未配置时保留历史合同，避免改变冻结 runner 的输入语义。新的实验 identity 若启用 Token 停止阈值，必须同时配置单响应上界；不得把历史模式用于新的确认实验。

## 3. 权威计量与事件

一次具有完整 usage 的响应必须满足：

```text
sum(model.request_completed.recorded_tokens)
  == tracker.snapshot.recorded_tokens
  == node_result.usage.recorded_tokens
  == report.recorded_tokens
```

合成费用以相同 completed events 的 input/output tokens 计算。响应边界违规不会删除、截断或重分类已经发生的费用。

usage 缺失或非法时写入独立的 `model.request_usage_incomplete` 事件，不伪造 `model.request_completed`。该 attempt 只能支持“计量不完整并 fail closed”的结论。

## 4. 零 Provider 门禁矩阵

| Case | 脚本响应 | 预期 |
| --- | --- | --- |
| `below_threshold` | 40 / 100 | 完整计量，可继续并提交候选 |
| `exact_threshold` | 100 / 100 | 完整计量并停止，无工具执行 |
| `bounded_overshoot` | 70 + 40 / 100，R=70 | 累计 110，第二次后停止，无第三次请求 |
| `response_bound_violation` | 60 / 100，R=50 | 累计 60，合同违规并停止 |
| `missing_usage` | 无 usage metadata | `usage_incomplete`，无第二次请求 |
| `invalid_usage` | total 与 input+output 不一致 | `usage_incomplete`，无第二次请求 |
| `provider_failure` | handler 抛错 | 记录 request failure，不伪造 Token |
| `strict_non_token_budget` | 第二次请求超过 request limit | 请求前拒绝，旧预算不变量保持 |
| `unbounded_legacy` | 未配置 Token 阈值 | 保持现有完整计量行为 |

同步与异步 middleware 路径使用相同解析和计量函数。正式 gate 使用完整异步 Agent node；tracker 单元测试覆盖纯合同边界。

## 5. 通过、失败与解释边界

全部 case 通过，且事件、tracker、node result、合成费用和报告一致时，决定为 `proceed_to_progress_aware_harness_v3_replication_decision`。这只解除预算合同阻塞，不恢复或改写 v2 的正式决定，也不构成 H1、Jev、动态预算 controller 或自然失败效果证据。

任一 case 失败时，决定为 `stop_before_progress_aware_harness_v3_replication`。不得创建或执行 v3。

本 gate 不读取 credential、不调用 Provider/Jev、不运行 Docker、不创建 H0/H1 效果 attempt，也不修改 v2 manifest、raw evidence、result、marker 或 inventory。
