# C/C++ formal 300 秒超时校准 canary 接线修订

## 修订原因

`formal-collection-4.5.0-timeout-calibration` 的唯一 canary 在任何模型调用前，被旧 runner 的匿名 endpoint preflight 拒绝。该终态只说明 canary 接线错误，不是 300 秒模型请求结果。

## 冻结修订

- 原失败 marker、0 provider report 和 0 JSONL ledger 保持不可变，并在新入口执行前逐项校验。
- 派生新的协议 identity、evidence 目录和唯一 canary 机会，不覆盖或删除旧 evidence。
- 新 canary 禁止匿名 `/models` endpoint preflight，以实际、经认证的双 provider 请求判断连通性。
- 新 canary 成功后仍只执行 `cppitertools` 的原 schedule order `1, 2`。
- RichLab `gpt-5.5`、DeepSeek `deepseek-v4-flash`、300 秒请求超时、0 retry、500,000 recorded-token ceiling、attempt budget、Ubuntu 原生 Docker、Compose/DooD、Compile Session 和 clean replay 均不变。

## 停止条件

- 新 canary 成功或失败都会消耗唯一机会。
- canary 失败时不得创建 ledger，并立即停止。
- 任一旧 evidence、目录、容器或运行门禁不匹配时，在新模型请求前停止。
- 两槽完成或 recorded-token boundary 到达后停止，不 retry、fallback、replacement、backfill 或 primary pooling。
