# Workflow + Jev + Agent 混合链路零 Provider 资格 v3 预注册

日期：2026-10-11。追踪：Issue #409。身份：`cpp-jev-hybrid-workflow-qualification-v3`。

v2 的 CMake 与 Make case 均通过 Jev 直接动作、严格 submit、clean replay 和 cleanup。Autotools case 的 Agent dependency、configure、build 和 stage 均成功，但固定 smoke 执行上游 `check_check` 自测；该二进制包含预期的 fixture failure，返回 1。协调器正确拒绝成功并在单 handoff 预算耗尽后停止。v2 marker、失败报告和 Session 证据保持只读。

v3 只替换 Autotools 功能 oracle：在同一 build 命令中用 `libcheck.a` 与 `libcompat.a` 编译一个调用 `suite_create` 的最小程序，stage 后直接运行。隔离诊断已确认该程序在冻结镜像与项目提交下是有效 ELF 且返回 0。协调器、Jev 门禁、CMake/Make case、预算和通过门槛均不变。

## 固定边界与门槛

- 新 create-once identity；不是 v2 retry、replacement 或 backfill。
- Provider call、credential read、formal attempt 全部为 0。
- 三个 case 各一次，首个不可恢复失败立即停止。
- 每个 case 最多 2 个循环、1 个直接动作、1 次 Agent handoff、1800 秒墙钟，单命令 900 秒。
- CMake、Make、Autotools 都必须得到严格 submit、显式功能 smoke、commit-pinned clean replay、`completed` cleanup 和 0 受管资源。
- 至少观察两次 Jev 直接动作后 Workflow 接管，以及一次 Agent handoff 后 Workflow 接管。

全部通过时决定为 `proceed_to_provider_canary_identity_freeze`；任一失败时为 `stop_and_repair_hybrid_workflow`。结果只属于工程链路资格，不支持自然失败效果、Provider 成本、动态预算或模型排名主张。
