# Jev 自然构建失败 source qualification v1 结果

- 状态：`failed`
- 决定：`attempt_failed`
- 候选：22；稳定自然失败：2
- Provider：0 request / 0 token；credential：0 read

## 角色配额

| 构建系统 | design | calibration | evaluation |
| --- | ---: | ---: | ---: |
| cmake | 1 | 0 | 1 |
| make | 0 | 0 | 0 |
| autotools | 0 | 0 | 0 |

## 项目结果

| 项目 | 系统 | 角色 | 分类 | 失败阶段 / 类别 |
| --- | --- | --- | --- | --- |
| `cmake-mold` | cmake | design | `source_contract_ineligible` | - |
| `cmake-flameshot` | cmake | design | `stable_natural_failure` | configure / unknown_build_failure |
| `cmake-openalpr` | cmake | calibration | `source_contract_ineligible` | - |
| `cmake-treefrog-framework` | cmake | calibration | `source_contract_ineligible` | - |
| `cmake-kvrocks` | cmake | evaluation | `stable_natural_failure` | configure / compile_error |
| `cmake-soloud` | cmake | evaluation | `source_contract_ineligible` | - |
| `cmake-srs` | cmake | evaluation | `source_contract_ineligible` | - |

## 解释边界

本结果只评估冻结项目能否形成稳定自然失败来源。它不验证 reference recipe、动作矩阵、
Jev/Agent 效果、成本收益或动态预算控制。
