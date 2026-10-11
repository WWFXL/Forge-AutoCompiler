# Jev 自然失败 source catalog v2 预注册

日期：2026-10-11。追踪：Issue #413。identity：
`cpp-jev-natural-failure-source-catalog-v2`。

## 问题与输入

本 identity 只判断未见项目的 source-only catalog 能否为 CMake、Make、Autotools 各冻结 8 个合格项目。
候选由 manifest 中两条 GitHub repository search 在正式 attempt 内生成；历史排除集合固定来自
`da8de64e4c8073858178d83dd2ed671878103197`。

## 观察与分类

- 每个仓库记录搜索元数据、默认分支 exact commit、commit 时间、根 tree 和入口 blob 哈希；
- 根入口、`.gitmodules` 和显式网络获取信号是 source facts，不运行 configure/build；
- 单仓库 API 或解析故障记为项目级 `infrastructure_failure` 并继续；
- 搜索快照本身失败、identity/父证据漂移或 evidence 目录已存在时 fail closed。

## 唯一正式 attempt

- create-once evidence：`.compile-sessions/benchmark-evidence-jev-natural-failure-source-catalog-v2`；
- 最多 2 个 search 请求、120 个搜索结果和每仓库 4 个有界 API 步骤；
- 单请求 60 秒，总 wall clock 3600 秒；
- 0 build command、0 Docker、0 credential read、0 Provider request、0 model token；
- execution authorization 前 formal attempt 数为 0，授权后为 1。

## 通过门槛

对每个 source-eligible `(family, system)` 边按冻结哈希和稀缺系统优先算法分配，项目族全局唯一。
CMake、Make、Autotools 各 8 项时决定为 `proceed_to_natural_failure_build_qualification_v2`；任一系统
不足时决定为 `stop_natural_failure_source_catalog_v2`。

通过只授权建立新的 build qualification 协议。它不证明存在自然失败，不形成 Jev/Agent 效果、成本、
模型排名、自然失败总体或动态预算结论。

## 冻结纪律

唯一 attempt 无论通过、失败或部分完成均永久只读。不得修改搜索条件、重排候选、放宽根入口、允许
submodule、忽略网络信号、replacement、backfill 或在同一 identity 下重跑。

