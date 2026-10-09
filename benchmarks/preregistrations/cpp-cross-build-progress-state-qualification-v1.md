# 跨构建系统进展状态 v1 离线资格审计预注册

> 日期：2026-10-09
> Tracking Issue：[#382](https://github.com/WWFXL/Forge-AutoCompiler/issues/382)
> Identity：`cpp-cross-build-progress-state-qualification-v1`
> 类型：基础设施与结果分析
> 授权：研究负责人已冻结本研究问题，并授权本阶段直至完成

## 1. 冻结研究问题

> 在不读取隐藏答案的前提下，由可执行构建证据形成的跨构建系统偏序状态，是否比轮次、预算、阶段和错误类别
> 更能解释未见项目族与未来时间段中的短期状态转移，并足以支持后续预算动作实验？

本阶段不估计 controller treatment effect。历史轨迹只观察实际选择动作后的结果，不能识别未选择动作的反事实效果。
“支持后续预算动作实验”仅表示：状态在给定实际 action type 后仍有稳定的增量转移信息，值得另行设计干预。

## 2. 权限与证据边界

- 零 Provider、零 credential read、零 formal attempt、零旧 evidence 写入；
- mechanism v1/v2 及其他旧 experiment identity、ledger、marker、session 和日志全部只读；
- 不修改权限，不恢复 13 份当前用户不可读的历史 session；
- 不读取 ground-truth patch、hidden evaluator answer、candidate result、arm outcome、session verification、artifact、replay result 或最终 task report；
- 只生成新的版本化输入清单、派生数据、人工审计 fixture、资格报告和测试；
- 最终比较只能在输入清单、实现测试和人工状态重建门禁闭合后运行一次。实现缺陷只能在读取最终比较结果前修复并记录。

## 3. 输入语料与隔离

### 3.1 开发集

固定为 2026-09-25 的 Stage B Phase 5 v3 六条独立轨迹：

- 路径模式：`.compile-sessions/phase5-v3-*-191062f15d83/*/session.json`；
- 预期项目族：6；预期 session：6；
- CMake：`c-ares`、`cppitertools`、`yyjson`；
- Make：`openh264`、`uWebSockets`；
- Autotools：`libass`。

这些项目及历史结果已暴露，只用于拟合 extractor 后的固定统计模型，不估计总体成功率。

### 3.2 隔离测试集

固定为 2026-09-26 的 Stage C v5 baseline `b` 轨迹：

- session 顶层目录匹配 `.compile-sessions/stage-c-b-*`；
- `agent-workflow` attempt ID 匹配 `stage-c-v5-*-r1-b` 或 `stage-c-v5-*-r2-b`；
- 预期项目族：12；每族恰好 2 个预先存在的重复；预期 session：24；
- 三种构建系统各至少 3 个项目族；
- 所有项目族首次出现日期晚于开发集，并且不得与开发集仓库 URL 重合。

项目族定义为规范化后的上游仓库 URL。重复 session 不能当作独立项目；所有指标先在项目族内平均，再对项目族宏平均。

### 3.3 固定排除

排除 Stage C v3/v4、v6 offline reevaluation、v8 remediation、`clone-*`、formal parent、provider canary、UUID 开发 session、
合同反馈 mechanism 轨迹、构建系统为空、命令少于 1、任一输入哈希漂移或命令日志不可解析的 session。排除项不能在结果后补入。

## 4. 允许读取的字段

`session.json` 只允许：

- `repo_url`、`commit_sha`、`build_system`、`created_at`；
- `commands[].command_id`、`role`、`timeout_seconds`、`duration_seconds`、`timed_out`、`termination`、
  `started_at`、`completed_at`、`exit_code`、`log_path`。

禁止读取 `commands[].command`。命令日志只用于规范化公开执行诊断，不把原始文本、仓库路径、target 名称或日志哈希作为模型特征。

`agent-workflow/events.jsonl` 只允许读取 `event_type == "model.request_completed"` 的 `timestamp`、
`payload.request_sequence` 和 `payload.recorded_tokens`。其他事件只允许在输入清单中按整文件字节计算 SHA-256，不得解析 payload。

## 5. 偏序状态

每个实际命令开始前构造状态 `S_t = (V_t, O_t, X_t, D_t, B_t)`：

- `V_t`：当前有执行证据支持的 obligation；
- `O_t`：尚未获得执行证据的 obligation；
- `X_t`：曾被证实、后被上游动作失效的 obligation；
- `D_t`：上一命令的规范化诊断类别；
- `B_t`：命令数、模型请求、recorded tokens 和命令执行时长累计。

义务顺序固定为：

1. `source_available`；
2. `toolchain_ready`；
3. `configuration_generated`；
4. `build_graph_ready`；
5. `contract_target_built`；
6. `artifacts_staged`；
7. `functional_oracle_passed`；
8. `provenance_verified`；
9. `clean_replay_closed`。

Make 的 `configuration_generated` 固定为 `not_applicable`。首个 compiler 命令前，只有存在 exact commit 的
`source_available` 为 `verified`；其余适用义务为 `pending`。本阶段的命令级轨迹不使用 submit/evaluator 结果，
因此最后两项保持 `pending`，用于防止把 Agent 自报或隐藏 evaluator 结果写入状态。

固定失效规则：

- 成功 `dependency` 证实 `toolchain_ready`，并使此前已证实的配置及全部下游义务失效；
- 实际执行的 `configure` 使此前配置及下游义务失效；成功时证实 toolchain、configuration 和 build graph；
- 实际执行的 `build` 使此前 target 及下游义务失效；成功时证实 toolchain、configuration（适用时）、build graph 和 target；
- 实际执行的 `artifact_stage` 使此前 staging 及下游义务失效；成功时证实 staging；
- 实际执行的 `smoke` 使此前 functional 及下游义务失效；成功时证实 functional；
- `diagnostic` 不改变义务；
- `termination == policy_rejected` 的动作没有执行，不触发失效；timeout 可能产生部分副作用，按已执行处理；
- 失败不能把从未证实的义务标成失效，只更新诊断和保留 pending。

诊断类别按固定优先级归一为：`none`、`timeout`、`policy_rejected`、`dependency_missing`、`configuration_error`、
`compile_error`、`link_error`、`target_error`、`artifact_error`、`test_error`、`unknown_error`。匹配只使用通用错误模式，
不保留项目或 target 标识。

## 6. 转移标签

比较命令执行前后的义务状态与诊断：

1. `regression`：此前 verified 的任一义务变为 invalidated；优先于其他标签；
2. `progress`：至少新增一个 verified 义务且没有 regression；
3. `stagnation`：义务状态与诊断类别均不变；
4. `lateral`：义务没有推进或回退，但诊断类别发生变化。

预算字段不进入标签。当前命令的退出码、日志和完成时间只用于构造 `S_{t+1}` 与标签，绝不进入 `S_t` 特征。

## 7. 人工重建门禁

- 从 30 条固定语料的 eligible commands 中，按 `SHA-256(project_family + NUL + command_id)` 排序，
  每种构建系统取最小的 4 项，共 12 项；选择不得使用转移标签；
- 人工审计只读第 4 节允许的命令元数据和日志，记录 before/after obligation 与四类标签；
- obligation 状态逐字段一致率必须至少 0.90，transition 一致率必须至少 0.90；
- 合成 fixture 还必须分别覆盖四类转移、Make 的 `not_applicable`、policy rejection 和 timeout；
- 门禁失败表示 extractor 尚不合格，最终统计比较不得运行。若缺陷能在不读取最终结果时修复，需更新实现和人工审计记录；否则停止。

## 8. 固定特征与模型

所有模型都接收实际 `next_action_role`；任何模型都不接收 repo URL、project family、commit、时间戳、原始日志或最终状态。

- `budget`：turn index、已用命令数、累计命令时长、已完成模型请求数、累计 recorded tokens；
- `context`：build system、next action role；
- `error`：prior error category；
- `simple_combined`：前三者并集；
- `progress_state`：`simple_combined` 加每项 obligation status、frontier obligation、verified/invalidated 数量、
  上一转移类别和当前状态签名此前重复次数。

每组特征使用同一 `scikit-learn` Pipeline：数值特征在开发集拟合 `StandardScaler`，类别特征使用
`OneHotEncoder(handle_unknown="ignore")`，分类器为 `LogisticRegression(C=1.0, penalty="l2", solver="lbfgs",
max_iter=2000, random_state=382)`。不调参、不按测试结果选择模型。开发集缺少任一转移类别则直接判为数据不足。

## 9. 指标与不确定性

主要指标是隔离测试集的 multiclass log loss。先计算每条命令损失，再在项目族内平均，最后对 12 个项目族宏平均。
次要指标为同样宏平均的 multiclass Brier score、accuracy、macro F1，以及三种构建系统各自的项目族宏平均 log loss。

主要比较为 `progress_state - simple_combined`；负值表示状态更好。对项目族做 10,000 次有放回 bootstrap，固定
`numpy.random.default_rng(382)`，报告 percentile 95% 区间。重复 session 只在所属项目族内部贡献均值。

## 10. 通过与放弃规则

只有同时满足以下条件，才判定“足以支持后续预算动作实验”：

1. 输入清单和全部哈希闭合，开发/测试项目族零重合，日期严格前后分离，三种构建系统覆盖达标；
2. 四类标签在开发集和隔离测试集均有观测；
3. 第 7 节人工重建门禁通过；
4. `progress_state` 的项目族宏平均 log loss 至少比 `simple_combined` 低 `0.05` nat；
5. 主要差值的项目族 bootstrap 95% 区间上界小于 `0`；
6. Brier score 不比 `simple_combined` 高 `0.01` 以上；
7. 三种构建系统中至少两种的 log loss 改善，且任一系统恶化不超过 `0.10` nat。

任一条件失败，当前方向不进入 controller 或 F0/A1 设计。若失败原因是输入覆盖不足，结论是“现有资产不足”，
不得把它改写成状态机制无效；若输入和重建门禁通过但增量指标失败，则放弃当前状态机制。不得在结果后调整阈值、
切分、诊断模式、义务规则、特征或模型。

## 11. 输出与解释

输出固定为：

- `benchmarks/manifests/cpp-cross-build-progress-state-qualification-v1.json`；
- `benchmarks/fixtures/cpp-cross-build-progress-state-manual-audit-v1.json`；
- `benchmarks/reports/cpp-cross-build-progress-state-qualification-v1.json`；
- `benchmarks/reports/cpp-cross-build-progress-state-qualification-v1.md`。

报告必须分开记录 observed facts、derived measurements、研究判断和不能支持的结论。无论结果如何，都不能声称
controller 效果、strict success 改善、成本节省、因果效应、总体模型排名或全球首次。
