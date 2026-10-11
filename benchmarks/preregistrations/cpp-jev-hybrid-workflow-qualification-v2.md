# Workflow + Jev + Agent 混合链路零 Provider 资格 v2 预注册

日期：2026-10-11。追踪：Issue #409。身份：`cpp-jev-hybrid-workflow-qualification-v2`。

v1 在第一个 CMake case 已完成严格 submit、clean replay 和 `completed` cleanup，但报告序列化读取不存在的 `CompileSession.replay_verification` 字段，因 `AttributeError` 按停止规则终止。v1 marker、失败报告和 Session 证据保持只读。

v2 只修复取证字段：从 `CompileSession.replay_attempts[-1].status` 读取最新 replay 状态。协调器、Jev 门禁、代码绑定命令、三个 case、预算、通过门槛和结论边界全部沿用 v1。v2 使用新的 create-once evidence root；它不是 v1 retry、replacement 或 backfill。

## 固定边界

- Provider call、credential read、formal attempt：全部为 0。
- 3 个 qualification attempt，每个 case 恰好一次；首个不可恢复失败立即停止。
- 每个 case 最多 2 个循环、1 个直接动作、1 次 Agent handoff、1800 秒墙钟，单命令 900 秒。
- 三个构建系统都必须通过真实命令、显式 smoke、严格 submit、commit-pinned clean replay 和 cleanup。
- 至少观察两次 Jev 直接动作后的 Workflow 接管，以及一次 Agent handoff 后的 Workflow 接管。

全部门槛通过时决定为 `proceed_to_provider_canary_identity_freeze`；任一失败时决定为 `stop_and_repair_hybrid_workflow`。结果仍只属于工程链路资格，不支持自然失败效果、Provider 成本、动态预算或模型排名主张。
