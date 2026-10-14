# H0/H1/H2 Runtime v6 十八臂 Provider 正式比较 v2 结果

**决定：`runtime_v6_noninferior_but_mechanism_not_activated`。**

Q0：通过，0 credential read / 0 Provider request；Q1：`18/18` arms 分类终结。

## 描述性结果

- `h0_runtime_v3`：strict `6/6`，evaluated `6/6`，requests `59`，recorded tokens `452060`，cost `$0.158667`，diagnostic `29`，replay closure `0`，repair windows `0`。
- `h1_runtime_v4`：strict `6/6`，evaluated `6/6`，requests `45`，recorded tokens `249376`，cost `$0.088058`，diagnostic `15`，replay closure `0`，repair windows `0`。
- `h2_runtime_v6`：strict `6/6`，evaluated `6/6`，requests `44`，recorded tokens `249229`，cost `$0.087804`，diagnostic `14`，replay closure `6`，repair windows `0`。

## 主要分析

- H2-H1 strict success 差值：`0.000`；
- 项目族 bootstrap 单侧 95% 下界：`0.000`，非劣界 `-0.10`；
- 非劣：`True`；机制自然激活：`False`；
- H1 S5 replay failure `0`，H2 closure rejection `0`，repair window `0`。

## 硬门禁

- `batch_budget`：通过
- `budget_conserved`：通过
- `classified_terminal`：通过
- `cleanup`：通过
- `host_storage_observed`：通过
- `no_infrastructure_error`：通过
- `request_lifecycle_and_usage`：通过
- `schedule_complete`：通过
- `source_and_post_observation_bound`：通过
- `treatment_instrumentation`：通过

## 解释边界

本正式比较只估计三个冻结项目族、两次重复上的 H2-H1 严格成功差值和 Runtime v6 机制是否自然激活；不支持开放世界、项目总体泛化、统计显著性、通用模型排名或动态预算效果。

## Evidence

- Manifest canonical SHA-256：`6c47c484b4ff1db073aaa79046c6986e3d236a3c34d3df5c3e6913fb19e6b33c`；
- Inventory canonical SHA-256：`372c395ffc36245be90327a01bd7a87c84491708fa507882738bf945c946f373`；
- Evidence files：`10813`，`1981539380` bytes。
