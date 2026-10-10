# Jev 控制器零 Provider 回放资格实验 v2

- Tracking Issue：[#404](https://github.com/WWFXL/Forge-AutoCompiler/issues/404)
- Identity：`cpp-jev-controller-replay-qualification-v2`
- Implementation revision：`984532a2344b0f79152fea1731aec3816ca6ee16`
- Manifest canonical SHA-256：`309b02edf34db238e318e2b5f9fbe945692e0d946edb181f76028f1c5bd4ce28`

## 研究问题

固定 v6 响应进入最小控制器后，能否在 18 个 evaluation 状态上复现动作和校准门禁，并在输入、模型、候选、预算、前置条件或严格验证能力异常时全部升级 `escalate_agent`？

v1 的 `choice_probability_mismatch` 夹具概率和为 0.9，控制器安全升级但实际理由先命中 `probability_contract_invalid`，因此 v1 已按协议失败并永久停止。v2 不修改控制器，只修正该夹具的可辨识性，并冻结 v1 失败 evidence。

## 冻结输入

- v2 report SHA-256：`ea2e126e81cfca374900436fa670015b28b3cc3f9d8c83e746ae2c92d2badfed`
- v6 report SHA-256：`7a9d440acd0dc1b51eea7470563fc263b518fffd428b2e4bd6c3967ab696b2c6`
- v1 failure evidence inventory canonical SHA-256：`e11cf5aa77587606ec70e5454cbe8b9c2574a34f6c1249660096e5c469863538`
- v6 evidence inventory canonical SHA-256：`296a365e9ebb7b0148fb9662d2aa2edf3cc5c2dfcf0da943f3a521e751877521`
- calibration SHA-256：`1c2d4a24eeb407821ad4e56f41b62e50bef247c71764398044d51d3a24c835cf`
- evaluation analysis SHA-256：`311f3f977677cb9d77a4d74b6fba4b5cf3de79c37b7e332178e35f4d13b2f33c`
- 模型：`jev-1.13.0`
- 校准阈值：`0.6747568477098429`

## 回放与故障注入

正常路径按 state ID 重建 state、代码绑定候选、原始 Jev 决策和校准概率。
每个状态执行 18 个预先冻结的故障场景，共 324 个故障回放。
回放 executor 只记录被调度的代码绑定候选，不执行 Shell。

## 通过条件

- 18/18 正常路径与 v6 的动作、校准概率和 direct decision 一致；
- 18/18 调度回执均为 `awaiting_strict_verification`，不存在路由器终态成功；
- 324/324 故障回放升级 Agent，
  错误直接动作和故障 executor 调用均为 0；
- CMake、Make、Autotools 各覆盖 6 个正常状态；
- v1 failure 与 v6 evidence inventory 前后哈希不变；
- credential、Provider、模型 token、费用和 Shell 动作执行均为 0。

任一输入漂移、错误直接执行、故障路径 executor 调用、验证链绕过或计数不完整均立即停止并决定 `stop_before_end_to_end_canary`。全部通过才决定 `proceed_to_end_to_end_canary`。

## 解释边界

本实验只评价冻结响应进入控制器后的确定性路由和 fail-closed 边界。它不执行真实构建动作，不估计端到端成功率、Agent 调用、token、费用、墙钟时间或 treatment effect。
