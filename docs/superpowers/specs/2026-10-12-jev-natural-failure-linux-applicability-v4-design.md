# Jev 自然失败 Linux applicability v4 设计

日期：2026-10-12。追踪：Issue #415。父结果：
`cpp-jev-natural-failure-linux-applicability-v3`。

## 1. 背景与问题

v3 的唯一正式 source-only attempt 完成 197/197 个未见候选，但在 7 条
`platform_ineligible` 边的 exact-commit 构造效度审计中出现 5 个明显误伤。误伤项目均有真实 Linux
路径；v3 只因入口或文档中存在局部 Apple/Windows 文本便排除了整个构建系统边。

问题来自分类语义，而不是 macOS 项目本身：

- 原始正则扫描整份入口，包括注释和条件分支；
- 文档中的局部 “only” 描述被当作项目级平台声明；
- 已采集的 Linux 文档证据没有进入分类决策；
- 宿主平台限制和裸机/固件等产物终点限制混为同一类 strong signal。

v4 的目标是建立一个保守、可审计的静态必要条件：排除非 Linux 用户态终点和真正的平台排他入口，同时保留
有明确 Linux 路径的多平台项目。它不尝试静态证明项目一定能构建。

## 2. 分类模型

v4 将信号拆成两个维度。

### 2.1 产物终点

`non_host_endpoint` 包括：

- 默认使用 `arm-none-eabi`、AVR、RISC-V ELF、Xtensa 等固定裸机交叉工具链；
- 默认产物为 kernel image、firmware hex/bin/upg 或 ROM；
- 根入口只定义上述终点，没有 Linux 用户态 ELF/`ar` 主路径。

该维度优先级最高。即使工具链运行在 Linux 上，GBA ROM 或裸机 firmware 也不是 Forge 当前严格终点，不能
被 Linux 文档覆盖。

### 2.2 宿主平台支持

宿主平台信号只在去除构建语言注释后的入口上扫描。Apple target/sysroot/toolchain、Mach-O universal、
MSBuild/WDK/MSVC-only 等信号只有在缺少明确 Linux 路径时才形成排除。明确 Linux 路径可以来自：

- 入口中的 Linux 条件分支、Linux target triple 或 Linux host 检测；
- 根级 README/BUILD/INSTALL 中的 Linux 构建标题、Linux build/install 命令、原生 Linux 支持或发行说明。

文档排他声明必须明确以项目、应用、工具或库为主语。局部组件、单一依赖、某个构建产物或安装步骤的
“Windows only”/“macOS only”不得提升为项目级排除。

### 2.3 决策顺序

每个构建系统边按以下固定顺序分类：

1. 根入口不可读：`ambiguous`；
2. 命中 `non_host_endpoint`：`platform_ineligible`，理由 `non_host_endpoint`；
3. 入口或文档存在明确 Linux 路径：`linux_applicable`，理由 `explicit_linux_path`；
4. 去注释入口仍有宿主平台排他信号：`platform_ineligible`，理由
   `exclusive_host_platform_without_linux_path`；
5. 文档有项目级排他声明：`platform_ineligible`，理由 `document_declares_exclusive_platform`；
6. 文档不可读且没有足够正面证据：`ambiguous`；
7. 其余具有普通根入口的项目：`linux_applicable`，理由 `portable_entry_without_exclusive_signal`。

分类输出必须分别记录原始入口信号、去注释后的有效信号、endpoint 信号、Linux 入口/文档信号和文档排他
信号。这样可以审计“词语存在”与“信号参与决策”的区别。

## 3. 冻结回归集

v3 的 7 个正式排除边全部转为已暴露 regression fixture，不进入 v4 结果样本：

| 项目 | v4 期望 | 关键依据 |
| --- | --- | --- |
| `jondgoodwin/cone` | `linux_applicable` | README 有 Ubuntu/Linux 构建；Windows only 只修饰部分包 |
| `LIJI32/SameBoy` | `linux_applicable` | 非 Darwin 默认 SDL，含 Linux install；Apple 工具在条件分支 |
| `metroidret/mf` | `platform_ineligible` | GBA ROM + `arm-none-eabi`，非宿主终点 |
| `mist-devel/mist-firmware` | `platform_ineligible` | 裸机 firmware + `arm-none-eabi` |
| `redhat-et/ripwire` | `linux_applicable` | 发布 Linux 二进制；Apple 词语位于注释/条件逻辑 |
| `SpeedBreakerProject/speedbreaker` | `linux_applicable` | 明确 Linux/SteamOS 构建；macOS only 是局部描述 |
| `Wallawalla47/Infernix` | `linux_applicable` | README 声明 Linux；MSBuild 只在注释 |

原 v3 的 `SketchyBar`、合成 Windows-only、裸机和多平台用例继续保留。协议校验必须执行整个 fixture，并要求
期望分类、理由类别和信号子集全部匹配；不能只依赖 pytest。

## 4. 未见项目与搜索框

v4 排除 v1/v2 历史项目和 v3 正式 attempt 的全部 197 个候选。历史集合固定到 versioned report SHA-256，
不能从聊天记录或当前 GitHub 状态重建。

搜索仍使用 GitHub repository search 的 C 与 C++ 两个查询，stars `50..20000`、size `<100000 KiB`、
updated `>=2024-01-01`、按 updated 降序；每个查询上限从 100 提高到 400，总上限 800。扩大搜索框只为获得
足够的根级 Autotools 候选，不改变资格条件。

每个候选固定默认分支当时 HEAD 的 exact commit，读取根 tree、根构建入口和最多 6 个根级 README/BUILD/
INSTALL 文档。`.gitmodules`、入口网络获取信号、缺少根入口、API/大小错误仍按既有 source contract 处理。

## 5. 分配与门槛

v4 不分配 design/calibration/evaluation 角色，只建立每系统 12 个 reserve。唯一项目族只能分给一个构建系统。
分配使用确定性的最大二分匹配，而不是在最稀缺系统耗尽时提前终止；报告必须同时给出：

- 每个系统全部 eligible edge 数；
- 最大唯一分配后的 reserve 数；
- 未满足的配额。

进入后续 build/reference qualification 必须同时满足：

- 冻结 regression fixture 全部通过；
- CMake、Make、Autotools 各 12 个唯一 `linux_applicable` 项目族；
- 0 infrastructure failure；
- 0 build、0 Docker、0 credential、0 Provider、0 model token；
- 正式 report、marker 和 evidence inventory 审计一致。

任一条件失败，决定为 `stop_natural_failure_linux_applicability_v4`，不 replacement、不 backfill、不调整规则。
通过决定为 `proceed_to_natural_failure_build_reference_qualification_v4`。

## 6. 证据与边界

identity 为 `cpp-jev-natural-failure-linux-applicability-v4`，使用全新 create-once evidence 根、manifest、Schema、
runner 和报告。v1-v3 runner、manifest、report、marker 和 raw evidence 永久只读。

本阶段是研究基础设施与数据资格。通过只说明静态必要条件和 reserve 数量满足要求；仍不证明 Linux 构建成功、
自然失败、reference closure、Jev/Agent 效果、成本收益或动态预算控制。只有 v4 通过后才能设计独立的双 clean
build + reference qualification identity。
