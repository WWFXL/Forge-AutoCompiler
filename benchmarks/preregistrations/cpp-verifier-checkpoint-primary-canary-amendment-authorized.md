# Failure checkpoint primary canary amendment 授权预注册

本协议承接 Issue #153 / PR #154 的不可执行候选。实验负责人在 Issue #155 明确授权 1 次新 reachability、1 个 controlled checkpoint pair，以及合计最多 245,000 recorded tokens。

## 授权 identity

- 授权 baseline 为 `main@9feb832da1f4b124694260de1b487ea645ae55af`；真实执行 revision 必须位于其后代、分支为 `main`、与 `origin/main` 一致且工作树干净。
- 父 candidate canonical SHA-256 为 `d0598b549301a2efbe431e2bfa7f6f21c4ba32e2c3eae1b078935630f1ffb704`。
- provider 固定为 DeepSeek `deepseek-v4-flash`，endpoint 为 `https://api.deepseek.com`，凭据环境变量为 `DEEPSEEK_API_KEY`，请求策略为 300 秒 timeout、0 retry、禁止 fallback。
- 运行拓扑固定为 WSL2 Ubuntu 原生 Docker 上的 Compose/DooD；不使用 Docker Desktop。

## 唯一授权范围

- Reachability：最多 1 request / 5,000 recorded tokens，使用独立 marker `amendment-reachability-attempt.json`。
- Controlled pair：只允许 1 pair，严格按 `baseline`、`treatment` 顺序各一次；每臂最多 8 requests、8 turns、24 graph steps、600 秒 work、120 秒 cleanup 和 120,000 recorded tokens。
- Pair maximum 为 240,000 recorded tokens，reachability 与 pair 的阶段总上限为 245,000 recorded tokens。
- `pilot_collection_authorized=false`、`natural_collection_authorized=false`、`secondary_provider_authorized=false`。

## 前置门禁

- Issue #149 的四份终态 evidence 必须保持文件集合、SHA-256 和语义不变；旧 reachability 不复用。
- 新 evidence 只写入 `/workspace/.compile-sessions/benchmark-evidence-checkpoint-primary-canary-amendment`。
- Controlled pair 必须读取同一 authorized manifest、同一 release revision 下已通过的 reachability marker 与 report。
- Windows bind 构建布局固定为 `.forge-cmake-build`；旧 runner 仅通过版本化 adapter 私有加载，不修改冻结文件。

## 停止条件

- Reachability 超时、模型 identity/token 门禁失败或 evidence/identity 漂移时立即停止，唯一机会不得重试。
- Controlled pair 任一臂失败、pair 不完整或 cleanup 未闭合时立即停止，禁止 replacement、backfill 和 fallback。
- Pair 通过只说明可以申请后续 6-pair pilot，不构成 pilot 自动授权，也不计入 pilot denominator。

## 发布前边界

authorized manifest 合并前只允许生成、校验和零 provider 测试；不得读取 AK、创建 marker/ledger/report、启动 Docker 或执行 physical attempt。真实 reachability 和 controlled pair 必须等待授权实现合入干净主干后再单独启动。
