# Jev 自然失败 Linux applicability v3 设计

日期：2026-10-12。追踪：Issue #415。父结论：Issue #413 的
`stop_natural_failure_evaluation_v2_before_reference_recipe`。

## 1. 问题

v2 只检查根构建入口、submodule 和显式网络获取。`SketchyBar` 因而进入 Make calibration，随后在
Linux 上两次稳定失败；但其唯一根构建路径固定 Apple target、macOS frameworks 和 Mach-O/`lipo`，
无法闭合到 Forge 冻结的 ELF/`ar` 终点。

v3 先回答更窄的问题：

> 在不执行仓库脚本的前提下，能否从根构建入口和有界项目文档中识别明确不适用于 Forge Linux
> 用户态 C/C++ 终点的构建系统边，同时保留具有真实 Linux 路径的多平台项目？

这是基础设施资格门禁。它不证明候选会自然失败、失败可修复或 Jev 有效。

## 2. 新 identity 与冻结边界

新 identity 为 `cpp-jev-natural-failure-linux-applicability-v3`。它使用新的 manifest、Schema、marker、
报告和 create-once evidence 根，不导入 v1/v2 outcome 作为新结果。

Issue #411/#413 的 runner、manifest、报告、marker 和 raw evidence 永久只读。v3 只把 v2 的
`SketchyBar` 构造效度事实用作预先公开的回归反例。

## 3. 输入与观察

v3 从新的 GitHub repository search 快照建立候选池，并排除冻结历史 revision 中出现过的项目族以及
v2 catalog 已观察的 109 个候选。对每个未见候选只读取：

1. 默认分支 exact commit 和 commit 时间；
2. 根 tree；
3. CMake、Make、Autotools 的根入口 blob；
4. 最多 6 个根级 `README*`、`BUILD*`、`INSTALL*` 文档 blob。

单 blob 最大 1 MiB。catalog 不 clone、不 checkout、不运行 configure/build、不启动 Docker。

## 4. 信号与判定

信号分成三个来源，不能混为一个关键词黑名单：

- **构建入口排他信号**：固定 Apple target triple、`xcrun`/`xcodebuild`/`lipo`、Apple framework
  链接；MSBuild/WDK/MSVC-only；`arm-none-eabi`、`avr-*`、`riscv*-unknown-elf`、`xtensa*-elf`
  等裸机或固定交叉工具链；Mach-O bundle、PE-only、固件或内核镜像作为默认终点。
- **Linux/native 正信号**：入口中的显式 Linux 分支、`uname` Linux 分支、GNU/POSIX host compiler
  路径，或项目文档明确给出的 Linux build 路径。
- **文档排他声明**：`macOS only`、`Windows only`、仅面向固件/内核等明确声明。文档中的可选平台
  词汇不能单独排除项目。

每条 `(project, build system)` 边得到以下之一：

- `linux_applicable`：没有排他信号，或排他平台配置同时存在明确 Linux/native 路径；
- `platform_ineligible`：构建入口有排他信号且没有 Linux/native 路径，或文档明确声明平台唯一性；
- `ambiguous`：入口/文档不可读、信号冲突且无法证明 Linux 路径，或终点类型无法静态判定。

只有 `linux_applicable` 边可进入后续候选池。`ambiguous` fail closed，不在同一 identity 中人工改标签。

## 5. 误伤控制

门禁必须通过以下冻结回归：

- `SketchyBar` 式固定 Apple target + frameworks + `lipo` 为 `platform_ineligible`；
- MSVC/WDK-only 和裸机交叉编译入口为 `platform_ineligible`；
- 同一 Makefile 中分别存在 Darwin 与 Linux 分支的项目为 `linux_applicable`；
- CMake 中受 `if(APPLE)` 保护的可选 framework、且存在非 Apple 路径时为 `linux_applicable`；
- 文档仅提及 macOS/Windows 支持，但入口是通用 CMake/Autotools 时不得仅凭文档词汇排除。

判定结果必须保存命中的信号名、来源路径和内容 SHA-256，不保存未经界定的模型判断。

## 6. 配额与后续角色

本 identity 只要求 CMake、Make、Autotools 各形成至少 12 个互不重复的 `linux_applicable` 项目族，
作为后续 build/reference 资格的 reserve pool。它不分配 design/calibration/evaluation 角色。

后续独立 identity 必须先完成：

1. 禁网双 clean build，排除运行时网络、平台、Docker 和超时失败；
2. 对稳定自然失败建立严格成功的 reference closure；
3. 只在 reference-eligible 集合中按预先固定哈希分配角色。

因此初始成功、无解失败或无法生成 ELF/`ar` 的候选不会再次占用 calibration/evaluation 配额。

## 7. 通过与停止条件

通过必须同时满足：

- 三个构建系统各至少 12 个唯一 `linux_applicable` 项目族；
- `SketchyBar` 和冻结合成反例全部被排除，多平台正例全部保留；
- 所有仓库级 API/解析错误保存 observation 后继续；
- 0 build command、0 Docker、0 credential read、0 Provider request、0 model token。

任一系统不足 12 项，或回归门禁失败，决定为
`stop_natural_failure_linux_applicability_v3`。不得修改查询、规则、配额、replacement 或 backfill 挽救
同一 identity。

通过决定为 `proceed_to_natural_failure_build_reference_qualification_v3`，只允许另行设计 build 与
reference 资格，不授权 Provider 或 Jev 比较。

## 8. 解释边界

静态门禁只能排除明确不适用，不能证明剩余项目一定支持 Linux，也不能证明 reference recipe 存在。
其价值是修复 v2 已观察到的构造效度缺口并减少无意义构建，不是新的通用平台识别算法。
