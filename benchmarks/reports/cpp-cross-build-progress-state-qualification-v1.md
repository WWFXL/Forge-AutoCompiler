# 跨构建系统进展状态 v1 离线资格审计结果

> 日期：2026-10-09
> Tracking Issue：[382](https://github.com/WWFXL/Forge-AutoCompiler/issues/382)
> Identity：`cpp-cross-build-progress-state-qualification-v1`
> 类型：基础设施与结果分析；0 Provider、0 credential read、0 formal attempt

## 1. 结论

**决定：`abandon_current_progress_state_mechanism`。** 输入与重建门禁已闭合，但偏序状态未通过冻结的增量信息门槛。

本报告只评价固定历史轨迹中实际已选动作后的短期状态转移。它不估计未选动作、controller 因果效果或 strict success 改善。

## 2. 输入与隔离

| Split | Session | 项目族 | 决策点 | CMake | Make | Autotools |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `development` | 6 | 6 | 100 | 31 | 44 | 25 |
| `evaluation` | 24 | 12 | 309 | 160 | 61 | 88 |

输入清单闭合：`True`；manifest canonical SHA-256：`9340a10f005a9a90f980ac45356e8c13d00f35a7b095e30a68ccde610944ee6d`。开发/测试项目族零重合，且测试轨迹时间严格晚于开发轨迹。

## 3. 状态重建门禁

人工审计 12 个按哈希选择、未按标签抽样的决策点：obligation 字段一致率 `1.0000`，诊断一致率 `1.0000`，transition 一致率 `1.0000`；门禁 `通过`。

四类转移覆盖：

| Split | progress | lateral | stagnation | regression | 全覆盖 |
| --- | ---: | ---: | ---: | ---: | --- |
| `development` | 24 | 33 | 42 | 1 | 是 |
| `evaluation` | 76 | 59 | 170 | 4 | 是 |

## 4. 隔离比较

项目族内先平均，再对 12 个未见项目族宏平均。

| 特征组 | Log loss | Brier | Accuracy | Macro F1 |
| --- | ---: | ---: | ---: | ---: |
| `budget` | 0.6882 | 0.3929 | 0.7624 | 0.4135 |
| `context` | 0.7104 | 0.4078 | 0.7693 | 0.4224 |
| `error` | 0.6514 | 0.3629 | 0.7379 | 0.4649 |
| `simple_combined` | 0.6717 | 0.3746 | 0.7554 | 0.4693 |
| `progress_state` | 0.6701 | 0.3678 | 0.7537 | 0.4850 |

主要差值 `progress_state - simple_combined` 为 `-0.0016` nat，项目族 bootstrap 95% 区间 `[-0.1033, 0.1143]`；7/12 个项目族改善。

按构建系统的 log-loss 差值：

| 构建系统 | progress_state - simple_combined |
| --- | ---: |
| `cmake` | 0.0133 |
| `make` | -0.1390 |
| `autotools` | 0.1059 |

## 5. 预注册门槛

| 门槛 | 观测 | 通过 |
| --- | --- | --- |
| `input_integrity_and_isolation` | `true` | 是 |
| `four_class_coverage` | `{"development": {"lateral": 33, "progress": 24, "regression": 1, "stagnation": 42}, "evaluation": {"lateral": 59, "progress": 76, "regression": 4, "stagnation": 170}}` | 是 |
| `manual_reconstruction` | `{"obligation_agreement": 1.0, "transition_agreement": 1.0}` | 是 |
| `minimum_log_loss_improvement` | `0.0016212136746145411` | 否 |
| `bootstrap_upper_below_zero` | `0.114255163598367` | 否 |
| `brier_non_degradation` | `-0.006741100911633879` | 是 |
| `cross_build_system_consistency` | `{"autotools": 0.10590486186538972, "cmake": 0.01330636146217734, "make": -0.13900243948820246}` | 否 |

## 6. 解释边界

能够支持：

- 固定输入上的状态重建一致性；
- 固定 observed-action 转移标签上的隔离预测增量或缺失；
- 是否达到进入后续预算动作实验设计的预注册门槛；

不能支持：

- 未选择动作的反事实效果；
- controller treatment effect；
- strict success、时间、token 或费用改善；
- 跨更广项目总体的泛化；
- 模型排名、统计显著性或全球首次；

所有旧 experiment identity 和 evidence 在本审计中保持只读。
