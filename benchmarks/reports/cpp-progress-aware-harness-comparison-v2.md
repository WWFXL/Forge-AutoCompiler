# 进展感知结构化 Harness H0/H1 配对比较 v2 结果

**决定：`stop_progress_aware_harness_as_primary_mechanism`。**

Q0 reference strict：`9/9`；Q1 配对 canary：`6/6` arms 分类闭合。

## 正式结果

- Strict success：H0 `16/27`，H1 `22/27`；
- H1-H0 strict difference：`0.222`，task-cluster 单侧 95% 下界 `0.000`；
- Provider cost：H0 `$1.619287`，H1 `$0.707752`，reduction `56.3%`；
- Recorded tokens：H0 `4530526`，H1 `1702701`；
- Budget exhausted：H0 `8`，H1 `0`；no candidate：H0 `0`，H1 `0`；
- 分系统 strict：`{"autotools": {"h0_runtime_v3": 5, "h1_runtime_v4": 5}, "cmake": {"h0_runtime_v3": 3, "h1_runtime_v4": 9}, "make": {"h0_runtime_v3": 8, "h1_runtime_v4": 8}}`。

## 门禁

- `classified_terminal`：通过
- `cleanup`：通过
- `cost_and_budget_complete`：失败
- `no_infrastructure_error`：通过
- `offline_source_binding`：通过
- `paired_schedule_complete`：通过
- `parent_checkpoint_binding`：通过
- `post_action_observation`：通过
- `alternative_success_improvement`：失败
- `primary_noninferiority_and_cost`：通过
- `system_non_regression`：通过

## 解释边界

只评价冻结受控 checkpoint、deepseek-flash 和固定预算下 Runtime v4 相对 Runtime v3 的 Harness 整体处理效应；不评价 Jev、动态预算、自然失败、开放世界或通用 Agent Harness。

## Evidence

- Manifest canonical SHA-256：`2891fcf708efda329686fb31b11abb25ec20e5716fa5219c5859a13c9a015018`；
- Inventory canonical SHA-256：`fb8f77bf05885dcb2f008fc2799de8361f7dd91af558815b7cff42b01cd5dce8`；
- Evidence files：`30108`，`719928939` bytes。
