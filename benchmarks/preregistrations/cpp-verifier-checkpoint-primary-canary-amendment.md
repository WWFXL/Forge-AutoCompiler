# Failure checkpoint primary canary amendment 候选预注册

本阶段只形成新的 amendment 候选协议，不授权或执行 provider 请求。Issue #149 的 reachability 与 controlled pair 已终态关闭；Issue #151 / PR #152 只修复 Windows bind 的 CMake binary dir parity，不改变旧实验终态。

## 旧终态

- 父授权 manifest canonical SHA-256 为 `2771e72eee45ca6eac7bc1e7d5040cf5633bb3bf7e24a186a44071d9a98ce579`，release revision 为 `1ae32b501db4f4e1c35cec84b93e02267239b051`。
- 唯一 reachability 为 `passed`，actual model 为 `deepseek-v4-flash`，记录 1 request / 17 tokens。
- 唯一 controlled pair 为 `failed/CanaryError`，失败发生在 checkpoint capture、arm provisioning 和 pair provider request 之前；没有 arm ledger 或 pair report。
- 旧 marker、report 与 parent ledger 保持 append-only，不允许重试、replacement、backfill、删除或改写。

## Amendment 决策

- 旧 reachability 不复用。它绑定旧 manifest hash 与旧 release revision，不能满足新 amendment 的同身份前置门禁。
- 新候选提出独立的一次 reachability 和一个 controlled checkpoint pair，仍固定 DeepSeek `deepseek-v4-flash`、300 秒 timeout、0 retry、禁止 fallback/replacement/backfill。
- 新 CMake binary dir 固定为 `.forge-cmake-build`，只通过 `forge_checkpoint_windows_build_layout.py` 适配；父 runner、父 manifest 和父测试逐字不变。
- 新 evidence 目录为 `/workspace/.compile-sessions/benchmark-evidence-checkpoint-primary-canary-amendment`，marker 使用 `amendment-reachability-attempt.json` 与 `amendment-controlled-pair-attempt.json`，不得与旧目录或文件名重合。

## 候选预算

- Reachability：最多 1 request / 5,000 recorded tokens。
- Controlled pair：每臂最多 8 requests、8 turns、24 graph steps、600 秒 work、120 秒 cleanup、120,000 recorded tokens。
- Pair maximum 为 240,000 recorded tokens，阶段 maximum 为 245,000 recorded tokens。
- 这些数值只是拟议 ceiling；`provider_canary_authorized=false`、`mechanism_canary_authorized=false`、`pilot_collection_authorized=false`。

## 本阶段门禁

- 只允许生成和校验候选 manifest，以及只读核对旧 evidence identity。
- 不读取 AK，不创建 marker/ledger/report，不调用 provider，不启动 Docker，不创建 formal physical attempt。
- 旧 evidence、父 manifest、父 protocol artifacts、build-layout adapter 或候选授权位发生漂移时失败关闭。

## 后续停止点

候选合并后，实验负责人仍需单独确认 1 次新 reachability、1 个 controlled checkpoint pair 和最多 245,000 recorded tokens。随后必须形成新的 authorized amendment manifest 并在干净 `main == origin/main` 上通过零调用 preflight；canary 通过也不自动授权 6-pair pilot。
