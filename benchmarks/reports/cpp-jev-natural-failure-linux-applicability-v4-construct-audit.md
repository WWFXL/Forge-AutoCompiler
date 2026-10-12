# Jev 自然失败 Linux applicability v4 构造效度审计

日期：2026-10-12。追踪：Issue #415。被审计 identity：
`cpp-jev-natural-failure-linux-applicability-v4`。

## 结论

v4 的唯一正式 attempt 和机械 `proceed_to_natural_failure_build_reference_qualification_v4` 决定保持原样，
但后验构造效度审计判定门禁仍不合格，决定为
`stop_before_natural_failure_build_reference_qualification_v4`。不能创建后续 build/reference identity。

本审计复核了正式排除的 5 条边和冻结 reserve 的 36 条边。5 条排除中有 2 条明显误伤；36 条 reserve 中
有 5 条明显误纳入。错误同时出现在两个方向，说明 v4 仍没有可靠判断默认主构建路径：它会把非默认条件分支中的
工具链信号提升为项目级排除，也会漏掉未被有限正则覆盖的 Windows DLL、kernel、PS Vita、Wii/Xbox 和 Android
设备交叉目标。

## 证据完整性

- 正式 execution revision：`1e79fd0bd0864c805f857b99c77f87d6b9cc8e77`；
- evidence：591 files / 1,488,806 bytes，canonical SHA-256
  `0d08616e0810a8def168a21fd838611b5a0dcb628d8aff3bbf638715fcc4e6bc`；
- 正式 JSON/Markdown SHA-256：`d7b169290e47045bfde7d5ba6674917d15795d64780f963ea7f44ff40e6d7e6c` /
  `b604dda8bda83f543fb769e636e748259b00770740e2406a0a36d37b013aa35f`；
- 正式 `audit` 返回 `valid=true` 且无错误；
- 41 个项目的 107 个根入口/文档 blob 均从记录的 exact commit 重新读取，Git blob SHA 和内容 SHA-256
  全部与正式 evidence 匹配。

这些事实证明正式运行记录完整，不证明 classifier 的语义标签正确。后验判断只写入独立审计报告，不修改 report、
marker 或 raw evidence。

## 排除项复核

| 项目 | 系统 | 审计判断 | 依据 |
| --- | --- | --- | --- |
| `ash/rakupp` | CMake | 误伤 | README 明确给出 Linux 容器、发行包和普通 CMake 源码构建；OSX sysroot 只在 Apple 分支。 |
| `incoai/splash` | Make | 应排除 | README 要求 Apple Silicon/macOS；Make 固定 Xcode、Metal、Apple frameworks，并显式拒绝非 Darwin/arm64。 |
| `libretro/opera-libretro` | Make | 误伤 | 默认 `platform=unix`，Linux 产物是 `opera_libretro.so`；裸机和 Apple 工具链只在非默认平台分支。 |
| `metroidret/mzm` | Make | 应排除 | 默认 `all` 生成 GBA ROM，依赖 `arm-none-eabi` 和 baserom。 |
| `SAT-R/sa3` | Make | 应排除 | 虽有显式 SDL 辅助目标，默认 `PLATFORM` 和 `all/rom` 路径仍生成 GBA ROM。 |

排除项上的描述性误伤为 2/5。该比例只描述这 5 条冻结边，不是总体 false-positive rate 估计。

## Reserve 复核

36 条 reserve 中，31 条有可辩护的 Linux 用户态主路径；以下 5 条明显不满足 Forge 当前终点：

| 项目 | 系统 | 错误类型 | exact-commit 依据 |
| --- | --- | --- | --- |
| `gta-reversed/gta-reversed` | CMake | Windows 专用主路径 | README 说明产物是注入 GTA:SA 的 DLL，要求 Visual Studio、Windows Compact exe 和 ASI loader。 |
| `seL4/seL4` | CMake | kernel endpoint | 根入口使用 `-ffreestanding`、`-nostdlib`、kernel linker flags 和平台架构配置构建 seL4 kernel。 |
| `RBEnhanced/RB3Enhanced` | Make | console endpoint | 默认 `all` 构建 Wii MOD 和 Xbox DLL，固定 `powerpc-eabi` 与 XEDK/MSVC。 |
| `Rinnegatamante/vitaGL` | Make | console endpoint | Make 固定 `arm-vita-eabi`、Cortex-A9/Vita flags，产物是 PS Vita 库。 |
| `Gamer92000/echo-dot-assist` | Make | device cross target | Linux PC 只是宿主；Make 固定 Android NDK 交叉编译器并链接 Echo 固件库。 |

`fastfloat/fast_float` 和 `tzcnt/TooManyCooks` 是 Linux 适用的 header-only 库，但默认配置不生成 compiled
artifact。本审计不把它们计作平台/终点误纳入；它们必须在独立 build qualification 中接受“是否能形成 Forge
严格交付”的动态判定。`gbdev/rgbds` 虽服务于 Game Boy 开发，但根 Make 构建的是 Linux 可运行的 assembler、
linker 等宿主工具，因此不属于 ROM endpoint。

Reserve 中的描述性误纳入为 5/36。该比例是对机械选中集合的全量复核，不代表搜索总体或未来项目的错误率。

## 失败机制

v4 修复了注释污染和部分显式 Linux 文档覆盖，但仍以“文件内是否出现某个词”为主要语义单位，没有解析信号
是否位于默认条件分支、默认 target 的依赖闭包，或编译器最终面向哪个运行环境。由此产生两类对称错误：

1. `opera-libretro` 的 `arm-none-eabi` 位于非默认平台分支，却被当作默认 endpoint；`rakupp` 的 OSX sysroot
   位于 Apple 分支，却被当作项目级排他条件。
2. `seL4`、Vita、Wii/Xbox、Android NDK 和 Windows DLL 使用了规则表之外的表达方式，普通根入口文件名又让
   它们落入 `portable_entry_without_exclusive_signal`。

继续增加工具链关键词只能修复已暴露例子，不能证明默认路径作用域。下一版不能继续把无作用域正则作为最终
资格裁判；必须把“源码候选发现”和“默认构建路径/实际产物终点确认”拆开，使用可执行或可解析的目标证据，并由
Forge verifier 对 Linux 用户态 ELF/`ar` 闭合做最终判断。

## 解释边界与下一步

本审计证明 v4 source-only classifier 不足以冻结后续自然失败样本。它没有执行构建，不证明其余 31 个 reserve
可以构建、存在自然失败或具有 reference closure，也不评价 Jev、Agent、动作路由、成本收益或动态预算控制。

v4 identity、report、marker 和 raw evidence 永久只读。后续应先冻结新的资格设计：source-only 阶段只做高精度
候选发现并保留风险信号；默认构建路径和目标端点在隔离环境中用非 Provider 的 build/reference qualification
确认。只有实际产物与 Forge 严格 verifier 闭合后，项目才能分配实验角色。
