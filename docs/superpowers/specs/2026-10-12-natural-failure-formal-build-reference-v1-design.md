# 自然失败正式 build/reference 资格 v1 设计

日期：2026-10-12。追踪：Issue #419。父机制：Issue #417 的 Linux 构建闭合资格 v5。

## 1. 研究问题

受控故障实验已经证明 Jev 类型化语义路由在冻结项目族和严格裁判下可以提高成功率并降低 Provider 成本，但
尚未证明该机制能够处理自然发生的构建失败。自然失败 source qualification v1-v4 又表明，仅凭根入口、源码
关键词或 Linux 文档无法确认默认 target 是否面向宿主 Linux 用户态，也无法确认失败是否存在可复现的成功
reference closure。

本阶段只回答下面的数据资格问题：

> v4 冻结的 CMake、Make、Autotools 各 12 个 reserve 中，是否存在足够数量的项目，其默认构建路径在两个
> clean workspace 中形成一致的自然失败，并且同一默认 target 能由可审计 reference recipe 在另外两个 clean
> workspace 中闭合为宿主 Linux 用户态 ELF 或静态库？

该问题分成两个独立、create-once 的 formal identity。默认路径 identity 先判断候选和固定角色配额是否仍有
可能满足；只有它通过，才允许建立 reference closure identity。两个 identity 的 evidence、marker、报告和审计
互不写入。

## 2. 父证据与固定候选

默认路径 identity 为 `cpp-jev-natural-failure-default-path-qualification-v1`。唯一候选来源是
`benchmarks/reports/cpp-jev-natural-failure-linux-applicability-v4.json` 中已经冻结的
`qualification.projects`，文件 SHA-256 为
`d7b169290e47045bfde7d5ba6674917d15795d64780f963ea7f44ff40e6d7e6c`。

候选固定为 CMake、Make、Autotools 各 12 个 exact commit，共 36 个互不重复的 project family。正式运行不再
搜索项目、不更新 commit、不切换构建系统，也不依据 v5 canary 结果删除或替换项目。v4 source-only 分类仅作为
风险和来源元数据，不决定动态资格。

固定角色由 v4 `system_rank` 直接决定：

| system rank | 角色 |
| --- | --- |
| 1--3 | design |
| 4--6 | calibration |
| 7--12 | evaluation |

项目不合格时留下空位；角色不前移、不 replacement、不 backfill。这个映射在正式 observation 前冻结，避免根据
失败类别或 reference 难度选择更有利的 evaluation 项目。

## 3. 默认路径正式观察

每个项目执行两个独立 clean replicate。源码在宿主机按 exact commit 获取并核对 HEAD、tracked source clean 和
submodule 合同；每个 replicate 从只读源副本开始。构建环境固定为：

- image：`autocompiler:gcc13@sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`；
- Linux x86_64，4 CPU，`--network none`，`LC_ALL=C`；
- source 获取 180 秒，单命令 300 秒，单 replicate 600 秒；
- 总 attempt 墙钟上限 43200 秒；
- 0 credential read、0 Provider request、0 model token。

标准默认路径与 v5 一致：

- CMake：`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_VERBOSE_MAKEFILE=ON
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`，随后 `cmake --build build --verbose --parallel 4`；
- Make：`make --trace -j4 V=1 VERBOSE=1`；
- Autotools：依次选择仓库已有 `./autogen.sh`、`./bootstrap` 或 `autoreconf -fi`，再执行 `./configure` 和
  `make --trace -j4 V=1 VERBOSE=1`。

不能增加 dependency、配置参数或可选 target。每次 observation 保存命令退出、timeout、完整日志哈希、有界预览、
构建前后文件快照、Forge compiled-artifact 分类、ELF/archive machine、producer 绑定、动态 target signal 和
source identity。

## 4. 分类与项目级隔离

单次分类顺序沿用 v5：`infrastructure_failure`、`timeout`、`non_host_target`、
`host_userland_closure`、`no_compiled_artifact`、`network_dependency_failure`、`bounded_failure`。
构建系统自身的 compiler ID、ABI、scratch、tmp 和 `conftest` 产物不得作为项目产物。

只有两个 replicate 都是 `bounded_failure`，并且 failure phase、error category 和关键 target facts 一致，才形成
`stable_failure_candidate`。它仍然不是合格自然失败，因为 target 在失败点可能尚未暴露。

单项目 clone、命令、timeout、解析或 cleanup 错误必须保存 observation 后继续下一个项目。只有父报告哈希不匹配、
manifest/Schema 不合法、evidence create-once 冲突、Docker runtime 不可用、镜像 identity 不匹配或 managed
resource 前置条件失败，才允许整个 attempt fail closed。

## 5. 默认路径阶段门槛

默认路径 identity 只有同时满足以下条件才决定
`proceed_to_formal_reference_closure_qualification_v1`：

1. 36/36 个项目均形成项目级终态，两个 replicate 的 observation 均被保存；
2. 每个构建系统的 design 角色至少 1 个、calibration 至少 1 个、evaluation 至少 2 个
   `stable_failure_candidate`；
3. 已知非宿主反例没有成为 `stable_failure_candidate` 或宿主闭合；
4. source-only 误伤项目没有仅因旧静态标签被排除；
5. 0 Provider、0 credential、0 model token，cleanup 后 0 managed resource；
6. formal audit 验证 marker、manifest、报告、evidence inventory 和日志哈希一致。

任一门槛失败即决定 `stop_natural_failure_build_reference_qualification_v1`。剩余未执行的 reference、动作矩阵和
Provider 实验全部停止；不得用新项目、变更角色、加长单项目预算或改入口来挽救该 identity。

## 6. Reference closure identity

只有默认路径阶段通过后，才创建独立
`cpp-jev-natural-failure-reference-closure-qualification-v1`。reference recipe 的编写允许读取本阶段冻结的失败
日志和项目文档，但必须按每个系统、每个角色中的 `system_rank` 升序审核所有 stable candidate，不能只选择容易
闭合的项目。recipe、文档依据、包版本、预期产物、functional oracle 和 source hash 必须在第一次 reference
运行前提交并冻结。

每份 recipe 必须：

- 最终执行同一个默认 target 命令，不以可选 Linux target 替代默认 endpoint；
- dependency、configure、build 步骤均可追溯到项目文档、构建文件或正式失败日志；
- 不修改 tracked source、不下载预构建目标产物、不跳过编译、不放宽 verifier；
- 在运行时无网络的两个 clean workspace 中生成宿主 Linux ELF/`ar`；
- 通过 machine、producer、source identity、functional oracle、provenance 和 clean replay；
- 两个 replicate 的产物相对路径、类型、machine 和 oracle 终态一致。

Reference 阶段最终仍要求每个系统 design `>=1`、calibration `>=1`、evaluation `>=2` 个
`qualified_natural_failure`。通过才允许设计 typed-action outcome matrix；失败则停止自然失败 Provider 路线。

## 7. 结论边界

默认路径通过只说明存在足够的稳定失败候选，不证明 reference 可闭合。reference 通过只说明能够构造合格的自然
失败 benchmark，不证明 Jev 或 Agent 有效。两个阶段都不能用于声称成本收益、动态预算控制、模型排名、开放世界
泛化或 treatment effect。

无论结果正负，v1-v5 的 manifest、marker、report 和 raw evidence 永久只读。本阶段不会修改任何历史
experiment identity。

