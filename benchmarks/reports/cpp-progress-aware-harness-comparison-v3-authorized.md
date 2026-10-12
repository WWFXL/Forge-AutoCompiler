# 进展感知结构化 Harness H0/H1 v3 确认性复现结果

**决定：`stop_progress_aware_harness_as_primary_mechanism`。**

Q0 reference strict：`9/9`；Q1 配对 canary：`6/6` arms 分类闭合。

## 正式结果

- Strict success：H0 `19/27`，H1 `22/27`；
- H1-H0 strict difference：`0.111`，task-cluster 单侧 95% 下界 `-0.111`；
- Provider cost：H0 `$1.507782`，H1 `$0.753661`，reduction `50.0%`；
- Recorded tokens：H0 `4230017`，H1 `1788466`；
- Budget exhausted：H0 `6`，H1 `1`；no candidate：H0 `0`，H1 `0`；
- 分系统 strict：`{"autotools": {"h0_runtime_v3": 6, "h1_runtime_v4": 5}, "cmake": {"h0_runtime_v3": 4, "h1_runtime_v4": 9}, "make": {"h0_runtime_v3": 9, "h1_runtime_v4": 8}}`。

## 门禁

- `classified_terminal`：通过
- `cleanup`：通过
- `cost_and_budget_complete`：通过
- `event_node_budget_consistent`：通过
- `no_budget_contract_violation`：通过
- `no_infrastructure_error`：通过
- `offline_source_binding`：通过
- `paired_schedule_complete`：通过
- `parent_checkpoint_binding`：通过
- `post_action_observation`：通过
- `request_lifecycle_closed`：通过
- `usage_complete`：通过
- `alternative_success_improvement`：失败
- `primary_noninferiority_and_cost`：失败
- `system_non_regression`：失败

## 解释边界

只评价冻结受控 checkpoint、deepseek-flash 和固定预算下 Runtime v4 相对 Runtime v3 的 Harness 整体处理效应；不评价 Jev、动态预算、自然失败、开放世界或通用 Agent Harness。

## Evidence

- Manifest canonical SHA-256：`81a5a0af34a6e6eaf9fa6a6c116c4ef3e9418fdc5c44a55a348d9256d1e59479`；
- Inventory canonical SHA-256：`a2cedd30ed5953eb716dd443e462e4ea0754ce53452a47b5504acb465957ffe7`；
- Evidence files：`26923`，`572668150` bytes。
