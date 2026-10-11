# Jev 自然构建失败 source qualification v1 失败审计

日期：2026-10-11。追踪：Issue #411。该文档只读审计已冻结的失败 attempt，不修改或补写 raw evidence。

## 结论

决定为 `stop_natural_failure_evaluation_v1`。当前 v1 source pool 和 runner 不能形成预注册的自然失败
benchmark，因此不进入 reference recipe、typed action matrix 或 Provider 三臂实验。

这个停止结论不依赖尚未运行的 Make/Autotools 项目。CMake calibration 的两个固定候选
`cmake-openalpr` 和 `cmake-treefrog-framework` 都缺少根目录 `CMakeLists.txt`，合格数为 0，而
预注册门槛为至少 1。角色不能前移、项目不能替换，所以剩余任务不能改变该门槛结果。

## Attempt 事实

- 执行 revision：`ba6c2f26a56f7be51caa34f5f512b380508c848a`；
- manifest canonical SHA-256：`64aeb10b8960b78ce82bb802f45d4bd7a437b5eaec1e17fdce6cd7b7e08a8deb`；
- 计划 22 项，完成 7 项；第 8 项 `cmake-rpcs3` 在 recursive submodule update 达到 300 秒；
- runner 没有把 `TimeoutExpired` 转成项目级排除，而是提升为全局失败；attempt 因此以
  `attempt_failed` 封口，不续跑、不 replacement、不 backfill；
- evidence 为 42 files / 49,680 bytes，inventory canonical SHA-256
  `fcb426ed7c7241148a9be224837a27b48935e300388d7c89a6fb6555afcd9c8b`；
- 0 credential read、0 Jev request、0 Agent Provider request、0 model token、0 reference recipe、
  0 action matrix；cleanup 后 0 受管容器，work root 已删除。

生成报告和 marker 保持原样。JSON/Markdown 生成报告 SHA-256 分别为
`72e8a57858365bafcd05e0cad764c52fff01cb4774240430deba2b07f586c60e` 和
`557499529eb762ef99113b85161df893a1dfb3be47d76570cc9e0fe731cca834`；marker SHA-256 为
`b485883ca1ecc2c5c56896b7ebbb8cd83b900eb37d79d03d1d568ca17da4e23e`。

## 标签复核

runner 在 7 个完成项中报告 5 个 `source_contract_ineligible` 和 2 个
`stable_natural_failure`。按预注册原文复核后，后两项也不能进入自然失败 benchmark：

| 项目 | runner 标签 | 原始日志事实 | 协议判定 |
| --- | --- | --- | --- |
| `cmake-flameshot` | configure / unknown | `FetchContent` 尝试从 GitLab clone Qt-Color-Widgets，禁网后失败 | network-dependent，排除 |
| `cmake-kvrocks` | configure / compile_error | `FetchContent` 尝试从 GitHub 下载 jemalloc，禁网后失败 | network-dependent，排除 |

两个项目各自两次 stderr 哈希完全一致，但“可重复”不能覆盖自然失败定义中的网络排除项。经协议复核，
已完成 7 项中的合格稳定自然失败为 `0/7`。未执行的 Make/Autotools 项目是未观察，不记为失败或零值。

## 说明了什么

本轮首先否定的是数据构造方案，而不是 Jev：

1. CXXCrafter 的构建系统能力元数据表示仓库中出现过某类构建设施，不保证 exact commit 根目录能按
   Forge 冻结的标准入口启动；
2. 在禁网环境中，现代 CMake 的 `FetchContent` 失败必须先从自然构建失败中剔除，否则会把环境政策
   误标成语义路由样本；
3. source/submodule 超时必须在正式运行前证明能按项目级 observation 封口，不能让单项目中止全批次。

本轮不能回答 Jev 是否能处理自然失败，也不能评价 Make/Autotools、reference recipe、动作多样性、
严格成功率、成本下降或动态预算控制。

## 后续决策

v1 永久停止。若研究负责人决定继续自然失败路线，需要新的设计而不是 replacement：先在结果盲的
source-only catalog 阶段验证根入口、递归 submodule 成本和离线依赖闭包，再进行角色分层；显式区分
“需要预取 vendored dependency”与“真实 configure/build failure”，并用故障注入测试证明每个项目级
超时都能保留后继续。新设计必须使用新 Issue、source pool、identity 和未观察项目，不能导入本次
部分 outcome 作为正式 treatment 数据。
