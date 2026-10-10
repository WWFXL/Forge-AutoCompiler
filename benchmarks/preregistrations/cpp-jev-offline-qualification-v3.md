# Jev 离线资格实验 v3 预注册与授权执行协议

## 身份

- Formal identity：`cpp-jev-offline-qualification-v3`
- Tracking Issue：[#398](https://github.com/WWFXL/Forge-AutoCompiler/issues/398)
- Parent candidate：`cpp-jev-offline-qualification-candidate-v1`
- Parent failed identity：`cpp-jev-offline-qualification-v2`
- Parent revision：`72a0003bae19ff5c6a881853ad822725ee9b5447`
- Implementation revision：`51751d9e48194aa872d5dae338ae431e946e2e67`
- Runner SHA-256：`a1cdf87bd616bf1f43ef68933198227d029179b2dfb11a088773d2287ae8ce22`
- Manifest canonical SHA-256：`b96c6ab0f8b3306607711b2fe7a6c6aebeebfc0455943547b029727149857c55`

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

Formal evidence 创建前必须完成 12 个 exact commits 的 Git bundle 物化与本地
clone 审计；bundle SHA、commit、source snapshot、license、gitlink 与 tracked
file count 全部通过后，formal 阶段禁止远端 source checkout。随后完成 12 项目 ×
3 faults × 2 replicates 的零 Provider fault-trigger
qualification；72 次均须形成非零、非 timeout、有日志且重复退出类别一致的
有界失败。通过后才可从全新 checkout 完成 12 个 design/calibration 项目族的
outcome qualification；
只有 reference closure、重复一致性、动作覆盖、候选有界终结和泄漏审计
全部通过才可读取 credential。Calibration 覆盖低于 `6/18` 时停止，不运行
evaluation。Evaluation 的 top-1、直接覆盖、错误直接动作、顺序一致性、
构建系统覆盖或预算任一门槛失败，决定均为
`stop_jev_controller_and_keep_offline_result`。

Issue #397 的部分 outcome 不得导入本实验。本 identity 不授权修改历史
evidence，不授权 retry、replacement、backfill
或 evaluation 后调参，也不授权 controller 实现。结果不支持跨时间泛化、
自然失败总体、端到端严格成功非劣或成本下降声明。
