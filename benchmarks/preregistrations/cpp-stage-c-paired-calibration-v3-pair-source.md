# Stage C v3 pair 源码与产物验证修复预注册

日期：2026-09-26。追踪：Issue #323。来源：Stage C v2 失败审计 `benchmarks/reports/cpp-stage-c-paired-calibration-v2-failed.json`。

## 研究用途

Stage C v2 的首个 A 臂已闭合，B 臂在自己的正式 attempt 前因第二次 GitHub exact-commit fetch 中断。A 臂还暴露了 orchestrator 缺少 `file` 命令导致的产物验证环境漂移。v2 已形成未闭合 pair，必须保持只读且不得续跑。

v3 从 0 个导入 outcome 重新执行完整的 12 projects × 2 replicates × 2 arms。不得导入 v1/v2 outcome、pair、源码目录、reachability 或 batch marker，也不得把 v3 解释为 v2 的 retry、replacement 或 backfill。

## 唯一允许变化

1. 每个 pair 在首个 `attempt.json` 前只执行一次 remote clone、exact commit checkout、source snapshot 和 build-system identity 校验。
2. 验证后的 pair source 在临时空间派生 A、B 两个独立副本。两臂只读取各自副本；A/B attempt 开始后不再访问 GitHub，也不共享可变 workspace、artifacts、container rootfs 或 evidence。
3. 任一 pair source acquisition 或副本校验失败时清理临时空间和 managed resources。由于该 pair 尚无正式 attempt，可以在同一 v3 identity 下重新启动 batch。
4. A 臂 candidate 的 `file` 类型检查与静态库成员检查在 candidate image 内运行，使用冻结 Stage C 工具链、`network=none` 和只读 container rootfs。编排进程只复核复制后文件的路径、regular-file/symlink、大小、archive magic 与 SHA-256。
5. `attempt.json` 写入后，任何中断仍形成不可重试的正式 physical attempt；未闭合 pair 永久阻断 v3。
6. evidence 目录、pair ID、attempt ID、protocol、runner 和 manifest/schema identity 更新为 v3 pair-source。

任务、exact commit、project order、replicate、arm order、A/B 方法逻辑、Provider/model、不可变镜像、每臂预算、48-arm 上限、统一 evaluator、S0-S5、严格成功定义与 project-level 配对分析保持不变。

## 新 identity

- evidence：`/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v3-pair-source`
- pair：`stage-c-v3-{task_id}-r{replicate}`
- attempt：`stage-c-v3-{task_id}-r{replicate}-{arm}`
- v1/v2 evidence：只读，不导入结果
- v3 reachability：只允许 1 request / 5,000 recorded tokens
- v3 formal arms：48 arms / 14,400,000 recorded tokens 硬上限
- v1 与 v2 实际消耗：42,001 recorded tokens
- 历史实际消耗与 v3 最坏上限合计：14,447,001 recorded tokens

## 执行顺序

1. 在合并后的干净 `main == origin/main` 上执行 `validate` 和非模型 `preflight`。
2. 核验 v2 失败审计、manifest、runner、Stage C image 和 evidence inventory 绑定。
3. 执行 v3 唯一 `reachability`。
4. 按冻结的 24-pair schedule 执行唯一 `batch`。
5. 只读生成 deployment、paired 和 inventory 报告，复算 usage、S0-S5、cleanup 与 0 managed resources。

## 停止与恢复规则

pair source 准备失败发生在首个 `attempt.json` 前时，batch 退出且不增加正式 attempt；修复网络或宿主环境后可以重新启动同一 v3 batch。只有完整连续 pair 前缀可以在 batch 进程退出后跳过。任一 `attempt.json` 已存在但 pair 未闭合时，整个 v3 identity 永久停止。禁止 retry、replacement、fallback、backfill、按结果重排以及导入 v1/v2 outcome。
