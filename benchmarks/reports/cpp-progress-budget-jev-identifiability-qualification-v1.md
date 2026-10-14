# 进展预算感知 Jev 联合 benchmark 可辨识性资格 v1 结果

- Identity：`cpp-progress-budget-jev-identifiability-qualification-v1`；
- Tracking Issue：[#457](https://github.com/WWFXL/Forge-AutoCompiler/issues/457)；
- 执行 revision：`e26033ef83a159795bdb93b7bf9caf26deefb116`；
- 决定：`proceed_to_jev_progress_budget_calibration_design`。

## 关键结论

联合 benchmark 通过可辨识性资格，允许进入独立 Jev 进展预算校准设计；尚未授权 Provider 或完整 controller。

本阶段在 6 个未见项目族上真实执行五类状态、四类动作和三种 matched budget。标签来自两次 action branch 的严格结果与冻结预算可行性，不使用人工期望或旧 Agent 行为。

## 结果

- 项目：`6`；
- 语义状态：`30`；
- action branches：`240`；
- matched budget decisions：`90`；
- action replay 一致率：`1.0000`；
- RuleGate route accuracy：`0.6000`；
- TF-IDF+BudgetFit action top-1：`0.8000`；
- TF-IDF+BudgetFit route accuracy：`0.8667`；
- 发生预算路由变化的状态：`30/30`；
- replay dependency recoveries：`12/12`。

| 最优动作 | 状态数 |
|---|---:|
| `dependency` | 12 |
| `configure` | 6 |
| `build` | 6 |
| `escalate_agent` | 6 |

| 最优路由 | decision 数 |
|---|---:|
| `direct` | 48 |
| `escalate_agent` | 6 |
| `stop` | 36 |

| 门槛 | 结果 |
|---|---|
| `expected_counts` | 通过 |
| `reference_closure` | 通过 |
| `replay_consistency` | 通过 |
| `cross_system_action_and_route_support` | 通过 |
| `rule_gate_below_ceiling` | 通过 |
| `tfidf_budgetfit_below_ceiling` | 通过 |
| `matched_budget_changes_route` | 通过 |
| `replay_rejection_and_recovery` | 通过 |
| `no_direct_label_leakage` | 通过 |
| `bounded_execution` | 通过 |
| `budget_and_observation_closure` | 通过 |
| `zero_provider_boundary` | 通过 |
| `cleanup` | 通过 |

## 解释边界

本结果只评价 benchmark 的联合可辨识性。它不估计 Jev、真实 Agent 或 controller 效果，不支持成功率非劣、Provider 成本下降、自然失败或开放世界结论。Agent reservation 是冻结规划量，实际 credential、Provider、Jev、Agent 和 model token 均为 0；历史 evidence 未修改。

## Evidence

- Root：`.compile-sessions/benchmark-evidence-progress-budget-jev-identifiability-qualification-v1`；
- Inventory：`702` files / `2851071` bytes；
- Inventory canonical SHA-256：`2e4209fb52c07af949789ae7880db478f5a6d9326b4496de7fcff45ad64da9e9`；
- Cleanup：`0` managed resource。
