# Linux 构建闭合资格 v5 工程 canary

日期：2026-10-12。追踪：Issue #417。身份标签：
`cpp-jev-natural-failure-linux-build-closure-canary-v5`。

## 结论

非正式工程 canary 通过，决定为 `proceed_to_formal_build_reference_qualification_design`。

这次修复解决了导致 `SketchyBar` 被误当作自然失败的判定漏洞：重复的 Linux 构建失败现在只形成
`stable_failure_candidate`，不能直接进入自然失败样本；项目还必须用绑定默认 target 的 reference recipe 在两个
clean workspace 中形成稳定的宿主 Linux 用户态 ELF/`ar` 闭合，并保持 exact-commit source clean。

在 10 个已做过人工构造效度审计的 exact commit 上：

- 20/20 个 clean observation 有界终结，0 infrastructure failure，cleanup 后 0 受管容器；
- 6 个非宿主反例中，5 个被实际默认路径直接识别为 `stable_non_host_target`；
- `gta-reversed` 在 CMake 4.2 版本检查处提前失败，target 证据未出现，因此保守停在
  `stable_failure_candidate`，没有被判为 Linux 适用；
- `libretro/opera-libretro` 两次生成 x86_64 `opera_libretro.so`，证明 v4 的 source-only 排除是误伤；
- `fast_float` 的 CMake 默认 `all` 没有项目编译产物；排除 CMake compiler ABI 探针后正确得到
  `stable_no_compiled_artifact`；
- 0/10 项在缺少 reference closure 时成为 `qualified_natural_failure`。

## 方法

每个项目从冻结 exact commit 获取源码，在 `autocompiler:gcc13`、`--network none`、4 CPU 的全新 workspace 中
执行两次默认路径。CMake 和 Make 均开启 verbose/trace，但不指定可选 target。runner 比较构建前后文件，调用
Forge `_classify_compiled_artifact` 验证 ELF/`ar` 结构，并提取 ELF/archive member machine。平台信号只来自
实际执行日志或真实产物，不再从整份源码文本直接提升为最终分类。宿主闭合还要求日志把合格产物路径绑定到
实际 compiler、linker 或 `ar` producer；静默命令或预置 binary 只能保持 target unresolved。

单命令 timeout 为 120 秒，单次 observation 为 240 秒，源码步骤为 180 秒。全过程 0 credential、0 Provider、
0 model token。

## 项目结果

| 项目 | 旧 source 判断 / 审计组 | 动态结果 | 关键证据 |
| --- | --- | --- | --- |
| `ash/rakupp` | `platform_ineligible` / Linux 正例 | `timeout` | 两次均进入宿主 x86_64 编译，但未在 120 秒内完成；未再静态排除 |
| `libretro/opera-libretro` | `platform_ineligible` / Linux 正例 | `stable_host_userland_closure` | 两次生成 x86_64 `opera_libretro.so` |
| `felixkratz/SketchyBar` | v2 误纳入 / macOS | `stable_non_host_target` | 实际默认路径使用 Apple target triple |
| `gta-reversed/gta-reversed` | `linux_applicable` / Windows DLL | `stable_failure_candidate` | CMake 4.2 版本门禁早于 target；必须有默认 target reference 才能继续 |
| `seL4/seL4` | `linux_applicable` / kernel | `stable_non_host_target` | 默认 configure 要求 `KernelPlatform` |
| `RBEnhanced/RB3Enhanced` | `linux_applicable` / console | `stable_non_host_target` | 实际调用 Xbox `cl.exe` |
| `Rinnegatamante/vitaGL` | `linux_applicable` / console | `stable_non_host_target` | 实际调用 `arm-vita-eabi-gcc` |
| `Gamer92000/echo-dot-assist` | `linux_applicable` / device | `stable_non_host_target` | 默认依赖设备 firmware/rootfs |
| `fastfloat/fast_float` | `linux_applicable` / no-artifact risk | `stable_no_compiled_artifact` | 默认 `all` 为 no-op，只有被排除的 CMake ABI 探针 |
| `tzcnt/TooManyCooks` | `linux_applicable` / no-artifact risk | `stable_failure_candidate` | configure 稳定缺少 `hwloc`；仍需 reference closure |

## 支持与不支持的结论

本 canary 支持以下工程结论：

1. source-only 平台标签应降级为风险信号；
2. 动态默认路径可以区分已观察的宿主闭合、非宿主 target、无产物、timeout 和 target 未决失败；
3. “稳定失败 + 默认 target reference 双闭合”能阻止 macOS/Windows/kernel/device 项目仅凭重复失败进入样本；
4. 构建系统自身的 compiler probe 必须从项目产物中排除。

本结果不是 formal experiment。临时 raw observation 没有作为冻结 evidence 发布，因此它不支持全量候选通过率、
各构建系统角色配额、Jev/Agent 效果、成本收益或动态预算结论。下一阶段应建立独立正式 identity，在更大的冻结候选
池上完成默认失败与 reference closure，并在通过后才分配自然失败角色。

机器可读摘要：
`benchmarks/reports/cpp-jev-natural-failure-linux-build-closure-canary-v5.json`。
