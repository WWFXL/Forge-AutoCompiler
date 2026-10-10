# Jev 未见项目族正式三臂比较 v6

- 决定：`supports_jev_controlled_failure_claim`
- 完整 arm：`72/72`
- Agent 请求 / tokens：`474 / 5102633`
- Jev 请求 / input tokens / 费用：`24 / 34938 / $0.00146740`
- Provider 保守估算总费用：`$1.793915`
- strict 差值单侧 95% 下界：`0.292`，门槛 `-0.100`
- Jev 相对 AlwaysAgent 成本下降：`89.6%`，门槛 `20%`
- 直接动作 / 错误直接动作 / Agent 升级：`45 / 16 / 43`

## 严格终点

- `always_agent`：10/24 strict success
- `rule_gate_agent`：13/24 strict success
- `jev_gate_agent`：22/24 strict success

## 解释边界

本结果只覆盖冻结的受控构建失败和当前未见项目族。Provider 费用按冻结的 peak/cache-miss 价目表保守估算；结果不支持自然失败泛化、通用模型排名或动态预算优越性。
