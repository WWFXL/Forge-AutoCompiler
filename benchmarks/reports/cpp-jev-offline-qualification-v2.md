# Jev 离线资格实验 v2 失败报告

## 决定

- Formal identity：`cpp-jev-offline-qualification-v2`
- Tracking Issue：[#397](https://github.com/WWFXL/Forge-AutoCompiler/issues/397)
- 终止阶段：`outcome_qualification`
- 决定：`stop_before_credential_read`
- Controller 决定：`stop_jev_controller_and_keep_offline_result`
- Credential read：`0`
- Provider call：`0`
- Model token：`0`
- Model cost：`$0`

本 identity 未进入 Jev design、calibration 或 evaluation。它在零 Provider 数据
收集阶段因 source checkout 传输故障失败，因此不构成 Jev 模型能力的正向或
负向结果。

## 前置门禁

修正后的 fault-trigger qualification 完成全部 72 次尝试。所有受控故障均形成
非零、非 timeout、有语义日志的有界失败；36 对重复执行的退出类别一致。
CMake、Make、Autotools 各 24 次，design 与 calibration split 各 36 次。

该结果支持 v2 的受控故障 fixture 有效，但不等于完整 outcome matrix 已建立。

## 失败事件

正式 outcome collection 在 6/24 个 replicate 完成后处理 `xxhash`。从 GitHub
检出冻结 exact commit 时，Git 因 GnuTLS 连接非正常终止而未能读完引用列表。
runner 按 create-once 协议写入 terminal failure marker 并停止。

这是 source checkout 的传输故障，不是故障构造、候选动作或 Jev 判断失败。
同一 identity 不允许 retry、replacement、resume 或 backfill。

## 部分证据

失败前已封存 6 个 replicate，覆盖 3 个项目族、9 个唯一状态、72 个动作
outcome 和 6 个 reference closure。已完成 reference closure 及其 strict checks
全部通过，已完成 action/strict 路径没有 timeout。

这些记录没有满足预注册的 36 个状态、288 个动作分支和 24 个 reference
closure 完整性门槛，不能用于形成 outcome matrix、标签分布、Jev 输入批次或
部分样本效果分析。它们只作为失败审计证据保留。

## Evidence

- Root：`.compile-sessions/benchmark-evidence-jev-offline-qualification-v2`
- 文件：`83`
- Inventory canonical SHA-256：`14fe4fd6cb4e60f792fc2c446d9f0b9fe5f857ce11c336534ef5c1939efc4e21`
- `identity.json` SHA-256：`b1c30fdc0afef78b8fe69fcd2e95074067f744d145d95635e8d168fde011c157`
- `fault-triggers.json` SHA-256：`0d27fb9ce1952a367eb058337bda30d549baa7730886ecb1cccdf57897a7245a`
- `outcome-terminal-failed.json` SHA-256：`b27fc0bdc024e0ef1510f2fb865258fd1753643d22035cc5a9e2566603bbb0b5`
- 失败后 qualification managed container：`0`
- Provider evidence 文件：`0`

## 结论边界

本结果支持：修正后的故障门禁有效；v2 因 source checkout 传输故障而失败关闭；
零 Provider 边界有效；本 identity 必须保持只读。

本结果不支持：Jev 的动作选择准确率、顺序稳定性、confidence 校准、延迟、费用
或模型排名；也不支持完整 benchmark 标签分布、controller 的严格成功率非劣、
成本下降、跨时间泛化或自然失败总体表现。

后续若继续，应建立独立 identity，在 formal evidence 创建前物化并校验全部
exact commit 的本地只读 source cache，避免运行中的远端 checkout 使科学门禁被
传输可用性截断。不得导入本 identity 的部分 outcome。
