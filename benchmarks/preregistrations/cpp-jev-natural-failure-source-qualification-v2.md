# Jev 自然失败 source qualification v2 预注册

日期：2026-10-11。追踪：Issue #413。identity：
`cpp-jev-natural-failure-source-qualification-v2`。

## 父样本

唯一输入为 SHA-256
`5ac8824a17bbc72307c39df0f0605284a03897f0149bfc9ecca9b7aab13887f8` 的
`benchmarks/reports/cpp-jev-natural-failure-source-catalog-v2.json` 中 24 个冻结项目。catalog 决定必须为
`proceed_to_natural_failure_build_qualification_v2`，三个系统必须各 8 项，family 必须全局唯一。

## 唯一正式 attempt

- create-once evidence：`.compile-sessions/benchmark-evidence-jev-natural-failure-source-qualification-v2`；
- work root：`.compile-sessions/work-jev-natural-failure-source-qualification-v2`；
- 每项目 2 个独立 clean replicate，无重试；
- clone/fetch/checkout 和单命令 180 秒，单 replicate 300 秒，总 attempt 14400 秒；
- 镜像 ID、禁网、4 jobs、标准命令和分类顺序以 design/manifest 为准；
- 0 credential read、0 Provider request、0 model token。

## 分类与门槛

网络下载失败、平台不兼容、Docker/harness、timeout、source drift、initial success 和 replicate 不一致均
不计为自然失败。只有两个 `bounded_failure` 的失败阶段和规范化错误类别一致才记为
`stable_natural_failure`。

CMake、Make、Autotools 分别要求 design `>=1`、calibration `>=1`、evaluation `>=2`。全部通过时决定
`proceed_to_reference_recipe_qualification_v2`；任一门槛失败时决定
`stop_natural_failure_build_qualification_v2`。

## 冻结纪律

项目不合格时保留空位，不 replacement、不 backfill、不前移角色、不切换构建系统、不改变标准入口。
唯一 attempt 的成功、失败、超时、完整日志、marker 和报告永久只读。

本结果不验证 reference recipe、typed action、安全动作、RuleGate、Jev/Agent 效果、成本收益或动态预算。

