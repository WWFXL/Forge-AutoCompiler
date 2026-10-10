# Jev 离线资格实验 v3 失败报告

## 决定

- Formal identity：`cpp-jev-offline-qualification-v3`
- Tracking Issue：[#398](https://github.com/WWFXL/Forge-AutoCompiler/issues/398)
- 终止阶段：`provider_design_round_1`
- 决定：`stop_jev_controller_and_keep_offline_result`
- Credential read：`1`
- Physical Provider request：`1`
- Completed response：`0`
- Model token：`0`
- Model cost：`$0`

本 identity 完成了 source cache、fault-trigger 和 outcome qualification，但在首个
Jev design 请求得到模型响应前，被 TypeSafe API 以 HTTP 451 和
`Typesafe is not available in your region.` 拒绝。该结果只证明当前服务器的直连
Provider 路径不可用，不构成 Jev 模型能力的正向或负向结果。

## 数据资格

12 个 exact commits 已物化为 12 个冻结 Git bundles，总大小 85,060,643 bytes。
所有 bundle 首次获取成功，且在 formal evidence 创建前通过本地 clone、commit、
source snapshot、license、gitlink 和 tracked-file count 复核。Formal clone 不再
访问远端 repository。

Fault-trigger qualification 完成 72/72 次尝试，全部为非零、非 timeout、日志
非空的有界失败，36 对重复执行的退出类别一致。

Outcome qualification 完成 36 个唯一状态、288 个动作分支和 24 个 reference
closures。144/144 state-action pairs 的两次 categorical replay 一致，所有候选
有界终止，全部 reference closure 通过，无直接标签泄漏。Design 与 calibration
各 18 状态；每个 split 中 CMake、Make、Autotools 各 6 状态，最优动作
`dependency`、`configure`、`build` 各 6 状态。

这些结果支持 outcome benchmark 合格，但不包含任何 Jev 完成响应。

## Provider 失败

Runner 已按授权读取一次 `jev-apikey.txt`，在写入第一个 physical attempt marker
后调用固定 `jev-1.13.0`。Provider 返回 HTTP 451，未提供 request ID、模型响应或
usage。Runner 未 retry，写入 `failed.json` 后停止；credential 和 Authorization
header 未进入 evidence。

同一 identity 不允许通过代理重试、续跑或补齐。任何新的网络路径必须先作为独立
availability 条件审计，再建立新 identity。

## Evidence

- Root：`.compile-sessions/benchmark-evidence-jev-offline-qualification-v3`
- 文件：`105`
- Inventory canonical SHA-256：`1e931f3124973b69daf24871a7b92d1b0cd982b8dc9e7baa51a324966c178507`
- `identity.json` SHA-256：`9dab80e3c0bac3ec370a2f1451eef5a59fef4dc22d3d13e96be8ebe56f64123c`
- `fault-triggers.json` SHA-256：`c256276c304b521958f994d9b1dfea3a80bfe94e223d48b69a55e8f653f24e29`
- `outcomes.json` SHA-256：`8fd490d8cc9e2517c1ff8e182a8e0930e103a6b6c9b2ff426904deede9d2cf93`
- Provider `failed.json` SHA-256：`75028da23c2c1c6bff2fdb343c24d98e2d36ab853ba7d207c54fa1d8ecaf744b`
- 失败后 qualification managed container：`0`

## 结论边界

本结果支持：v3 source-cache 修复有效；新的 36-state outcome benchmark 完整、
平衡且重复一致；当前服务器直连 TypeSafe API 不可用；v3 必须保持只读。

本结果不支持：Jev 的动作选择准确率、顺序稳定性、confidence 校准、延迟、token、
费用或模型排名；也不支持 controller 的严格成功率非劣、成本下降、跨时间泛化或
自然失败总体表现。
