# Jev 自然构建失败 source qualification v1 预注册

日期：2026-10-11。追踪：Issue #411。设计提交：`e94c94c871881adfb6f621e0edf1550d2e800f0e`。

## 目的

在调用 Jev 或 Agent Provider 前，判断冻结的 22 个未见项目是否能形成跨 CMake、Make、
Autotools、角色隔离且可重复的自然失败来源。该 identity 只运行源码门禁和标准初始路径双 replay，
不验证 reference recipe、候选动作 outcome、Jev 能力或系统 treatment effect。

## 冻结输入

- source pool：`benchmarks/fixtures/cpp-jev-natural-failure-source-pool-v1.json`，22 个 exact commit；
- 镜像：`autocompiler:gcc13@sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`；
- build network：`none`；并发度：4；
- 每项目 2 个独立 session；单命令 300 秒，单 session 600 秒，整个 batch 28800 秒；
- 0 retry、0 credential read、0 Provider、0 model token；
- create-once evidence：`.compile-sessions/benchmark-evidence-jev-natural-failure-source-qualification-v1`。

## 观察与分类

每个项目记录 clone、exact checkout、submodule、源码入口、命令、退出码、墙钟和完整 stdout/stderr。
只有两个 session 都是非基础设施、非超时的非零退出，并且失败阶段与预先定义的错误类别一致，才标为
`stable_natural_failure`。初始成功、入口不匹配、clone/submodule/Docker 错误、超时和不一致失败均
保留，但不计入合格样本。

## 通过条件

CMake、Make、Autotools 每个系统都必须同时具有：

- design 至少 1 个稳定自然失败；
- calibration 至少 1 个稳定自然失败；
- evaluation 至少 2 个稳定自然失败。

通过时决定为 `proceed_to_reference_recipe_qualification`。任一配额失败时决定为
`stop_natural_failure_evaluation`，不得 replacement、backfill、前移角色、改换构建系统或调整
标准初始路径。

## 停止规则

- manifest、source pool、父证据、设计提交、镜像或 branch 合同漂移；
- evidence/report/work 路径在 attempt 前已存在；
- 全局 Docker/runtime、磁盘或 cleanup 异常，或发现未清理的受管容器；
- batch 总墙钟超过 28800 秒；
- 运行器未能原子保存当前失败记录。

项目自身 clone/submodule/timeout 作为该项目的排除 observation，通常不停止其他项目；全局基础设施
故障则立即停止 batch。失败 attempt 保留，不续跑、不 replacement、不 backfill。

## 解释边界

通过只证明冻结样本中存在数量足够、类别稳定的自然失败，允许继续人工审核 reference recipe 和动作
矩阵；不等于完整 benchmark 已合格，更不支持 Jev/Agent 成功率、成本或动态预算结论。失败只约束
当前抽样框、镜像、标准路径和资源上限。
