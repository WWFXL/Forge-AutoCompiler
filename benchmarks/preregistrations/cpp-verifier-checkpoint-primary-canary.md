# Failure checkpoint primary mechanism canary 预注册

本阶段只验证 DeepSeek `deepseek-v4-flash` 能否从同一个 controlled fault v1 checkpoint 完成 baseline/treatment continuation。它不是 6-pair pilot，不进入 pilot 分母，不采集 natural failure，也不用于模型排名。

## 授权边界

- provider endpoint 固定为 `https://api.deepseek.com`，凭据只从 `DEEPSEEK_API_KEY` 读取。
- 最多一次 reachability request；只有它通过，才运行一个 controlled checkpoint pair。
- 每臂最多 8 requests、8 model turns、24 graph steps、600 秒工作时间和 120 秒 cleanup reserve。
- 每臂最多记录 120,000 tokens；reachability 最多 5,000 tokens；阶段总上限 245,000 tokens。
- request timeout 为 300 秒，provider 与 runner retry 均为 0；禁止 fallback、replacement 和 backfill。
- 任何 timeout、actual-model 缺失、pair 不完整、checkpoint/identity 漂移、预算越界或 cleanup 失败都终止 canary。

## 配对机制

controlled fault v1 只删除真实构建后已经暂存的唯一 required artifact，由真实 verifier 形成 pre-replay `candidate_verification_failed`。baseline 和 treatment 从同一个 committed message/environment/budget checkpoint 派生；唯一允许的输入差异是 treatment ToolMessage 中附加 schema-valid structured repair packet。

两臂固定按 baseline、treatment 顺序运行。该顺序只服务一次性接线门禁，不作为效应估计。两个 arm 使用独立 Compile Session、container、ledger 和内存 checkpointer；父 checkpoint 与另一臂均保持只读。

## 通过标准

reachability 必须返回精确 `CANARY_OK`、记录实际模型名和 token usage。两臂均必须在各自预算内完成真实 candidate verification 与 clean replay，actual model 必须为 `deepseek-v4-flash`，最终 cleanup 必须无 checkpoint 资源残留。报告只保存脱敏 identity、计数、hash、终态和时间，不保存 prompt、模型正文、AK 或请求体。

canary 通过只允许形成机制接线证据。后续 6-pair controlled pilot、RichLab secondary replication 和 natural stratum 必须分别重新授权。
