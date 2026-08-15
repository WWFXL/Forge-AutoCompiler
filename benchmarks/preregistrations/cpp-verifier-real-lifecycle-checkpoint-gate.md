# Verifier-driven repair 真实生命周期 checkpoint 无模型门禁预注册

## 研究问题

Issue #135、#137、#139 和 #141 已分别证明消息、环境、预算 checkpoint 及其三层组合契约。本门禁只回答：能否把一次 neutral capture 接入真实 Compile Session、真实 Docker 容器和持久化 ledger evidence，在下一次 continuation 前冻结父状态，并从同一个 committed manifest 派生两个相互隔离的 continuation arm。

## 冻结范围

- 跟踪 Issue：#143。
- 使用实验专用 SQLite message checkpointer、SQLite capture coordinator、environment adapter 和 budget adapter；不修改生产 Compiler 图或 `_ACTIVE_EXPERIMENTS`。
- Docker 只使用 WSL2 `Ubuntu` 中由 `docker.service` 管理的原生 daemon，以及本地已有的 `autocompiler:gcc13` 镜像；不启动或回退到 Docker Desktop。
- 集成用例创建 synthetic Compile Session、synthetic ExperimentLedger 和确定性 verification failure。该 ledger 不是 formal collection，不进入模型能力、repair conversion 或端到端成功率分母。
- Provider calls、formal physical attempts 与 model tokens 均为 0；不读取或使用任何模型密钥。
- 不修改自然任务 ITT runner、Oracle、clean replay acceptance、正式 evidence、历史 Slot 7/10 或 verifier-driven repair 配对结果。
- 不授权 provider canary、mechanism slot、随机顺序、样本量、停止条件或 token ceiling。

## Capture 与发布契约

1. 真实 `submit_build_result_impl` 对无 artifact 的合成 Session 生成确定性 verification failure，并把 submit/failure evidence 持久化到 synthetic ledger。
2. 独立 compiler graph 只调用一次 submit callback，把中性 ToolMessage 写入 SQLite，并暂停在 `continue_model` 前。
3. coordinator 按 `preparing -> message_frozen -> environment_frozen -> budget_frozen -> committed` 推进；revision、lease 和 CAS 拒绝并发或越序修改。
4. environment adapter 在同一 pause 窗口冻结父容器 rootfs，并归档 workspace、artifacts、logs 与 repro bind mount；异常路径必须恢复 parent pause 状态。
5. budget adapter 固定 capture 前累计成本和两臂相同的 continuation budget。
6. `combined.json` 只在三层校验全部通过后原子发布；只有 coordinator 为 `committed` 且 manifest hash 有效时才能派生 arm。
7. 文件已发布但 coordinator 尚为 `budget_frozen` 的崩溃窗口，由 reconciler 校验现有文件后提交，不重复 submit 或重做环境 capture。

## Arm 与清理契约

- baseline/treatment 使用不同 thread、session、container、workspace、artifacts、message checkpoint 和 budget runtime identity。
- 两臂来自同一个 continuation image 和同一组只读 archive，初始 canonical 环境与预算相同。
- treatment 只在最后一个 ToolMessage 中附加 schema-valid repair packet；baseline 保留中性 verifier 反馈。
- 任一臂 rootfs、workspace、artifacts 或预算写入不得污染另一臂或只读父快照。
- arm provisioning 在 Session 或 container 边界中断后，reconciler 只清理该 capture/arm 的确定性资源，并允许从 `planned` 重试。
- cleanup 必须 finalize parent 与两臂、删除 capture 专属 helper/container/image/snapshot，并对账为无 paused parent、无 capture label orphan。

## Crash/reconcile 门禁

在 message freeze、parent pause、rootfs commit、各 bind archive、environment freeze、budget freeze、combined manifest write、arm Session creation 与 arm container creation 后注入进程崩溃。恢复必须满足以下之一：

- 已有完整且 hash 有效的下一阶段证据时，幂等推进到 `committed`；
- 证据不完整时进入 `aborted -> cleaned`，执行有界补偿；
- 不重复 parent submit，不重新消费 continuation budget，不遗留 paused container、helper、arm container、continuation image 或临时 snapshot。

## 通过条件

- coordinator 的 lease/CAS、状态顺序、identity 与 hash 漂移测试通过。
- synthetic actionable submit 实际只执行一次；SQLite 冷恢复仍从同一个 next node 派生两臂。
- 真实 Compile Session、`submit_build_result_impl`、synthetic ledger、Docker rootfs/bind capture、两臂 provisioning 与 cleanup 形成一次端到端非 provider 生命周期。
- 两臂初始 canonical 环境相同，单臂写入隔离；baseline/treatment budget runtime 相互独立。
- 所有预注册崩溃边界按契约继续或清理；Docker 对账无 capture orphan。
- 聚焦单元测试、唯一 opt-in Docker 集成用例、三个 checkpoint 原型及 compile lifecycle/task/replay 相邻回归通过。
- 实际计数固定为 0 provider calls、0 formal physical attempts、0 model tokens。

## 失效条件

- Ubuntu 原生 Docker 门禁失败，或测试使用 Windows Docker CLI、Docker Desktop 或其他 daemon。
- synthetic ledger 被写入正式 evidence 目录，或被计入任何模型/repair 效果分母。
- submit 重复执行、未提交 manifest 可派生 arm、任一 arm 污染另一 arm/父状态，或 cleanup 后存在 capture orphan。
- crash recovery 跳过 hash/identity 校验、重做已持久化副作用，或用宽泛 label 删除非本 capture 资源。
- 发生真实 provider 请求、formal physical attempt 或 model token 消耗。

## 已知适用边界

本门禁只覆盖 `replay_attempts == 0` 的 pre-replay actionable verification failure。已有 clean replay attempt 含独立 replay container identity 和 evidence，不能通过复制父 Session 直接归一化；若后续要覆盖 clean-replay mismatch，必须另行设计 evidence-only replay normalization 并单独预注册。

通过只证明真实 Session/Docker 生命周期的 checkpoint capture、双臂派生、崩溃恢复和清理可行；不证明 provider client、网络连接或进程内存可恢复，也不产生 verifier-driven repair 因果效果。任何真实模型 canary 或机制实验仍需新的中文 Issue、预注册和实验负责人授权。
