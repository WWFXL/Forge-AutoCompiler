# Opaque provenance confirmatory independent replication candidate

## 状态

本文是 Issue #243 的未授权候选，不是执行授权。阶段内不得调用 provider、读取 credential、启动 Docker、创建 checkpoint、写正式 evidence 或消耗 model token。任何真实 reachability 或 pair collection 都需要新的 authorized amendment。

## 与 confirmatory v1 的关系

Confirmatory v1 保持为 `failed_mechanism_attempt_closed`。其 28-file inventory digest 为 `dc7e53020af27929ea334376628c37f02236ae5510166c07109a1ddde7f5f431`。`pupnp-rep-01`、`ada-url-rep-01` 和 `args-rep-01` 三个 outcome 不导入本候选的 primary test；`gpac-rep-01` 即使未消费 provider opportunity，也不续跑。

本候选明确冻结：

- `historical_outcomes_imported=false`
- `v1_attempt_extended=false`
- `replacement=false`
- `backfill=false`
- `gpac_v1_attempt_resumed=false`

## 新 estimand

实验单位仍为 project block。六个 C/C++ project 各有两个 replicate；每个 replicate 从同一 checkpoint 派生 baseline/treatment，两次 arm order 在项目内对调。Project score 是两个有效 paired provenance conversion delta 的均值；只有六个 project block 全部 estimable 时才执行 two-sided exact sign-flip test。

该 estimand 只描述修复后统一 runtime 与新采集时段下 verifier-driven repair 对 opaque build provenance conversion 的配对效应。V1 outcome 和历史 exploratory pair 均不池化，也不做模型排名。

## 冻结 identity

- 候选基线：`main@c38f73816be706f7e8ef7115422bb9878d675493`
- Parent v1 manifest canonical SHA-256：`68349316cfdbe8411c49c7ffc9491760bf19fb10e0583f40a47dd0c91ea31e78`
- Repair adapter byte SHA-256：`c8a13388f6c53d308b34f013bf4a9f449190a10e779667cdf73b0e8ef1da2544`
- 新 evidence directory：`/workspace/.compile-sessions/benchmark-evidence-opaque-provenance-confirmatory-replication-v1`
- Schedule：继承六 case、12 pairs 与原 arm order，不删减、不插入、不重排

## 仅供后续授权评审的运行候选

- Provider/model：DeepSeek `deepseek-v4-flash`
- Endpoint：`https://api.deepseek.com`
- Credential env name：`DEEPSEEK_API_KEY`
- Request timeout：300 秒
- Retry：0
- Fallback：禁止
- Batch maximum recorded tokens：2,940,000

这些字段只表达候选配置。当前 authorization 全部为 false，`model_tokens_authorized=0`。

## Evidence 与安全边界

新 evidence identity 绑定 Issue、基线 commit、parent manifest、v1 inventory、schedule、repair adapter 与新目录。Reachability、batch 和 pair marker/report 使用独立 create-once 路径，不读取或写入 v1 evidence。

真实执行前必须依次通过：合并主干 release、manifest identity、空 replication evidence、Ubuntu 原生 Docker、0 managed orphan、credential-name-only、repair adapter CMake/Make 合同和 capture-before-commit cleanup。失败不得回退 Docker Desktop，不得 replacement/backfill。

## 下一阶段

候选 manifest/Schema 合并后，先在 Ubuntu daemon 恢复的前提下运行零 provider lifecycle 门禁。只有门禁成功并形成新的显式授权后，才派生 authorized runner、执行唯一 reachability，再按完整 12-pair schedule 采集。
