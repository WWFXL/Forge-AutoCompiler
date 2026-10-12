# Linux 构建闭合资格 v5 设计

日期：2026-10-12。追踪：Issue #417。父结果：
`cpp-jev-natural-failure-linux-applicability-v4`。

## 1. 问题与修复目标

v4 的 source-only 门禁无法判断条件分支是否属于默认路径，也无法从文本确定默认 target 最终面向宿主 Linux、
kernel、console 还是设备。对 41 个 exact-commit 项目的构造效度审计发现：5 条正式排除中有 2 条 Linux 项目
误伤，36 条 reserve 中有 5 条非宿主项目误纳入。

v5 不再尝试用更多源码关键词证明 Linux 适用性。修复后的资格链把静态扫描降级为候选发现和风险标注，把
默认路径、编译目标和产物终点交给隔离执行与 Forge 结构验证。

核心规则是：

> 两次稳定的默认构建失败只能形成 failure candidate。只有独立 reference recipe 在两次 clean workspace 中均
> 生成宿主 Linux 用户态 ELF 或静态库，并通过结构、目标架构和来源检查后，该 failure candidate 才能进入
> 自然失败实验角色。

因此，macOS、Windows、kernel、console 或设备项目即使在 Linux 上重复失败，也不能再被当作可修复的自然失败。

## 2. 输入与边界

v5 从 v4 report 读取 exact commit、根构建系统边和静态风险信号。v4 的 `linux_applicable`、
`platform_ineligible` 与 `ambiguous` 不再是最终资格标签：只要项目满足根入口、无 submodule、无入口网络获取等
基础 source contract，均可进入动态观察。缺少根入口、存在 submodule 或入口主动获取网络内容的项目仍按独立
实验边界排除。

v5 不修改 v1-v4 manifest、runner、report、marker 或 raw evidence。它不调用 Provider，不读取 credential，
也不改变 Forge 的严格成功合同。

## 3. 动态观察

每个 `(exact commit, build system)` 在两个全新 workspace 中执行相同默认路径。源码获取在受控阶段完成；构建
容器使用冻结镜像、`--network none`、固定 CPU 并行度、命令与 session timeout。默认路径为：

- CMake：configure 到独立 `build` 目录，再用 verbose 模式构建默认 target；
- Make：从根目录以 GNU Make trace 和 verbose 变量构建默认 target；
- Autotools：按 `autogen.sh`、`bootstrap` 或 `autoreconf -fi` bootstrap，执行 `./configure`，再构建默认 target。

每次观察记录：

- 容器宿主架构、默认 C/C++ 编译器 target triple 和镜像 identity；
- 每条实际执行命令的 phase、退出码、timeout、完整 stdout/stderr 哈希与有界预览；
- workspace 构建前后文件快照；
- 新增或变化文件的 magic、Forge compiled-artifact 分类、ELF machine 和静态库成员 machine；
- 只从实际执行日志和生成的编译数据库提取的 cross-target、Apple、Windows 与 freestanding 信号。

源码正文中的平台词不能直接形成动态排除。动态 target 信号必须来自实际命令输出、生成的 build metadata 或真实
产物。

## 4. 单次与双次分类

单次观察按以下优先级分类：

1. Docker、挂载或采集失败：`infrastructure_failure`；
2. timeout：`timeout`；
3. 实际执行证据指向 Apple、Windows、foreign architecture、kernel、firmware、console 或设备工具链：
   `non_host_target`；
4. 命令成功，至少一个 Forge-valid compiled artifact 与宿主 machine 一致，且无 freestanding/non-host 信号：
   `host_userland_closure`；
5. 命令成功但没有 compiled artifact：`no_compiled_artifact`；
6. 网络失败：`network_dependency_failure`；
7. 其余命令失败：`bounded_failure`，保留 phase 与 error category。

双次 clean observation 只有类别和关键 target facts 一致才形成稳定分类。两个 `bounded_failure` 形成
`stable_failure_candidate`，但其 target 仍为 unresolved，不能分配实验角色。任何不一致均为
`inconsistent_observation`。

## 5. Reference closure

reference recipe 必须显式冻结有序命令、预期产物相对路径和允许的产物类型。它在两个全新 workspace 中执行，
并要求：

- 最终 build 命令仍是对应构建系统的默认 target 命令；允许增加 dependency 和 configure 步骤，但不能改选
  可选 Linux target 来替代默认 macOS、kernel、console 或 device target；
- 每条命令成功，且没有运行时网络访问；
- 每个声明产物通过 Forge 的 ELF/`ar` 结构分类；
- ELF 或 archive member machine 与冻结宿主 machine 一致；
- verbose/trace 执行证据能把至少一个合格产物路径绑定到宿主 compiler、linker 或 `ar` producer；静默命令或
  预置 binary 不能仅凭文件 machine 形成 host closure；
- 实际命令和 build metadata 不含 non-host/freestanding target 证据；
- 两次产物相对路径、类型和 target machine 一致；
- source HEAD 保持 exact commit，recipe 不改写 tracked source。

可执行物的任务级 functional oracle、provenance 和完整 clean replay 仍由后续 Forge verifier 执行。v5 reference
closure 是进入自然失败实验前的必要条件，不替代最终 S0-S5 裁判。

## 6. 项目资格与停止规则

项目边只有同时满足以下条件才是 `qualified_natural_failure`：

- 默认路径为 `stable_failure_candidate`；
- 两次默认失败的 phase 与 error category 一致；
- 冻结 reference recipe 为 `stable_host_userland_closure`；
- 没有 network、platform、target、artifact、source identity 或 infrastructure 排除项。

默认路径直接形成稳定宿主闭合的项目可作为 reference 或对照资产，但不是自然失败。稳定 non-host、无产物、
unresolved failure 和不一致结果全部不得用于补足配额。

在任何正式角色分配前，机制资格必须至少满足：

- 已暴露的 macOS/Windows/kernel/console/device 反例均不能成为 `qualified_natural_failure`；
- `ash/rakupp`、`libretro/opera-libretro` 不再因 source-only 文本直接排除；
- header-only/no-default-artifact 用例不会被误记为宿主构建成功；
- 合成 Linux ELF、静态库、foreign ELF、PE/Mach-O 与 freestanding 命令证据全部通过回归；
- Docker cleanup 后无受管容器残留。

如果真实反例仍能仅凭重复失败进入自然失败角色，或 Linux 正例仍被 source-only 标签直接排除，则 v5 机制失败，
不得进入全量 build/reference qualification。

## 7. 解释边界

机制资格通过只证明新的门禁能保守地区分“重复失败”与“已证明可闭合到宿主 Linux 用户态终点”。它不证明
Jev、Agent、Workflow、动态预算或自然失败上的成功率与成本收益。全量样本、reference recipe、角色配额、预算和
统计分析必须由新的正式 identity 预注册。
