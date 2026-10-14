# 进展预算感知 Jev 正式离线校准 v1 执行协议

## 身份

- Formal identity：`cpp-jev-progress-budget-calibration-v1`
- Tracking Issue：[#463](https://github.com/WWFXL/Forge-AutoCompiler/issues/463)
- Parent candidate：`cpp-jev-progress-budget-calibration-candidate-v1`
- Parent revision：`f5f76db338b9f87bf3916417301f363d50e88213`
- Implementation revision：`039f6226b93709d8065387a4a0ebdb3fe18c7eee`
- Runner SHA-256：`978e458b9a33e03864b1e67db9533d3c727b77eb340d12094f9178430a4c7f52`
- Manifest canonical SHA-256：`ffbdc6dfd9f940d327214c5bb3060fc798b455a44b67d5e7240db67574975116`

## 授权与硬预算

研究负责人已授权本 identity 读取仓库根 `jev-apikey.txt`、通过冻结 TypeSafe
egress 调用固定 `jev-1.13.0`，并写入本 identity 的 create-once evidence。
credential 和 Authorization header 不得进入日志、evidence、Issue、PR 或 Git。

- Calibration：15 个状态，最多 15 个物理请求
- Evaluation：仅 calibration 门槛全部通过后执行 15 个状态，最多 15 个物理请求
- 总物理请求：`30`
- 最大 input tokens：`200000`
- 最大 output tokens：`50000`
- 最大模型费用：`$0.0084`
- timeout：30 秒；SDK retry：0

## 执行与停止边界

每个状态在请求前写 attempt，收到响应后先写不含 raw body 的 observation，再做
模型版本、Choice、概率、usage 和顺序语义校验。任何失败、部分响应和用量均保留。
禁止 retry、replacement 和 backfill。Calibration 必须 15/15 有效、45 行标签同时
含正负类，并在零 observed unsafe direct 下覆盖至少 5/15 且三个构建系统各至少
1 个状态；否则决定为 `stop_before_progress_budget_evaluation`，不得执行 evaluation。

Evaluation 只运行和分析一次。核心门槛失败时决定为
`stop_jev_progress_budget_routing_before_controller`；只超过 RuleGate 而未达到冻结
TF-IDF 增量门槛时决定为
`stop_jev_as_incremental_component_keep_semantic_budget_method`；全部通过时决定为
`proceed_to_frozen_response_progress_budget_controller_replay_design`。

本 identity 不授权修改任何历史 evidence，不授权 evaluation 后调整 prompt、split、
模型、阈值或标签，也不授权 controller 实现。结果只支持冻结受控状态上的离线动作
选择、校准和预算路由判断，不支持端到端成功率、成本处理效应、显著性、跨时间泛化
或自然失败总体声明。
