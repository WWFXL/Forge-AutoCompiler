# Checkpoint 六配对 pilot coordinator WAL recovery amendment

Issue #159 的 `pair-01` 已形成双臂 passed、clean replay passed、pair marker passed、controlled report passed、Session 全部终结与 0 orphan，但 v1 外层 `immutable=1` 审计在 WAL checkpoint 前读取到旧 coordinator phase，导致 batch marker false negative。Issue #161 授权一个不重跑 `pair-01` 的 recovery amendment。

## 冻结输入

- v1 manifest canonical SHA-256 固定为 `d5edd9683def7c8842ad1eb0471cce877b47b52b2939f1b45d9c2a51f2362391`。
- v1 输出目录的文件集合固定为 8 个文件；batch/pair marker、controlled report、parent/baseline/treatment ledger、coordinator 和 messages SQLite 均固定 SHA-256。
- parent、baseline 与 treatment 的 Session JSON 固定 SHA-256；三者均已终结，当前 0 Compile Session/replay orphan。
- 导入的 `pair-01` 记录 23,811 tokens，baseline/treatment 均为完整 pair，只计一次且禁止重跑、replacement 或 backfill。

## 剩余执行

- recovery 使用独立 manifest、batch marker 和 evidence 目录 `/workspace/.compile-sessions/benchmark-evidence-checkpoint-censored-pilot-recovery-v1`。
- 只执行原预注册的 `pair-02` 至 `pair-06`，保持原 arm order；不创建新的 `pair-01`，不扩展到第 7 个 pair。
- 新增执行最多 10 arms × 120,000 = 1,200,000 recorded tokens；与导入的 23,811 tokens 合并后仍受原 1,440,000 总上限约束。
- provider、300 秒 timeout、0 retry、非 streaming、fallback 禁止、endpoint timeout 删失规则和双 estimand 均不改变。

## Copy-based SQLite 审计

pair 停止写入后，runner 枚举并哈希源 `coordinator.sqlite`、`-wal`、`-shm`，复制存在的文件到进程临时目录，在副本中重建 SHM/回放 WAL 并读取唯一 capture。读取后再次核对源文件集合与哈希未变。所有 SQLite recovery/checkpoint 和 sidecar 变化只能发生在临时副本，不得修改 evidence 源目录。

只有副本中的 coordinator 为 `cleaned`、`cleanup.succeeded=true` 且 daemon 为 0 Compile Session/replay orphan 时，pair 才能进入 complete 或 endpoint-censored 终态。其他 cleanup、identity、evidence、预算与非 endpoint 错误仍失败关闭。

## 分析边界

最终报告固定分母为最初预注册的 6 pair：导入 `pair-01` 加 recovery 执行的 5 pair。ITT/attrition 包含所有六 pair；conditional mechanism 只包含完整双臂 pair。只做描述性分析，不计算 p 值，不做模型排名。
