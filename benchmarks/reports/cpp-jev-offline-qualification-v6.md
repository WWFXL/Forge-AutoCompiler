# Jev 离线资格实验 v6 结果

- identity：`cpp-jev-offline-qualification-v6`
- 决定：`proceed_to_controller_replay_qualification`
- Evaluation top-1：`18/18`
- 正反顺序一致：`18/18`
- 校准门禁直接执行覆盖：`18/18`
- 错误直接动作：`0`
- TF-IDF/逻辑回归：`17/18`
- Macro-F1：`1.000000`
- Multiclass Brier：`0.000322`
- ECE（5 个等宽区间）：`0.007222`
- Provider 请求：`72`
- Input tokens：`83210`
- Jev 模型费用：`$0.00349482`

## 结论

Jev 通过离线动作与校准门槛，可以进入冻结响应的零 Provider controller 回放资格；这还不是端到端收益证据。

## 门槛

```json
{
  "all_build_systems_correct_direct": true,
  "budget": true,
  "calibration_direct_coverage": true,
  "design_qualification": true,
  "direct_coverage": true,
  "evaluation_top1": true,
  "fixed_model_provider_execution": true,
  "order_agreement": true,
  "zero_wrong_direct_actions": true
}
```

## 解释边界

本实验只估计固定受控故障 holdout 上的动作选择、顺序稳定性和校准门禁。它不估计 controller treatment effect、严格成功率非劣、端到端成本节省、跨时间泛化或自然失败总体表现。
