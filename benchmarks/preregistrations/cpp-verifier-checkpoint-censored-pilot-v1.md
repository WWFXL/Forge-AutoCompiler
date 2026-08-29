# Endpoint 删失容忍 checkpoint 六配对 pilot 预注册

本协议承接 Issue #157 的只读 timeout 审计和 Issue #159 的路线 B 授权。研究变量仍是 failure checkpoint 是否向 compiler continuation 提供结构化 verifier repair packet；本次只改变批次停止策略，不改变 provider、prompt、controlled fault、Oracle、candidate verification 或 clean replay。

## 实验身份与预算

- 语言范围固定为 C/C++，controlled fault 固定为 `artifact_staging_missing`。
- provider 固定为 DeepSeek `deepseek-v4-flash` 与 `https://api.deepseek.com`；单请求 300 秒 timeout、0 retry、禁止 fallback，保持非 streaming。
- 预注册 6 pair、12 arms；每臂最多 120,000 recorded tokens，总机械上限为 1,440,000 recorded tokens。
- pair 1/3/5 按 `baseline -> treatment`，pair 2/4/6 按 `treatment -> baseline`，形成 3:3 交叉平衡。
- 不允许 replacement、backfill、补跑或第 7 个 pair。timeout、streaming 和输出上限不能在本批次中另行改变。

## 独立 evidence 与断点

- 新 evidence 只写入 `/workspace/.compile-sessions/benchmark-evidence-checkpoint-censored-pilot-v1`。
- 每个 pair 使用 `pairs/pair-NN` 独立目录、独立 checkpoint SQLite、ledger、report 和一次性 marker。
- 已形成 `complete` 或 `endpoint_censored` outcome 的 pair 在批次恢复时只读跳过，不能重复执行。
- 已出现内容但没有合法终态的 pair 视为中断，不自动重试；必须人工审计 cleanup 和 evidence 后另行决策。
- Issue #155 的 7 个核心 evidence 与 2 个后验 SQLite sidecar 均固定文件集合和 SHA-256。sidecar 保留，不删除、不覆盖；SQLite 审计只使用 `immutable=1`。

## Endpoint 删失定义

只有同时满足以下条件的失败 pair 才标记为 `endpoint_censored` 并继续后续预注册 pair：

1. 唯一请求失败事件为 `model.request_failed`；
2. `classification=timeout`、`retry_exhausted=true`、`status_code=null`；
3. 存在唯一匹配的 primary `failure.recorded`，其 `domain=model_endpoint`、`classification=timeout` 且 secondary 包含 `retry_exhausted`；
4. ledger 哈希链完整，每臂 recorded tokens 未超过上限；
5. coordinator 以 `immutable=1` 读取后为 `cleaned`，并记录 `cleanup.succeeded=true`；
6. Docker daemon 中没有 `deerflow-compile-*` 或 `deerflow-replay-*` orphan。

identity/evidence 漂移、cleanup 不闭合、预算超限、非 endpoint 请求失败、模型行为失败或其他异常仍立即关闭批次。删失不能解释为模型能力、checkpoint treatment、Oracle 或 clean replay 的失败。

## 两个 estimand

- ITT/attrition：分母固定为全部 6 个预注册 pair，报告 complete 与 endpoint-censored 数量、删失 pair/arm、请求数和 recorded tokens。
- Conditional mechanism：只纳入双臂均形成完整可验证终态的 pair，描述 repair conversion、请求数、submit/replay 次数、token 和 wall-clock 差异。

本 pilot 仅做描述性机制评估，不计算 p 值，不做模型排名或跨 provider 推断。单个 pair 或少量 complete pair 不支持确定性效应结论。

## 发布与执行门禁

实现合并前只允许 manifest/Schema 生成、零 provider 单测、Ruff 和冻结 evidence 只读核验。真实执行必须位于干净 `main == origin/main`，使用 WSL2 Ubuntu 原生 Docker 的既有 Compose/DooD control plane，网络介质记录为 `wifi`，并在每个 pair 前后核验 0 受管 orphan。
