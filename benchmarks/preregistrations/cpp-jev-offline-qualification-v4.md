# Jev 离线资格实验 v4 预注册与授权执行协议

## 身份

- Formal identity：`cpp-jev-offline-qualification-v4`
- Tracking Issue：[#399](https://github.com/WWFXL/Forge-AutoCompiler/issues/399)
- Parent candidate：`cpp-jev-offline-qualification-candidate-v1`
- Parent failed identity：`cpp-jev-offline-qualification-v3`
- Parent revision：`72a0003bae19ff5c6a881853ad822725ee9b5447`
- Implementation revision：`c7d045afcc5a6df1ea062e93a2ecaa7089c5669e`
- Runner SHA-256：`7119e20e8326e4f5cdf7c65a02a6d77df57438314d2504096c005328876e7d63`
- Manifest canonical SHA-256：`665bf655a7c9bd5a44e2fe84d65a9122587fcea2dd4320a0d016cb5e6e1c9416`

## 授权与预算

本 identity 已获研究负责人授权读取仓库根 `jev-apikey.txt`、调用固定
`jev-1.13.0`、通过冻结 TypeSafe egress 调用 Provider，并写入本 identity 的
create-once evidence。credential 和 Authorization header 不得进入日志、
evidence 或 Git。

- 最大 Provider 请求：`72`
- 最大 availability metadata 请求：`1`
- 最大 input tokens：`1000000`
- 最大模型费用：`$0.042`
- Design：首轮 `18` 请求；仅首轮失败时允许一次版本化 prompt amendment 和最多 `18` 请求
- Calibration：`18` 请求
- Evaluation：一次性 `18` 请求

## 执行和停止边界

只读绑定 Issue #398 已通过资格门禁的完整 outcome matrix；不得导入其失败的
Provider attempt。Formal evidence 首先通过冻结代理调用一次 `/v1/models`，该
availability 请求不得触发模型推理；只有返回固定 `jev-1.13.0` 才可进入 design。
Calibration 覆盖低于 `6/18` 时停止，不运行
evaluation。Evaluation 的 top-1、直接覆盖、错误直接动作、顺序一致性、
构建系统覆盖或预算任一门槛失败，决定均为
`stop_jev_controller_and_keep_offline_result`。

Issue #398 的 Provider attempt 不得导入本实验。本 identity 不授权修改历史
evidence，不授权 retry、replacement、backfill
或 evaluation 后调参，也不授权 controller 实现。结果不支持跨时间泛化、
自然失败总体、端到端严格成功非劣或成本下降声明。
