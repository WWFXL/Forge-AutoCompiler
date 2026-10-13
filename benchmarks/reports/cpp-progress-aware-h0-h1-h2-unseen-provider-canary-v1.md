# H0/H1/H2 未见项目族九臂 Provider Canary 结果

**决定：`proceed_to_unseen_three_arm_formal_comparison_design`。**

Q0：通过，0 credential read / 0 Provider request；Q1：`9/9` arms 分类终结。

## 描述性结果

- `h0_runtime_v3`：strict `3/3`，evaluated `3/3`，requests `25`，recorded tokens `162560`，cost `$0.056622`，replay closure events `0`。
- `h1_runtime_v4`：strict `3/3`，evaluated `3/3`，requests `21`，recorded tokens `118186`，cost `$0.042906`，replay closure events `0`。
- `h2_runtime_v5`：strict `2/3`，evaluated `2/3`，requests `48`，recorded tokens `553403`，cost `$0.269391`，replay closure events `9`。

## 硬门禁

- `batch_budget`：通过
- `budget_conserved`：通过
- `classified_terminal`：通过
- `cleanup`：通过
- `evaluator_coverage`：通过
- `h2_replay_closure_exercised`：通过
- `no_infrastructure_error`：通过
- `request_lifecycle_and_usage`：通过
- `schedule_complete`：通过
- `source_and_post_observation_bound`：通过
- `treatment_instrumentation`：通过

## 解释边界

本 canary 只评价三个冻结未见项目上 H0/H1/H2 的真实 Provider 生命周期、计量、treatment separation、严格终点覆盖与 cleanup；九臂数值不进入 treatment effect、非劣、成本节省比例或成功率泛化估计。

## Evidence

- Manifest canonical SHA-256：`ccd66bba742b7589ca93136f2eb39646b54a5fedeceb58fc0e05321b2791683c`；
- Inventory canonical SHA-256：`e911bb1d5d40fc270ede9921bbb4781bcd75d4851bf8fe4ef1f95d02f97e6696`；
- Evidence files：`3780`，`55020816` bytes。
