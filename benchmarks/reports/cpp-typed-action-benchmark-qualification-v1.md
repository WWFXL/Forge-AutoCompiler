# Jev 类型化动作 benchmark 阶段 A 资格报告

- identity：`cpp-typed-action-benchmark-qualification-v1`
- Issue：https://github.com/WWFXL/Forge-AutoCompiler/issues/389
- 完成时间：`2026-10-09T11:30:34.886912+00:00`
- 状态：`passed`
- 决定：`proceed_to_jev_offline_qualification`

## 资格结果

| 门槛 | 结果 |
|---|---|
| `project_count` | 通过 |
| `split_counts` | 通过 |
| `state_count` | 通过 |
| `candidate_execution_count` | 通过 |
| `reference_closure` | 通过 |
| `action_family_coverage` | 通过 |
| `replay_consistency` | 通过 |
| `historical_catalog_coverage` | 通过 |
| `all_build_systems_complete` | 通过 |
| `all_candidates_bounded` | 通过 |

共资格审计 24 个项目、120 个状态、720 次隔离候选执行。两次 replay 的 categorical outcome 一致率为 `1.0000`（360/360）。旧 409 个决策点的动作目录覆盖率为 `1.0000`（409/409）。

## 构建系统覆盖

| 构建系统 | 项目 | 状态 |
|---|---:|---:|
| autotools | 8 | 40 |
| cmake | 8 | 40 |
| make | 8 | 40 |

## 动作覆盖

| 动作族 | 独立状态数 |
|---|---:|
| `artifact_stage` | 48 |
| `build` | 55 |
| `configure` | 34 |
| `dependency` | 24 |
| `diagnostic_probe` | 72 |
| `escalate_agent` | 31 |
| `smoke` | 72 |
| `submit` | 24 |

## 解释边界

本报告只证明跨 CMake、Make、Autotools 的闭集候选动作 benchmark 在固定镜像上是否可执行和可重复。动作标签来自隔离执行后的真实证据；旧 Agent 动作未作为正确标签，旧 409 点只用于目录覆盖率。`submit` 只有在 candidate、functional、provenance 和 clean replay 四项全部闭合时才标记为可直接执行。

本阶段调用 Provider `0` 次，读取 credential `0` 次，模型调用 `0` 次，模型 token `0`；没有实现 Jev controller，也没有修改历史 evidence。因此本报告不能说明 Jev 判断准确率、校准质量、成本收益或端到端成功率。
