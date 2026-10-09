# Jev 离线资格实验 v1 授权执行补充

## 身份

- Formal identity：`cpp-jev-offline-qualification-v1`
- Tracking Issue：[#395](https://github.com/WWFXL/Forge-AutoCompiler/issues/395)
- Parent candidate：`cpp-jev-offline-qualification-candidate-v1`
- Parent revision：`72a0003bae19ff5c6a881853ad822725ee9b5447`
- Implementation revision：`1d1840f9e52f27d79dae644a189f20f32c701c3e`
- Runner SHA-256：`c4815e71c8079940c4735d08824153766a6d21eee5995de09cea59466f268771`
- Manifest canonical SHA-256：`e98b6b3e3a485ca26f3185491f460cc5a6b447f64d7a15d5fac9fcf72daf6616`

## 授权与预算

本 identity 已获研究负责人授权读取仓库根 `jev-apikey.txt`、调用固定
`jev-1.13.0`、执行 Docker outcome collection，并写入本 identity 的
create-once evidence。credential 和 Authorization header 不得进入日志、
evidence 或 Git。

- 最大 Provider 请求：`72`
- 最大 input tokens：`1000000`
- 最大模型费用：`$0.042`
- Design：首轮 `18` 请求；仅首轮失败时允许一次版本化 prompt amendment 和最多 `18` 请求
- Calibration：`18` 请求
- Evaluation：一次性 `18` 请求

## 执行和停止边界

先完成 12 个 design/calibration 项目族的零 Provider outcome qualification；
只有 reference closure、重复一致性、动作覆盖、候选有界终结和泄漏审计
全部通过才可读取 credential。Calibration 覆盖低于 `6/18` 时停止，不运行
evaluation。Evaluation 的 top-1、直接覆盖、错误直接动作、顺序一致性、
构建系统覆盖或预算任一门槛失败，决定均为
`stop_jev_controller_and_keep_offline_result`。

本 identity 不授权修改历史 evidence，不授权 retry、replacement、backfill
或 evaluation 后调参，也不授权 controller 实现。结果不支持跨时间泛化、
自然失败总体、端到端严格成功非劣或成本下降声明。
