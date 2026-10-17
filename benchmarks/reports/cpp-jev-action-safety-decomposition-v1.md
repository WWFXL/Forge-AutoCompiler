# Jev 逐动作安全判断问题分解 v1 报告

## 正式身份

- Identity：`cpp-jev-action-safety-decomposition-v1`
- Tracking Issue：[#465](https://github.com/WWFXL/Forge-AutoCompiler/issues/465)
- Implementation revision：`4ce573d0fcd84b5df00073dbcc7a0b13c1b58040`
- 决定：`stop_jev_action_safety_before_controller`
- 机制判断：`stop_jev_action_safety_before_controller`

## 结果

| 条件 | Cal direct | Eval direct | Eval wrong | Exact | Joint | TF-IDF match | Increment |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `action_noul` | 4/15 | 3/15 | 0 | 6/15 | 27/45 | False | False |
| `action_card_noul` | 3/15 | 2/15 | 0 | 5/15 | 25/45 | False | False |

## Provider 用量

- 物理请求：60/60
- Input tokens：95472
- Output tokens：7320
- 费用：`$0.004009824`

## 解释边界

本实验比较冻结受控构建状态上的逐动作 Noul 与 ActionCard 增强，并复用父 BudgetFit。它不估计 controller 的端到端成功率、成本处理效应、自然失败、时间泛化、开放世界或通用模型排名。四选一结果只来自 #463 冻结 calibration，本 identity 没有补齐其 evaluation。
