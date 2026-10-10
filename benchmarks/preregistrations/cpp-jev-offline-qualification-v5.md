# Jev 离线资格实验 v5 预注册与授权执行协议

## 身份

- Formal identity：`cpp-jev-offline-qualification-v5`
- Tracking Issue：[#400](https://github.com/WWFXL/Forge-AutoCompiler/issues/400)
- Parent candidate：`cpp-jev-offline-qualification-candidate-v1`
- Parent failed identity：`cpp-jev-offline-qualification-v3`
- Parent revision：`72a0003bae19ff5c6a881853ad822725ee9b5447`
- Implementation revision：`6c5c7f984bc5ce4001a6b01077ab75cf530ffca6`
- Runner SHA-256：`b2e434db688e4b969cf7853069c37cc124ee0057407e318d278a65635e89afde`
- Manifest canonical SHA-256：`1ae7b5059083ca9db3385b02dfca3f54dbffee75e073199f69701cd9eb8025bd`

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
Provider attempt。Issue #399 的 `/v1/models` 已成功返回 `jev-latest` 与
`jev-preview`，但目录未枚举官方文档仍列出的稳定版本 `jev-1.13.0`。本 identity
不再把目录枚举作为精确版本白名单，而是直接以固定 `jev-1.13.0` 执行首个 design
请求；API 拒绝或响应 `model` 不精确等于请求值时立即失败关闭，不使用 alias 回退。
Calibration 覆盖低于 `6/18` 时停止，不运行
evaluation。Evaluation 的 top-1、直接覆盖、错误直接动作、顺序一致性、
构建系统覆盖或预算任一门槛失败，决定均为
`stop_jev_controller_and_keep_offline_result`。

Issue #398 和 #399 的 Provider attempt 不得导入本实验。本 identity 不授权修改历史
evidence，不授权 retry、replacement、backfill
或 evaluation 后调参，也不授权 controller 实现。结果不支持跨时间泛化、
自然失败总体、端到端严格成功非劣或成本下降声明。
