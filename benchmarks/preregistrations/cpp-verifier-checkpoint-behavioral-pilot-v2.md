# Checkpoint 行为终态 v2 六配对实验预注册

本协议承接 Issue #163 的选择 A 决策和 Issue #165 的长程任务授权。路线 B v1 的 pair-01 与 recovery pair-02 只作为 exploratory feasibility evidence；旧 pair-03 至 pair-06 永不执行，也不与 v2 池化。

## 研究问题与 estimand

研究变量保持不变：在同一个 actionable verifier failure checkpoint 上，treatment 向 compiler continuation 提供结构化 repair packet，baseline 不提供。Primary mechanism estimand 比较 candidate verification + clean replay 的 repair conversion。

Replay success 是 outcome，不再兼任采集纳入 gate。只有两臂均被尝试且 infrastructure 为 `valid` 的 pair 进入 primary mechanism 分母；其中 `GraphRecursionError`、work wall-clock 耗尽、无 submit 和 verification failed 都以失败 outcome 保留。

## 身份、provider 与预算

- 语言固定为 C/C++，controlled fault 固定为 `artifact_staging_missing`。
- provider 固定为 DeepSeek `deepseek-v4-flash` 与 `https://api.deepseek.com`；300 秒 timeout、0 retry、非 streaming、禁止 fallback。
- 新建 6 pair / 12 arms；pair 1/3/5 为 `baseline -> treatment`，pair 2/4/6 为 `treatment -> baseline`。
- 每臂最多 8 requests、8 model turns、24 graph steps、600 秒 work + 120 秒 cleanup、120,000 recorded tokens；总机械上限 1,440,000 recorded tokens。
- 禁止 replacement、backfill、补跑、第 7 个 pair 和任何旧 pair 复用。

## 三层 arm 终态

每个已尝试 arm 同时记录：

1. `infrastructure`: `valid` / `endpoint_censored` / `invalid`；
2. `model_behavior`: `completed` / `graph_step_limit` / `work_wall_clock_limit` / `no_submit` / `verification_failed` / `not_observed`；
3. `verification_outcome`: `passed` / `failed` / `not_attempted`。

唯一合法 endpoint timeout 需要请求/失败分类、0 retry、ledger 哈希链、预算和 cleanup 全部闭合，记为 `endpoint_censored`。它进入 ITT/attrition，但不进入 primary mechanism 分母。第一臂出现 endpoint censoring 或可分类模型行为失败时，第二臂仍继续。

Release/manifest/evidence identity 漂移、ledger 损坏、预算越界、cleanup/orphan 或无法分类的异常属于 hard infrastructure failure，立即关闭 batch。

## Evidence 与停止规则

- v2 只写入 `/workspace/.compile-sessions/benchmark-evidence-checkpoint-behavioral-pilot-v2`。
- 每个 `v2-pair-NN` 使用独立 checkpoint、ledger、marker、outcome 与 Compile Session。
- 已形成合法 pair outcome 的 pair 在同一 started batch 恢复时只读跳过；存在部分内容但没有终态时禁止自动补跑。
- v1/recovery 的文件集合和 SHA-256 在 v2 manifest 中冻结，运行前只读核验；旧目录不得删除、覆盖或写 sidecar。
- 每个 pair 后核验累计 recorded tokens 与 0 Compile Session/replay orphan。

## 分析边界

- ITT/attrition 固定分母为 6 个新 pair，报告 attempted arms、endpoint censoring 和 hard infrastructure stop。
- Primary mechanism 报告 infrastructure-valid 双臂 pair 的 baseline/treatment repair success、配对 conversion delta 和模型行为失败分类。
- 请求数、tokens、submit/replay 次数与 wall-clock 只按终态做条件描述。
- 仅做描述性机制评估，不计算 p 值、不做模型排名、不跨 provider 外推。

## 发布与执行

实现合并前只允许 0-provider 单测、Ruff、确定性 manifest/Schema、历史 evidence 核验和真实 Compose/DooD fake-model 门禁。真实采集必须位于干净 `main == origin/main`，使用 WSL Ubuntu 原生 Docker Engine，网络介质记录为 `wifi`。AK 只做环境变量非空核验，不写入日志、Git、evidence 或文档。
