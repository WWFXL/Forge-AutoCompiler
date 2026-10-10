# Jev 离线资格实验 v6 预注册与授权执行协议

## 身份

- Formal identity：`cpp-jev-offline-qualification-v6`
- Tracking Issue：[#401](https://github.com/WWFXL/Forge-AutoCompiler/issues/401)
- Parent candidate：`cpp-jev-offline-qualification-candidate-v1`
- Parent failed identity：`cpp-jev-offline-qualification-v3`
- Parent revision：`72a0003bae19ff5c6a881853ad822725ee9b5447`
- Implementation revision：`9de7f68f3e7dcb377a6c1be335995b0a59466c68`
- Runner SHA-256：`3347f1bd4b2428fd80d6d727158362bcc85d45b9934f36d1f2de5b476b08cdc0`
- Manifest canonical SHA-256：`4d17426ecee591584bdfd6d1520c454d3e402d5da894ae54ec7c0841ba067eee`

## 授权与预算

本 identity 已获研究负责人授权读取仓库根 `jev-apikey.txt`、调用固定
`jev-1.13.0`、通过冻结 TypeSafe egress 调用 Provider，并写入本 identity 的
create-once evidence。credential 和 Authorization header 不得进入日志、
evidence 或 Git。

- 最大 Provider 请求：`72`
- 最大 input tokens：`1000000`
- 最大模型费用：`$0.042`
- Design：首轮 `18` 请求；仅首轮失败时允许一次版本化 prompt amendment 和最多 `18` 请求
- Calibration：`18` 请求
- Evaluation：一次性 `18` 请求

## 执行和停止边界

只读绑定 Issue #398 已通过资格门禁的完整 outcome matrix；不得导入其失败的
Provider attempt。Issue #399 已证明固定版本未被模型目录枚举，Issue #400 已证明
固定 `jev-1.13.0` 可直接调用，但在第 13 个 design 响应因原始概率和的 `1e-6`
容差过严而失败关闭。本 identity 不导入其部分预测，把原始概率和容差冻结为
`abs(sum - 1) <= 0.005`，保存原始概率与原始和，并将每个概率除以原始和后再用于
校准和指标。响应观察必须在语义校验前 create-once 封存，以准确计入 token 和费用。
模型版本、Choice schema、概率范围和最大项一致性仍严格校验，不使用 alias 回退。
Calibration 覆盖低于 `6/18` 时停止，不运行
evaluation。Evaluation 的 top-1、直接覆盖、错误直接动作、顺序一致性、
构建系统覆盖或预算任一门槛失败，决定均为
`stop_jev_controller_and_keep_offline_result`。

Issue #398、#399 和 #400 的 Provider attempt 不得导入本实验。本 identity 不授权修改历史
evidence，不授权 retry、replacement、backfill
或 evaluation 后调参，也不授权 controller 实现。结果不支持跨时间泛化、
自然失败总体、端到端严格成功非劣或成本下降声明。
