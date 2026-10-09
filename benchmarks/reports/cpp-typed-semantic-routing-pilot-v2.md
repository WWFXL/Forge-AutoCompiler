# 同阶段异根因类型化语义路由 benchmark v2 结果

- identity：`cpp-typed-semantic-routing-pilot-v2`
- tracking Issue：[#391](https://github.com/WWFXL/Forge-AutoCompiler/issues/391)
- 执行 revision：`b8b68b1a5457e0097c3d4d1a8213595c73178ece`
- 决定：`proceed_to_jev_offline_qualification`

## 关键结论

v2 同阶段异根因 benchmark 通过零 Provider 难度门禁。简单 RuleGate 与项目族隔离的 TF-IDF/逻辑回归均未饱和，因此存在进入独立 Jev 离线资格实验的可辨识空间。

本轮在完全相同的 coarse phase facts 下，对 6 个项目各构造 3 个故障状态。每个 state/action pair 执行两次，候选动作后统一运行 build、artifact stage、functional oracle、provenance 和 clean replay。最优动作由 strict success 优先、冻结成本次优确定，没有使用旧 Agent 行为或人工故障类别作标签。

## 结果

- 项目：`6`
- 状态：`18`
- action branches：`144`
- reference closures：`12`
- categorical replay 一致率：`1.0000`
- RuleGate top-1：`0.3333`
- RuleGate route-acceptable coverage：`0.3333`
- LOPO TF-IDF/逻辑回归 top-1：`0.9444`

| 构建系统 | 状态数 |
|---|---:|
| cmake | 6 |
| make | 6 |
| autotools | 6 |

| 最优动作 | 状态数 | project family 数 |
|---|---:|---:|
| dependency | 6 | 6 |
| configure | 6 | 6 |
| build | 6 | 6 |
| escalate_agent | 0 | 0 |

| 门禁 | 结果 |
|---|---|
| `expected_counts` | 通过 |
| `reference_closure` | 通过 |
| `replay_consistency` | 通过 |
| `all_build_systems_complete` | 通过 |
| `direct_actions_optimal_in_two_project_families` | 通过 |
| `rule_gate_top1_below_ceiling` | 通过 |
| `rule_gate_coverage_below_ceiling` | 通过 |
| `tfidf_top1_below_ceiling` | 通过 |
| `no_direct_label_leakage` | 通过 |
| `all_candidates_bounded` | 通过 |

## 解释边界

本 pilot 只回答 benchmark 是否能在相同阶段事实下形成异根因、异最优动作，并抵抗两个零 Provider 基线。它没有调用 Jev 或通用 LLM，不估计 confidence、费用、延迟、controller 成功率或端到端 treatment effect。`escalate_agent` 使用确定性零 Provider recovery surrogate，只保证每个状态存在兜底路径，不代表真实 Agent 效果。

Provider `0` 次、credential `0` 次、模型调用 `0` 次、模型 token `0`；历史 evidence 保持只读。
