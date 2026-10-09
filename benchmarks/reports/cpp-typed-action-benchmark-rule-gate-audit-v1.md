# Jev benchmark v1 RuleGate 可辨识性审计

- identity：`cpp-typed-action-benchmark-rule-gate-audit-v1`
- 来源资格报告 SHA-256：`bdbf2bca0f76c978630d58f618202cc9fb61d968ed287dd74a2f29f5292151d6`
- 决定：`stop_jev_provider_qualification_and_redesign_benchmark`

## 关键结果

`RuleGate` 只读取确定性 `phase_facts` 和可用动作族，不读取构建日志。在 120 个状态上，top-1 安全率、直接执行覆盖率均为 `1.0000`，错误直接动作率为 `0.0000`。

| 构建系统 | 状态 | top-1 安全率 | 直接覆盖率 | 错误率 |
|---|---:|---:|---:|---:|
| cmake | 40 | 1.0000 | 1.0000 | 0.0000 |
| make | 40 | 1.0000 | 1.0000 | 0.0000 |
| autotools | 40 | 1.0000 | 1.0000 | 0.0000 |

| split | 状态 | 直接覆盖率 |
|---|---:|---:|
| design | 30 | 1.0000 |
| calibration | 30 | 1.0000 |
| evaluation | 60 | 1.0000 |

48 个状态有两个合格下一动作，72 个状态有一个合格下一动作。冻结的阶段 B 门槛要求 Jev 在相同风险下相对 RuleGate 增加至少 10 个百分点覆盖率；当前 RuleGate 覆盖率已为 100%，最大可能提升为 0 个百分点，因此该比较在 v1 上不可辨识。

## 研究决定

阶段 A 的“可执行且可重复”结论仍成立，但它没有证明 benchmark 足以评价语义路由。当前 v1 的状态被确定性阶段事实完全解出，语义日志没有产生增量决策空间。因此停止 Jev Provider 资格、controller 和端到端比较，不消费模型预算。

这不是 Jev 效果失败，因为本阶段没有调用 Jev。若继续该研究问题，必须建立新 identity：在相同 coarse phase facts 下构造需要不同动作的多种失败根因，以候选动作后的冻结 continuation 和严格终点决定标签，并使用新的未暴露项目族与时间后移 evaluation split。

本审计 Provider `0` 次、credential `0` 次、模型调用 `0` 次、模型 token `0`。
