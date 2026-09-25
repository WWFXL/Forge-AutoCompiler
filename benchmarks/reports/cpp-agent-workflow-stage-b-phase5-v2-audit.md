# Phase 5 v2 结果审计

源 release：`5ed549ea92add2403a91512d3148f29686559d67`；manifest：`aa1f9ec280cbbecf91b5e10a9724e9b2462aed8dccc44bfb906c5e3e1ef962ed`。

## 原始结果

唯一 batch 已完成调度和报告生成。generated=6/6，submitted=5/6，strict=1/6，bitwise=2/6；总 recorded tokens=918,179。batch marker 的 `passed` 只表示执行闭合，不表示六项目严格通过。

## 审计判定

可靠成功 1 项，明确工作流失败 2 项，evaluator 缺陷导致不可判定 3 项。该分类是事后审计，不能用于无偏成功率主张，也不能把不可判定项目追认为成功。

| 项目 | 审计分类 | 原始 strict | 依据 |
|---|---|---:|---|
| `yyjson` | `workflow_failure` | 否 | undeclared_compiled_artifact |
| `cppitertools` | `reliable_success` | 是 | all_s0_s5_layers_passed |
| `openh264` | `invalid_due_to_evaluator_defect` | 否 | system_oracle_inherited_agent_post_build_budget |
| `uwebsockets` | `workflow_failure` | 否 | invalid_candidate_contract_then_graph_recursion_limit |
| `c-ares` | `invalid_due_to_evaluator_defect` | 否 | system_oracle_inherited_agent_post_build_budget |
| `libass` | `invalid_due_to_evaluator_defect` | 否 | system_oracle_inherited_agent_post_build_budget |

## 决策

Stage C 继续阻断。当前 batch 已全部消费，不允许重跑、retry、replacement 或 backfill。下一步是合并 evaluator v3 修复，再为新的独立评测设计授权 identity。

## Evidence 完整性

原始报告 SHA-256：`4cab2400927ef2a557ab81e7deeba26d3ee5aad85e716ca56157516a865c4d6c`。原始 decision SHA-256：`7e8000f10b8c6026a5908b1b6634e4c8ccbf323762e369d3d47ae5c7b0045a5d`。历史 evidence 未修改。发现 6 个 root:root/0600 ledger；修复只作用于未来 evidence。
