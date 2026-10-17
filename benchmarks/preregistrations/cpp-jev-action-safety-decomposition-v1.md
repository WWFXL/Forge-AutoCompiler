# Jev 逐动作安全判断问题分解 v1 执行协议

## 身份

- Formal identity：`cpp-jev-action-safety-decomposition-v1`
- Tracking Issue：[#465](https://github.com/WWFXL/Forge-AutoCompiler/issues/465)
- Candidate identity：`cpp-jev-action-safety-decomposition-candidate-v1`
- Implementation revision：`4ce573d0fcd84b5df00073dbcc7a0b13c1b58040`
- Runner SHA-256：`94614ae19d2cbbf2b03a3391b775b6295b63d230a0f0e6eeac4a62bd411db603`
- Manifest canonical SHA-256：`36da3464515cd7c94cf255b167f9d2fb9cbb34baf88ccc3414db422fbda0d05b`

## 授权与预算

研究负责人已授权本 identity 读取仓库根 `jev-apikey.txt`、通过冻结 TypeSafe egress
调用 `jev-1.13.0`，并写入本 identity 的 create-once evidence。credential 和
Authorization header 不得进入日志、evidence、Issue、PR 或 Git。

- `action_noul`：15 calibration + 15 evaluation requests
- `action_card_noul`：15 calibration + 15 evaluation requests
- 最大物理请求：`60`
- 最大 input tokens：`400000`
- 最大 output tokens：`100000`
- 最大模型费用：`$0.0168`
- timeout 30 秒；SDK retry 0

## 固定执行

每个状态在请求前写 attempt，收到响应后先写不含 raw HTTP body 的 observation，再
校验固定模型、六个 Noul、概率、usage 和 request ID。任一失败都保留已写 evidence，
不 retry、replacement 或 backfill。

两个 condition 的 calibration 完成后分别拟合一维 Platt，并在最终最低成本动作
选择器上选择零 observed unsafe direct 且覆盖最大的阈值。随后按冻结顺序运行两个
evaluation split，一次性应用阈值和父 BudgetFit。即使 calibration 未达到最低覆盖，
evaluation 仍按预注册执行，以区分问题分解与 ActionCard 的诊断机制；该结果不能用于
放宽 controller 门禁。

本 identity 不运行历史四选一 evaluation，不修改历史 evidence，不实现 controller，
不支持端到端成功率、成本处理效应、自然失败、时间泛化或开放世界声明。
