# Opaque provenance independent replication lifecycle 零 provider 门禁

- GitHub Issue：[Issue #245](https://github.com/WWFXL/Forge-AutoCompiler/issues/245)
- 状态：opt-in、零 provider、非正式实验
- 父候选：Issue #243 independent replication candidate
- Docker：仅允许 Ubuntu WSL2 原生 `docker.service`

## 目的

在任何 authorized amendment、reachability 或 12-pair batch 前，验证新 replication identity 能通过 Issue #241 的版本化 repair adapter 到达真实 Compile Session 生命周期。门禁只回答运行机制是否闭合，不估计模型效应，也不把 confirmatory v1 的三个 outcome 导入新 estimand。

## 冻结检查

- Candidate canonical SHA-256 固定为 `7b1817becba4ec57eb9726be0e1faaa5427af309dca7552634e3f6a3a1b5d938`。
- Evidence identity 固定为 `b136cc5669384176853f00b878dae207d89b7bce593cc8e5f1ff9ab06505b9bc`，schedule identity 固定为 `3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134`。
- Repair adapter byte SHA-256 固定为 `c8a13388f6c53d308b34f013bf4a9f449190a10e779667cdf73b0e8ef1da2544`。
- 新正式 evidence 目录在门禁前后都必须为空；门禁只写 pytest 临时目录。
- 6 case、12 pair、CMake/Make 分派、arm order 和 P2 criterion 不得变化。

## 最薄真实生命周期

1. CMake case 在 parent capture、coordinator commit 之前注入确定性异常，必须精确删除本 pair 新建的 Compile Session，且不得扫描或删除其他任务资源。
2. Make case 使用显式 deterministic fake model 执行一个完整 pair：parent checkpoint、baseline/treatment、treatment direct Make P2 conversion、production candidate verification、唯一 clean replay、finalize 与 cleanup。
3. 两条路径前后都要求 0 个 `deerflow-compile-*` / `deerflow-replay-*` managed orphan。
4. Fake model 的 endpoint 固定为 `https://example.invalid/v1`、credential env 固定为不存在的占位名；调用方不显式提供 fake model factory 时 fail closed。

## 授权与停止规则

本门禁固定 0 provider、0 credential read、0 formal attempt、0 model token 与 0 正式 evidence write。它不创建 authorized amendment，不执行 reachability，不运行正式 pair，不读取任何 AK，也不修改 production Compiler 或冻结的 v1/replication candidate。若门禁必须放宽 verifier、复用 v1 outcome 或写入正式 evidence 才能通过，则立即停止并重新评审。
