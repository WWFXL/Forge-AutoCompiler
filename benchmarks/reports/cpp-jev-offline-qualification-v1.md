# Jev 离线资格实验 v1 失败报告

## 决定

- Formal identity：`cpp-jev-offline-qualification-v1`
- Tracking Issue：[#395](https://github.com/WWFXL/Forge-AutoCompiler/issues/395)
- 终止阶段：`outcome_qualification`
- 决定：`stop_before_credential_read`
- Controller 决定：`stop_jev_controller_and_keep_offline_result`
- Credential read：`0`
- Provider call：`0`
- Model token：`0`
- Model cost：`$0`

本 identity 未进入 Jev design、calibration 或 evaluation。它在零 Provider 数据资格阶段失败，因此不构成 Jev 模型能力的正向或负向结果。

## 失败事件

正式执行在 18/24 个 replicate 完成后处理 `zstd` calibration 项目的第 1 次 replicate。冻结故障删除 `lib/common/entropy_common.c`，随后执行 `make -C lib -j4 libzstd.a`；该命令没有形成预期的有界构建失败，runner 按协议抛出 `PilotError` 并写入 terminal failure marker。

根因是该 exact commit 的 `lib/libzstd.mk` 使用 `wildcard` 动态收集 `common` 目录中的 C 源文件。删除 `entropy_common.c` 后，它从构建输入集合中消失，而不是成为 Make 的缺失依赖。因此，当前故障 fixture 不适用于该项目和 commit。

## 部分证据

失败前已 create-once 封存 18 个 replicate，覆盖 9 个项目族、27 个状态、216 个动作 outcome 和 18 个 reference closure。已完成 reference closure 及其 strict checks 全部通过，已完成 action/strict 路径没有 timeout。

这些记录没有满足预注册的 36 个状态、288 个动作分支和 24 个 reference closure 完整性门槛，不能用于形成 outcome matrix、标签分布、Jev 输入批次或部分样本效果分析。它们只作为失败审计证据保留。

## Evidence

- Root：`.compile-sessions/benchmark-evidence-jev-offline-qualification-v1`
- 文件：`20`
- Inventory canonical SHA-256：`b1c52c54b5ccae8b6e21a841df480fdaba3415d333ee007a937688eba75633fb`
- `identity.json` SHA-256：`ef131abeafe878a955dde53e0a6df73c2a021ccacb9b304042d9d642019ad1ab`
- `outcome-terminal-failed.json` SHA-256：`3522f650bf46cf4d0f542d411e338698ce45c2f62a79b4f9283d1b74cf76f9f8`
- 失败后 Forge managed container：`0`
- Provider evidence 文件：`0`

## 结论边界

本结果支持：当前 zstd 受控故障不满足数据资格合同；失败关闭和零 Provider 边界有效；本 identity 必须保持只读，禁止重跑、续跑、补齐或覆盖。

本结果不支持：Jev 的动作选择准确率、顺序稳定性、confidence 校准、延迟、费用或模型排名；也不支持 controller 的严格成功率非劣、成本下降、跨时间泛化或自然失败总体表现。

若继续 Jev 研究，必须由研究负责人另行决定是否建立新 identity。新设计需要在正式执行前证明每个项目的故障触发本身可重复形成有界失败；不能把本 identity 的 18 个已完成 replicate 导入新 outcome matrix。
