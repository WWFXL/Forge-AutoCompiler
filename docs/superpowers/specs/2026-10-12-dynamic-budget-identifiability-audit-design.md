# 动态预算控制轨迹可辨识性审计设计

> 日期：2026-10-12  
> Tracking Issue：[#421](https://github.com/WWFXL/Forge-AutoCompiler/issues/421)  
> 工作类型：结果分析与后续数据设计；0 Provider、0 credential read、0 formal attempt

## 1. 研究问题

现有 Forge 只读证据是否足以在不重新运行历史 identity 的前提下，为
`direct / escalate / stop` 动态预算控制器构造无泄漏、可重复、可证伪的离线资格实验？

本审计不评价控制器效果。它只判断以下因果和计量前提是否成立：

1. 同一决策状态下是否观察到各候选动作的重复 continuation；
2. continuation 是否从可恢复且可核验的同一 checkpoint 派生；
3. 每个决策点是否记录剩余预算和动作后的新状态；
4. 是否同时记录严格成功与完整成本向量；
5. 是否存在未暴露的项目族，可用于独立设计、校准和最终评测。

## 2. 动作语义

- `direct`：执行一个代码预先绑定的 typed action，完成后重新观察权威状态并形成新的决策点。动作失败不能在同一标签内静默拼接 Agent。
- `escalate`：从同一 checkpoint 调用固定 Agent continuation；必须受剩余预算向量约束，并在每个有界动作后重新观察或进入严格终态。
- `stop`：在当前已用预算处终止该任务，记为未达到严格成功，并把未使用资源释放给同一冻结 batch 的其他任务。它不是“低成本失败”标签；只有共享预算可再分配时才具有控制价值。

## 3. 固定基线与预算

后续最小基线 `F0` 使用固定阶段 Flow：按构建系统和确定性阶段选择预先冻结的 typed action；动作失败后按固定时序升级 Agent；仅在预算耗尽时停止。候选 `A1` 才允许读取运行中的语义状态，在 `direct / escalate / stop` 中改变资源分配。

预算向量固定为：

`B = (wall-clock, model requests, input tokens, output tokens, provider cost, build executions)`。

必须同时记录每个决策点的已用量、剩余量和动作增量。任务级预算用于安全上限；主要比较使用项目 block 共享总预算，使 `stop` 释放的资源能够转移给其他任务。

## 4. 输入与只读边界

审计仅读取：

1. `cpp-cross-build-progress-state-qualification-v1` 的派生报告；
2. `cpp-jev-formal-comparison-v6` 的 manifest、报告和 72 个 arm 的 `result.json` / `experiment.jsonl`；
3. mechanism v2 现存的 4 个 checkpoint 元数据，用于确认 Forge 是否曾冻结环境和剩余预算。

以上 identity、manifest、report、marker 和 raw evidence 全部保持只读。审计不读取命令正文、Provider 响应正文或 credential，不重跑、不续跑、不 replacement、不 backfill。

## 5. 资格门槛

全部门槛通过，才允许决定
`proceed_to_dynamic_budget_offline_controller_qualification`：

| 门槛 | 阈值 |
| --- | --- |
| 输入完整性 | 绑定文件 SHA-256 全部一致；v6 为 72/72 arm，ledger/result 闭合 |
| matched policy coverage | 12 个状态均有三策略各 2 次重复，覆盖三种构建系统 |
| 严格终点与成本 | 每个 arm 均有严格成功、墙钟、请求、token、费用、命令和构建执行观测 |
| 动作支持 | 每个状态的 `direct / escalate / stop` 均至少有 2 个独立 continuation |
| 序列决策 | 每条可用于训练或评测的轨迹至少有 2 个控制决策点及动作后状态 |
| checkpoint | 每个评测状态都有同源、可恢复、哈希绑定的 checkpoint |
| 决策点预算 | 每个决策点均有完整预算向量的已用量、剩余量和动作增量 |
| 隔离 | 存在未暴露且项目族隔离的 design、calibration、evaluation split |

任一核心门槛失败，决定为
`stop_before_dynamic_budget_controller_implementation`。此时只能设计新的轨迹 benchmark，不能用缺失反事实的旧轨迹训练并评价控制器。

## 6. 指标

本审计报告结构覆盖率和缺口，不计算 treatment effect。后续实验的主要终点为固定共享预算下的 S0-S5 严格成功数或成功率；有序次要终点为 success-budget curve、失败按预算上限删失的受限平均时间、受限平均 token/费用、模型请求和 build execution 数。

失败任务必须保留在分母中。不能只报告成功案例均值，也不能用加权 utility 掩盖严格成功下降。

## 7. 解释边界

通过只能说明现有数据足以开展离线控制器资格，不说明控制器有效。失败只说明现有数据不足，不否定动态预算控制本身。受控故障结果不能外推到自然失败或开放世界。
