# 动态预算控制轨迹可辨识性审计结果

> 日期：2026-10-12  
> Tracking Issue：[421](https://github.com/WWFXL/Forge-AutoCompiler/issues/421)  
> Identity：`cpp-dynamic-budget-identifiability-audit-v1`  
> 类型：结果分析；0 Provider、0 credential read、0 formal attempt

## 1. 关键结论

**决定：`stop_before_dynamic_budget_controller_implementation`。**

现有证据足以比较单个受控故障状态上的策略终点和大部分总成本，但缺少 stop 的共享预算机会成本、序列动作后状态、逐决策剩余预算、评测状态 checkpoint 和未暴露项目族，因此不能识别动态预算控制器。

这不是动态预算方向的负效果结论。它只说明当前数据不能支持 controller 的离线训练、选择或效果评价。

## 2. 已有证据能回答什么

- Jev v6：12 个同源状态、72 个 arm，严格成功 45、失败 27；72/72 ledger/result 哈希闭合。
- 总成本：71/72 arm 同时具备严格终点、墙钟、请求、token、费用、命令和 build execution；共观察 164 次 build execution。
- 缺失成本：`redis` repetition 2 的 Jev 请求因 `TypeSafeAPIConnectionError` 结束，1 次请求的 token 与费用未知，未做估算回填。
- 旧轨迹：进展状态 v1 有 409 个连续 observed-action 决策点，但没有未选择动作结果。
- Checkpoint：现存 4 个历史 checkpoint 均绑定环境哈希和剩余安全预算，但其干预不是本轮三动作。

## 3. 动作覆盖

纯动作要求该 arm 没有把直接动作失败与 Agent 自动回退合并。

| 状态/项目 | pure direct | pure escalate | stop | direct 后自动 escalate |
| --- | ---: | ---: | ---: | ---: |
| `benchmark` | 2 | 2 | 0 | 2 |
| `cc65` | 0 | 4 | 0 | 2 |
| `curl` | 2 | 2 | 0 | 2 |
| `haproxy` | 4 | 2 | 0 | 0 |
| `jemalloc` | 4 | 2 | 0 | 0 |
| `libarchive` | 2 | 2 | 0 | 2 |
| `libgit2` | 2 | 2 | 0 | 2 |
| `pcre2` | 2 | 2 | 0 | 2 |
| `quickjs` | 2 | 2 | 0 | 2 |
| `redis` | 3 | 3 | 0 | 0 |
| `simdjson` | 4 | 2 | 0 | 0 |
| `wolfssl` | 2 | 2 | 0 | 2 |

`stop` 的任务内终点虽可确定为失败，但当前实验没有共享 batch 预算，因此无法观察把节省资源转移给其他任务后的机会收益。

## 4. 资格门槛

| 门槛 | 观测 | 通过 |
| --- | --- | --- |
| `input_integrity` | `{"arms": 72, "checkpoint_files": 4, "ledger_result_matches": 72}` | 是 |
| `matched_policy_coverage` | `{"build_systems": ["autotools", "cmake", "make"], "states": 12, "three_policies_two_repetitions": true}` | 是 |
| `strict_terminal_and_total_cost` | `71` | 否 |
| `action_continuation_support` | `{"composite_direct_then_escalate_arms": 16, "required_actions": ["direct", "escalate", "stop"], "states": 12, "states_meeting_all_actions": 0, "states_without_pure_direct": ["cc65"], "stop_continuations": 0}` | 否 |
| `sequential_control_decisions` | `{"maximum": 1, "minimum": 1}` | 否 |
| `resumable_checkpoint_coverage` | `0` | 否 |
| `per_decision_budget_state` | `{"complete_snapshots": 0, "required_fields": ["wall_clock", "model_requests", "input_tokens", "output_tokens", "provider_cost", "build_executions"]}` | 否 |
| `unexposed_project_family_splits` | `{"outcomes_already_exposed": true, "split_roles": ["evaluation"]}` | 否 |

通过的两项说明旧证据具备完整账本和 matched 三策略结构。失败的六项包含完整成本、动作支持、序列状态、checkpoint、逐决策预算和隔离语料，不能用更多后验特征或阈值补齐。

## 5. 为什么现在不能实现 controller

1. 一个 Jev 失败请求缺少 token 与费用，完整成本向量只有 71/72。
2. 每个 v6 arm 只有一个控制决策；Agent 内部命令不是控制器可替换的独立决策点。
3. 16 个直接动作失败 arm 自动拼接 Agent，终点标签混合了两个动作，不能当作 pure direct 结果。
4. 72 个路由状态没有可恢复 checkpoint，也没有动作前/后六维剩余预算快照。
5. v6 的 12 个项目全部是结果已公开的 evaluation 数据，没有预算机制自己的 design/calibration holdout。
6. 每任务预算相互独立，停止一个任务不能把资源转移给另一个任务，因此无法评价预算分配。

## 6. 下一阶段最小采集

下一 identity 候选为 `dynamic_budget_trajectory_benchmark_qualification_v1`，先做 0 Provider 轨迹 benchmark 资格：CMake、Make、Autotools 各 3 个新项目族，每项至少 3 个多步状态，每状态 2 次 clean checkpoint replay。

资格通过前仍不实现 controller，也不调用 Jev/Agent。通过后再单独冻结 Agent continuation 的请求、token、费用、重复次数和停止规则。

## 7. 解释边界

能够支持：

- 现有 v6 受控故障数据的 matched policy、严格终点与 71/72 总成本覆盖边界；
- 历史 checkpoint 资产能够冻结环境和剩余安全预算；
- 是否达到实现动态预算 controller 前的数据可辨识性门槛；

不能支持：

- 动态预算 controller 的成功率、成本或时间效果；
- 任何未观察动作的反事实收益；
- 自然失败、开放世界或跨时间泛化；
- Jev、Agent 或其他模型的通用排名；

所有历史 identity 和 evidence 在本审计中保持只读。
