# Agent Token 预算语义与证据一致性门禁 v1

**决定：`proceed_to_progress_aware_harness_v3_replication_decision`。**

状态：`passed`；门禁通过 `9/9`。

## 门禁结果

| Case | 通过 | Token（events/result） | 请求（started/completed/failed/incomplete） | 终止 |
| --- | --- | ---: | ---: | --- |
| `below_threshold` | 是 | 40/40 | 1/1/0/0 | `success` |
| `exact_threshold` | 是 | 100/100 | 1/1/0/0 | `budget_exhausted:recorded_tokens` |
| `bounded_overshoot` | 是 | 110/110 | 2/2/0/0 | `budget_exhausted:recorded_tokens` |
| `response_bound_violation` | 是 | 60/60 | 1/1/0/0 | `budget_contract_violation:recorded_tokens_per_response` |
| `missing_usage` | 是 | 0/0 | 1/0/0/1 | `usage_incomplete` |
| `invalid_usage` | 是 | 0/0 | 1/0/0/1 | `usage_incomplete` |
| `provider_failure` | 是 | 0/0 | 1/0/1/0 | `node_failed` |
| `strict_non_token_budget` | 是 | 40/40 | 1/1/0/0 | `budget_exhausted:model_requests` |
| `unbounded_legacy` | 是 | 110/110 | 2/2/0/0 | `success` |

## 冻结证据检查

v2 inventory：`valid=true`，30108 files / 719928939 bytes，canonical SHA-256 `fb8f77bf05885dcb2f008fc2799de8361f7dd91af558815b7cff42b01cd5dce8`。

## 结论边界

本门禁是工程修复验证。通过只说明 bounded post-response Token 预算可以完整计量已发生的响应、在触阈后停止后续请求，并保持事件与节点结果一致；它只解除全新 H0/H1 v3 确认性复现的预算合同阻塞。

本结果不改变 v2 的正式停止决定，不证明 H1 效果，不评价动态预算 controller、Jev、自然失败或开放世界。v3 尚未创建或获得执行授权。

全程 0 credential、0 Provider、0 Docker、0 formal effect attempt；v2 evidence 保持只读。
