# 多 checkpoint behavioral pilot v3 授权采集预注册

本协议承接 Issue #170 / PR #171 的未授权冻结设计。实验负责人在 Issue #172 前确认当前网络介质为 `wifi`、Ubuntu 原生 `docker.service` 已启动，并授权 DeepSeek `deepseek-v4-flash` 的一次 canary 与后续 6 个冻结 pair，总 recorded-token 机械上限保持 1,440,000。

## 不变的研究设计

- Case 固定为 CMake `cppitertools`、Make `janet`、Autotools `libcheck`，继续引用 #168 的零 provider case identity。
- 每个 case 固定两个 pair：一个 baseline-first，一个 treatment-first；共 6 pair / 12 arm。
- Provider 固定为 `https://api.deepseek.com` / `deepseek-v4-flash`，300 秒 timeout、0 retry、禁止 fallback。
- 每臂 120,000、每对 240,000、阶段总计 1,440,000 recorded tokens。
- 三层终态、endpoint censoring、模型行为 outcome、candidate verifier、clean replay 和 cleanup 语义保持 behavioral v2 不变。

## 授权顺序

1. 在合并后的干净 `main == origin/main`、Compose/DooD 与 Ubuntu 原生 daemon 上运行零请求 preflight。
2. 唯一 provider canary 只允许 1 个请求，必须精确返回 `CANARY_OK`，actual model、endpoint、300 秒 timeout、0 retry 和 token usage 全部闭合。
3. Canary marker 无论成功或失败都消耗机会；失败后不得重试或创建 replacement identity。
4. Canary 通过后按 manifest 顺序执行 6 pair。每个 pair 后检查累计预算、三层终态、ledger 哈希链和 0 managed orphan。
5. Identity、evidence、预算、cleanup 或未分类基础设施失败立即关闭 batch；合法 endpoint timeout 与已分类模型行为失败按预注册 outcome 保留并继续另一臂。

## Evidence 与分析

Evidence 只写入 `/workspace/.compile-sessions/benchmark-evidence-multi-checkpoint-behavioral-pilot-v3-authorized`。禁止覆盖已有 marker、ledger、pair outcome、report 或 sidecar。

结果逐 case 报 paired four-cell、请求、recorded tokens、failure transitions 和执行顺序；跨 case 使用三个 case 各 `1/3` 权重的 macro-average。禁止 p 值、provider 池化、模型排名、历史 pair 池化、replacement、backfill 和 schedule extension。

AK 只允许通过 `DEEPSEEK_API_KEY` 非空门禁进入模型 SDK；不得输出、哈希、写入 Git、日志、marker、report 或 evidence。
