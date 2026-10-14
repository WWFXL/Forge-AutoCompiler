# 进展预算感知 Jev 正式离线校准 v1 结果

- identity：`cpp-jev-progress-budget-calibration-v1`
- 决定：`stop_before_progress_budget_evaluation`
- 停止阶段：`calibration`
- Provider 请求：`15`
- 有效响应：`15`
- Input tokens：`14552`
- Output tokens：`1557`
- Jev 模型费用：`$0.00061118`

## 结论

实验按预注册停止规则在 `calibration` 阶段关闭，未执行或未形成完整 evaluation 分析。该结果不能估计 evaluation holdout 上的动作选择、预算路由或 Jev 相对轻量基线的增量。

## 解释边界

本 identity 不估计 controller treatment effect、严格成功率非劣、端到端成本下降、统计显著性、跨时间泛化或自然失败总体表现。
