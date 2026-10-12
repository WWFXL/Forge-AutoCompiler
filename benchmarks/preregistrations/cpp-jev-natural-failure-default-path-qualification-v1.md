# Jev 自然失败默认路径资格 v1 预注册

日期：2026-10-12。追踪：Issue #419。identity：
`cpp-jev-natural-failure-default-path-qualification-v1`。

## 父样本与固定角色

唯一候选来源为 SHA-256
`d7b169290e47045bfde7d5ba6674917d15795d64780f963ea7f44ff40e6d7e6c` 的
`benchmarks/reports/cpp-jev-natural-failure-linux-applicability-v4.json` 中 36 个
`qualification.projects`。CMake、Make、Autotools 各 12 项；`system_rank` 1--3 为 design，4--6 为
calibration，7--12 为 evaluation。不得改项目、commit、构建系统、rank 或角色。

## 唯一正式 attempt

- evidence：`.compile-sessions/benchmark-evidence-jev-natural-failure-default-path-qualification-v1`；
- work root：`.compile-sessions/work-jev-natural-failure-default-path-qualification-v1`；
- 每项目 2 个独立 clean replicate，无重试；
- source 180 秒，单命令 300 秒，单 replicate 600 秒，总 attempt 43200 秒；
- image：`autocompiler:gcc13@sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a`；
- 构建 `--network none`、4 CPU、标准默认 target；
- 0 credential read、0 Provider request、0 model token。

## 分类与停止规则

动态分类、CMake probe 排除、machine/producer 绑定和 source identity 合同以版本化 design 与 runner 为准。
只有两个 clean replicate 都是相同 phase/error category 的 `bounded_failure` 才形成
`stable_failure_candidate`。

通过必须满足：36/36 项目级终结；每个项目两个 observation 均保存；三个构建系统各有 design `>=1`、
calibration `>=1`、evaluation `>=2` 个 stable candidate；已知非宿主反例未误纳入；cleanup 后 0 managed
resource；formal audit 有效；0 credential/Provider/model token。

通过决定为 `proceed_to_formal_reference_closure_qualification_v1`。任一门槛失败决定为
`stop_natural_failure_build_reference_qualification_v1`，不创建 reference、动作矩阵或 Provider identity。

## 冻结纪律

唯一 attempt 的 marker、成功、失败、超时、日志、报告和 inventory 永久只读。不得续跑、重跑、替换、回填、
前移角色、改预算或修改分类来挽救结果。本阶段不评价 Jev、Agent、成本收益或动态预算控制。

