# Jev 自然失败 source catalog v2 设计

日期：2026-10-11。追踪：Issue #413。父失败证据：Issue #411 的
`cpp-jev-natural-failure-source-qualification-v1`。

## 1. 阶段问题

v1 在观察构建结果前冻结了 CXXCrafter 的构建系统能力标签，但该标签不保证 exact commit 的仓库根
存在 Forge 标准入口。唯一 attempt 中还把禁网触发的 `FetchContent` 下载失败误标为稳定自然失败，并让
单个 recursive submodule 超时中止全批次。

v2 先回答一个更窄的问题：

> 能否在不运行 configure/build 的前提下，从未进入 Forge 历史实验的活跃 C/C++ 仓库中冻结足够的
> exact-commit、根入口合格、无 submodule 且根构建入口没有显式下载动作的 CMake、Make、Autotools
> 候选，并证明每个仓库的采集故障不会中断批次？

本阶段是 source-only 数据资格和采集基础设施门禁，不产生 Jev、Agent、动作路由或动态预算效果证据。

## 2. 两个独立 identity

1. `cpp-jev-natural-failure-source-catalog-v2`：冻结公开搜索快照，解析 exact commit，检查源码合同，
   分配每个构建系统 8 个互不重复的项目族。该 identity 不运行构建。
2. `cpp-jev-natural-failure-source-qualification-v2`：只在 catalog 通过后另行冻结。它对 catalog 选出的
   24 个项目执行双 clean build，并把网络、Docker、超时和 harness 失败与自然 configure/build 失败
   分开。

两个 identity 使用不同 manifest、marker、报告和 evidence 根。catalog 失败时不得创建 build identity。

## 3. 结果盲候选快照

catalog 在唯一正式 attempt 开始后，通过 GitHub repository search 分别取得主语言为 C 与 C++ 的仓库：

- stars 为 100--20000；
- size 小于 100000 KiB；
- 非 archived、非 fork、公开；
- `updated >= 2024-01-01`；
- 按 stars 降序，每个语言最多 60 项。

两份原始搜索响应写入 evidence。候选去重后，以冻结的历史 revision
`da8de64e4c8073858178d83dd2ed671878103197` 中 `benchmarks/fixtures/*.json` 与
`benchmarks/manifests/*.json` 的 GitHub project family 集合作排除快照。排除集合只由历史版本化数据生成，
不读取历史 outcome。

## 4. Source-only 检查

每个未排除候选只执行 GitHub API 读取，不 clone、不 checkout、不运行仓库脚本：

1. 解析默认分支当前 exact commit，并记录 commit 时间；
2. 读取该 commit 的根 tree；
3. 根 `CMakeLists.txt` 表示 CMake 候选，根 `Makefile`、`makefile` 或 `GNUmakefile` 表示 Make 候选，
   根 `configure.ac` 或 `configure.in` 表示 Autotools 候选；
4. 根存在 `.gitmodules` 时排除。v2 不估计或下载 recursive submodule，以确定性排除消除该成本和超时；
5. 读取候选系统对应的根入口 blob，扫描 `FetchContent`、`ExternalProject_Add`、`file(DOWNLOAD)`、
   `git clone`、`curl` 和 `wget` 等显式网络获取原语；命中时该系统边不合格；
6. 单仓库 API 超时、404、解析错误或异常形成项目级 `infrastructure_failure`，保存结果后继续下一个候选。

根入口扫描不是完整离线依赖闭包证明。被 include 的嵌套构建文件仍可能下载依赖；build qualification
必须根据完整日志把这类运行时网络失败排除，不能将其归入自然失败。

## 5. 确定性系统分配

对 source-eligible 的 `(project family, system)` 边计算
`sha256(seed + NUL + family + NUL + system)`。分配器反复选择“剩余可用项目最少”的系统，再取该系统
最小哈希且尚未使用的项目，直到每个系统 8 项或无法继续。项目族全局唯一。

系统内按 `sha256(seed + NUL + family)` 排序；序号 1--2 为 design，3--4 为 calibration，5--8 为
evaluation。角色只在 catalog 完成后由 source facts 冻结，不能依据后续构建结果前移、替换或回填。

## 6. Runner 故障隔离门禁

正式执行前，测试必须注入 repository search、commit、tree 和 blob 四类超时/错误，并证明：

- 单仓库错误产生有界 observation；
- 后续仓库仍被处理；
- marker 的完成计数与已写结果一致；
- 全局搜索快照失败才允许关闭整个 attempt；
- 不会创建 Docker 容器、读取 Provider credential 或调用模型。

## 7. Catalog 通过与停止规则

catalog 通过必须同时满足：

- CMake、Make、Autotools 各分配 8 个互不重复的 source-eligible 项目族；
- 24 个项目均有 exact commit、根入口、无 `.gitmodules`，对应根入口无冻结网络获取信号；
- 所有 API/解析故障均按项目终结，attempt 完整封口；
- 0 build command、0 Docker、0 Provider credential read、0 Provider request、0 model token。

任一系统少于 8 项即决定 `stop_natural_failure_source_catalog_v2`。不得修改查询、放宽 source 合同、
复用被排除项目、replacement 或 backfill 来挽救同一 identity。

通过时只允许建立新的 build qualification 预注册；catalog 本身不证明存在自然失败，也不授权 Jev。

## 8. 后续 build qualification 边界

build identity 必须在看到任何构建结果前冻结镜像、标准入口、双 clean replay、超时、网络错误分类、角色、
停止规则和 evidence 根。每个项目级 clone、命令和 cleanup 故障均保存后继续。

若稳定自然失败不能覆盖每个系统的 design `>=1`、calibration `>=1`、evaluation `>=2`，则停止。
通过后才允许审核 reference recipe 和三动作 outcome matrix；固定 `build` RuleGate 安全率高于 75% 或
安全动作只有一种时，同样停止 Provider 阶段。

