# 跨构建系统类型化动作 benchmark 阶段 A 预注册

## 身份与阶段

- identity：`cpp-typed-action-benchmark-qualification-v1`
- tracking Issue：[#389](https://github.com/WWFXL/Forge-AutoCompiler/issues/389)
- 工作类型：零 Provider benchmark 资格审计
- 后续候选：Jev 类型化语义路由

本阶段只回答一个问题：能否构造一个跨 CMake、Make、Autotools、候选动作经过隔离执行且 outcome 可重复的决策 benchmark。它不估计 Jev、规则门禁、通用 LLM 或 controller 的效果。

## 研究边界

- Provider 调用、credential 读取、模型调用和模型 token 均为 `0`。
- 不实现 controller，不创建 Jev 请求，不使用 `jev-latest`，不校准 confidence。
- 不修改、补写或重新解释任何历史 experiment identity 和 evidence。
- 旧进展状态 v1 的 409 个 eligible 决策点只用于动作目录覆盖率；不读取未观察反事实，不把旧 Agent 动作当成正确动作。
- “直接执行”只表示跳过完整 Agent 推理并执行代码绑定动作。candidate、functional、provenance 和 clean replay 终点不得跳过。

## 项目池与隔离

冻结 24 个 project family，CMake、Make、Autotools 各 8 个。`design`、`calibration`、`evaluation` 分别包含 6、6、12 个互不重叠的 project family。

时间隔离使用 exact commit 的 committer timestamp。`design` 与 `calibration` 的最晚 commit 严格早于 `evaluation` 的最早 commit。项目、commit、source archive SHA-256、license SHA-256、构建配方和 oracle 以 `benchmarks/fixtures/cpp-typed-action-benchmark-source-pool-v1.json` 为准。

选择期间允许执行不进入 outcome matrix 的离线构建可行性检查。`libffi@bc553867...` 因固定镜像中的 Autoconf/Libtool 宏不兼容被排除；替代项目 `libuv@eb497c58...` 在冻结 benchmark outcome 前确定。此后不得根据动作结果替换项目。

## 状态与动作

每个项目固定 5 个状态：

1. `source_ready`
2. `configured_or_ready`
3. `build_failed`
4. `built`
5. `staged`

`build_failed` 由不存在的固定 target 产生，必须真实失败且不得修改源码语义。每个状态固定生成 3 个候选动作。动作闭集为：

- `dependency`
- `configure`
- `build`
- `diagnostic_probe`
- `smoke`
- `artifact_stage`
- `submit`
- `escalate_agent`

代码在模型之外绑定命令；模型不得生成命令或参数。每项动作记录 executor、命令、期望证据和风险等级。`escalate_agent` 是明确拒答/升级动作，不计作直接执行成功。

## Outcome 定义

每个候选动作从相同状态的隔离副本执行。动作 outcome 记录退出状态、timeout、日志哈希、有限日志尾部、执行后阶段事实、是否可直接安全执行以及是否增加证据。

- `direct_execution_safe`：绑定动作成功，且不是 `escalate_agent`。
- `progressed`：执行后确定性证据等级高于执行前。
- `eligible_next_action`：同时满足 `direct_execution_safe` 与 `progressed`。
- `route_acceptable`：直接动作安全，或明确选择 `escalate_agent`。

日志文本、耗时和非 bitwise executable 的字节差异不进入 replay categorical signature。退出类别、安全性、推进性和阶段事实进入 signature。

`submit` 只有在以下四项全部通过时才可标记为安全：

1. required artifact 结构检查；
2. functional oracle；
3. exact commit provenance；
4. 从 clean source 执行完整配方的 replay，并按冻结 bitwise policy 比较交付。

## 执行与重复

- 固定镜像：`autocompiler:stage-c-v1`
- image ID：`sha256:adbef4a26de49e9cd2c361a50b5fe2a000073a343b072ed0e515cc67e6e758b1`
- clone 阶段允许访问公开 HTTPS Git 仓库，但禁用 credential helper 和交互式 credential prompt。
- 所有 configure、build、diagnostic、smoke、artifact 和 clean replay 动作均在 `--network none` 容器中运行。
- CPU 上限为 4；单动作 timeout 为 900 秒。
- 每个项目、状态和候选动作执行两次独立 replay。
- 失败、timeout 和部分结果均保留，不只分析成功动作。

## 资格门槛

以下条件必须同时满足：

- 24 个项目全部形成 reference build 与 functional oracle 闭环，两次重复均成功；
- 每项目恰好 5 个状态，每状态恰好 3 个候选动作；
- 每个动作族至少出现在 20 个独立状态；
- 两次 replay 的 categorical outcome 一致率至少 95%；
- 动作目录覆盖至少 30% 的旧 409 个 eligible 决策点；
- 三个构建系统各有 8 个项目、40 个状态和完整 outcome matrix；
- 所有候选执行有明确退出或受 timeout 约束；
- Provider、credential、模型和历史 evidence 写入计数保持为 0。

全部通过时决定为 `proceed_to_jev_offline_qualification`。任一条件失败时决定为 `abandon_controller_and_keep_benchmark`。不得根据结果降低门槛、替换项目或只保留成功样本。

## 完成与解释

JSON 报告保存完整 `DecisionState`、`CandidateAction`、`ActionOutcome`、reference closure、覆盖率和裁决；Markdown 只作可读摘要。报告通过 outcome matrix 重新计算指标，不能手工填写结果。

阶段 A 通过只说明 benchmark 可执行且足以进入阶段 B。它不支持 Jev 判断准确率、confidence 校准、费用节省、成功率非劣、模型排名或通用路由创新主张。

## 执行中修正 Amendment 1（2026-10-09）

Attempt 1 在完成 20 个项目的两次重复后，于 `libuv` replicate 1 的 reference functional oracle 停止。libuv 本身已成功 configure、build 和 install；失败发生在使用 `-std=c11` 编译公开头的 oracle，glibc 因严格标准模式未暴露 `pthread_rwlock_t`。该故障是 oracle compile contract 错误，尚未产生完整资格报告或阶段 A 裁决。

Attempt 1 的失败记录固定在 `benchmarks/reports/cpp-typed-action-benchmark-qualification-v1-attempt-1-failure.json`。Amendment 1 只把 libuv oracle 的编译参数从 `-std=c11` 改为 `-std=gnu11`。项目、commit、split、状态、候选动作、outcome 定义、重复数、阈值和停止规则不变；不得复用 attempt 1 的部分 outcome。修正经单独离线 oracle 验证后，attempt 2 必须从全新工作目录完整重跑 24 个项目。
