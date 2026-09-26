# Stage C v2 源码准备修复与完整重启预注册

日期：2026-09-26。追踪：Issue #321。来源：Stage C v1 失败审计 `benchmarks/reports/cpp-stage-c-paired-calibration-v1-failed.json`。

## 研究用途

本轮修复 Stage C v1 在首个正式 arm 之前的源码获取编排缺口。v1 的唯一 reachability 已通过，但第一项 A 臂在 `git fetch` 完成前中断，留下未闭合 pair；v1 必须保持只读且不得续跑。

v2 从 0 个 method outcome 重新执行完整的 12 projects × 2 replicates × 2 arms。不得导入 v1 outcome、pair、源码目录或 batch marker，也不得把 v2 解释成 v1 的续跑或补跑。

## 唯一允许变化

1. A/B 两臂的源码 clone、exact commit、source snapshot 和 build-system 身份检查在 create-once `attempt.json` 之前完成。
2. 前置源码准备使用 arm 专属临时空间或尚未登记的 Compile Session。失败时必须清理 managed resources；由于尚未登记正式 attempt，可以在同一 v2 identity 下重新启动 batch。
3. `attempt.json` 写入后，任何中断仍形成不可重试的正式 physical attempt；未闭合 pair 继续阻断整个 identity。
4. preflight 从 evidence 复算 reachability 和 arm 的请求、token、attempt 数，并把未闭合 pair 报告为 `ready=false`。
5. evidence 目录、pair ID、attempt ID、protocol、runner 和 manifest/schema identity 更新为 v2 remediation。

任务、exact commit、project order、replicate、arm order、A/B 方法逻辑、Provider/model、不可变镜像、每臂预算、48-arm 上限、统一 evaluator、S0-S5、严格成功定义与 project-level 配对分析保持不变。

## 新 identity

- evidence：`/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v2-remediation`
- pair：`stage-c-v2-{task_id}-r{replicate}`
- attempt：`stage-c-v2-{task_id}-r{replicate}-{arm}`
- v1 evidence：只读，不导入结果
- v2 reachability：只允许 1 request / 5,000 recorded tokens
- v2 formal arms：48 arms / 14,400,000 recorded tokens 硬上限
- v1 实际 reachability 与 v2 最坏上限合计：14,405,070 recorded tokens

## 执行顺序

1. 在合并后的干净 `main == origin/main` 上执行 `validate` 和非模型 `preflight`。
2. 核验 v1 失败审计、manifest、runner 和 evidence inventory 绑定。
3. 执行 v2 唯一 `reachability`。
4. 按冻结的 24-pair schedule 执行唯一 `batch`。
5. 只读生成 deployment、paired 和 inventory 报告，复算 usage、S0-S5、cleanup 与 0 managed resources。

## 停止规则

源码准备失败发生在 `attempt.json` 前时，batch 退出并保留 0 个新增正式 attempt；修复网络或宿主环境后可以重新启动同一 v2 batch。`attempt.json` 一旦存在，任何未闭合 arm 或 pair 都永久阻断 v2。禁止 retry、replacement、fallback、backfill、按结果重排和导入 v1 outcome。
