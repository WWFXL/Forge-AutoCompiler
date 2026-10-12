# 进展感知结构化 Harness H0/H1 配对比较 v1 canary instrumentation 审计

## 决定

`supersede_before_q2_due_to_canary_instrumentation_gap`

v1 停止在 Q1 canary 后，不创建 Q2 attempt。Q0 与 Q1 raw evidence 保持只读，v1 canary 不进入后续正式 effect estimate。

## 已观察结果

- Q0：9/9 reference strict，S0-S5、bitwise reproduction、离线 source archive 和 cleanup 全部通过；0 credential、0 Provider。
- Q1：6/6 H0/H1 arms 分类终结、token/预算完整、offline source 绑定、cleanup 闭合且没有 Provider/基础设施错误。
- Canary strict：H0 `2/3`，H1 `2/3`。
- Recorded tokens：H0 `206,812`，H1 `108,612`；Provider cost：H0 `$0.073173`，H1 `$0.038861`。
- 上述 Q1 数值只用于工程诊断，不形成 treatment claim。

## 缺陷

每个 Session snapshot 中同时存在主 Agent `events.jsonl` 和 external evaluator `events.jsonl`。v1 `_events()` 要求递归搜索结果恰好只有一个文件，因此返回空列表，使派生 `harness-metrics.json` 将 H1 的 progress snapshot 和 context compaction 错记为 0。

只读核对主 Agent raw events 后，三个 H1 arms 分别存在 5、6、7 个 `harness.progress_snapshot`，与各自 Provider request 数一致；H0 raw events 不包含该事件。因此 treatment 实际接线正确，错误仅在派生 instrumentation。v1 Q1 门禁还缺少 H0/H1 事件分离断言，导致错误指标没有阻止 canary 机械通过。

## v2 修订

v2 只选择不位于 `evaluations/` 下的主 Agent events，并要求：

- H0 progress snapshot/context compaction 均为 0；
- H1 progress snapshot/context compaction 均大于 0，且分别等于该 arm 的 model request 数；
- 其余 treatment、样本、顺序、模型、预算、离线源码、裁判、主要判据和停止规则保持不变。

## Evidence

- v1 release：`e87bc794625bae8a2658e2e1688fb507ce458fb9`；
- manifest canonical SHA-256：`2c90e1f82a9d47673aa1cd4e99bada60e2ba9e45dc5aa334f716abffe68b4f0f`；
- evidence：6,996 files / 123,160,740 bytes；
- inventory canonical SHA-256：`3a03ec1a2bed0ab5311842ce51bc0292963871d2c9f3d9d364ce84aae51fa201`；
- Q2 path：不存在；cleanup 后 managed resources：0。

## 结论边界

该审计只证明 v1 canary 的派生 Harness 计数无效、raw treatment 接线存在以及需要 v2 instrumentation 门禁。它不评价 H1 相对 H0 的正式成功率、成本效应或动态预算控制。
