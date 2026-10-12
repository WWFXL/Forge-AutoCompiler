# 进展感知结构化 Harness H0/H1 配对比较 v2 预算合同审计

## 正式决定

`stop_progress_aware_harness_as_primary_mechanism`

该决定由预注册硬门禁 `cost_and_budget_complete=false` 机械触发，不能在观察结果后改写。v2 evidence 已封存，禁止重跑、补齐、replacement、backfill 或修改 raw result。

## 完整性

- Q0：9/9 reference strict，S0-S5、bitwise reproduction、离线 source 和 cleanup 全部通过；0 Provider、0 credential read。
- Q1：6/6 arms 分类与计量闭合，H0/H1 strict 均为 2/3。三个 H0 arm 的 snapshot/compaction 均为 0；三个 H1 arm 分别为 6/6、7/7、9/9，精确等于各自模型请求数。
- Q2：27 pairs / 54 arms 全部分类、checkpoint/source 绑定、动作后观察和 cleanup 闭合；0 infrastructure error，0 managed resource。
- Q2 的 27 个 H0 arm 均无 snapshot/compaction；27 个 H1 arm 的 snapshot/compaction 均大于 0 且等于模型请求数。

## 观察结果

| 指标 | H0 Runtime v3 | H1 Runtime v4 | H1 相对变化 |
|---|---:|---:|---:|
| Strict success | 16/27 | 22/27 | +6 arms / +22.2 pct |
| Provider requests | 318 | 220 | -30.8% |
| Recorded tokens | 4,530,526 | 1,702,701 | -62.4% |
| Provider cost | $1.619287 | $0.707752 | -56.3% |
| Diagnostic commands | 271 | 98 | -63.8% |
| Budget exhausted | 8 | 0 | -8 arms |
| Wall clock | 2,109,118 ms | 2,049,761 ms | -2.8% |

Strict-success 差值为 `0.222222`，task-cluster 单侧 95% bootstrap 下界为 `0.0`。预注册的 `primary_noninferiority_and_cost` 和 `system_non_regression` 均通过；要求下界严格大于 0 的替代 superiority 路径未通过。

分系统 strict 为：CMake `3/9 -> 9/9`，Make `8/9 -> 8/9`，Autotools `5/9 -> 5/9`。项目级结果并非单向：`libfastjson` 为 H0 `1/3`、H1 `0/3`，`libev` 为 H0 `1/3`、H1 `2/3`；因此不能把总体信号解释为每个项目都改善。

## 硬门禁失败原因

8 个 `budget_exhausted` arm 全部属于 H0，终止原因为 `recorded_tokens`。其 Provider events 均完整：requests started 等于 completed、failed 为 0，实际 recorded tokens 为 `304,588` 至 `328,146`，超过冻结的单臂 300,000 token 上限 `4,588` 至 `28,146`。

Runtime 在一次响应完成后才知道精确 token。最后一次响应会先写入 `model.request_completed`，随后 `AgentWorkflowBudgetTracker.consume()` 检测到累计值超过上限并抛出 budget exhausted；tracker snapshot 保留越界前值。因此：

- raw events 和费用包含最后一次真实响应；
- `node_result.usage.recorded_tokens` 不包含该响应；
- token accounting 完整、预算加法守恒，但两种计数不相等，使 `budget.complete=false`；
- 8 个 arm 的最后一次响应为 28,964 至 60,594 tokens，无法由仅在响应后检查的机制严格限制。

这不是 Provider 请求丢失、Docker cleanup 失败或结果文件缺失，而是 token ceiling 的执行语义不能保证严格上限。由于 H0/H1 公平比较预注册要求所有 arm 的预算合同完整，正式 qualification 必须失败。

## 能够与不能够得出的结论

能够支持：在冻结的 9 个受控 checkpoint、`deepseek-flash` 和本次运行中，H1 与更多 strict success、更少请求/token/费用、更少诊断命令和更少预算长尾同时出现；进展快照、上下文裁剪和 guards 的整体 Harness 机制具有强正向实证信号，值得修复预算计量后做确认性复现。

不能支持：v2 正式通过、H1 strict superiority、单个组件的独立因果贡献、自然失败或开放世界泛化、通用 Agent Harness 排名、Jev 效果或动态预算 controller 效果。墙钟仅下降 2.8%，也不能主张显著加速。

## 下一阶段建议

先建立独立零 Provider 预算语义门禁：把已发生的最后一次响应完整计入 authoritative usage；将 token 预算明确定义为“停止阈值加一次响应的冻结最大 overshoot”，或实现有可证明上界的请求前预留；验证触阈后不再发起下一请求、events 与 node usage 精确一致、费用使用真实 token、budget-exhausted 仍是合法终态。

该门禁通过后，再由研究负责人决定是否建立全新 v3 confirmatory replication identity。v3 必须声明已观察 v2 结果，不得把同样本复现伪装成盲的首次验证；在此之前不进入 Workflow+Agent+Jev 新链路设计。

## Evidence

- Release：`0dec1b2427b5146c37ebad8ec589b5c8e43132e4`；
- Manifest canonical SHA-256：`2891fcf708efda329686fb31b11abb25ec20e5716fa5219c5859a13c9a015018`；
- Q2 result SHA-256：`74c161596c8bdefd1a58bf502fe43aab6b1f38bbc6401c0d0a231d5cde119126`；
- Inventory canonical SHA-256：`fb8f77bf05885dcb2f008fc2799de8361f7dd91af558815b7cff42b01cd5dce8`；
- Evidence：30,108 files / 719,928,939 bytes；
- Result JSON/Markdown SHA-256：`04a649c2bc3ec2e224fab3e449f6b771b05d7ba1cc18e74e844868573858d29a` / `2e75516fb05f5d3a2952b65bfbc21ac4df5796a3f3067d008e50696f2df9742f`。
