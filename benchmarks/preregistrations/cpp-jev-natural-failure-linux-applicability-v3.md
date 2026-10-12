# Jev 自然失败 Linux applicability v3 预注册

日期：2026-10-12。追踪：Issue #415。候选 identity：
`cpp-jev-natural-failure-linux-applicability-v3`。

## 问题

source-only 门禁能否在新的未见 C/C++ 项目池中排除明确无法闭合到 Forge Linux ELF/`ar` 终点的
构建系统边，同时为 CMake、Make、Autotools 各保留至少 12 个候选？

## 冻结分类

- `linux_applicable`：没有排他平台/终点信号，或存在明确 Linux/native 路径；
- `platform_ineligible`：入口固定到 Apple、Windows、裸机/固件或非宿主交叉目标，且没有 Linux 路径；
- `ambiguous`：可读性或冲突证据不足，fail closed。

分类只使用 exact commit 的根 tree、根构建入口和最多 6 个根级构建说明文档。所有信号及内容哈希写入
evidence。任何模型输出、构建结果或历史 outcome 都不得参与判定。

## 门槛

- `SketchyBar` 固定回归和合成 Apple/Windows/cross 反例全部排除；
- 合成 Make/CMake 多平台 Linux 正例全部保留；
- CMake、Make、Autotools 各至少 12 个唯一 `linux_applicable` 项目族；
- 项目级故障不终止批次；
- 0 build、0 Docker、0 credential、0 Provider、0 model token。

通过决定为 `proceed_to_natural_failure_build_reference_qualification_v3`；否则为
`stop_natural_failure_linux_applicability_v3`。

## 冻结纪律与解释

唯一 attempt 一旦创建，无论完成、失败或部分完成均只读；禁止重跑、replacement、backfill 或结果后改
规则。通过只说明 reserve pool 满足静态必要条件，不证明 Linux 构建成功、自然失败、reference closure、
Jev 效果、Agent 效果或动态预算效果。
