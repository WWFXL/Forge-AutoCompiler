# Agent Token 预算语义与证据一致性门禁实施计划

> Tracking Issue：[#436](https://github.com/WWFXL/Forge-AutoCompiler/issues/436)
> 设计：`docs/superpowers/specs/2026-10-13-agent-token-budget-semantics-gate-design.md`

## 1. 合同实现

1. 在 `AgentWorkflowBudget` 增加可选 `max_recorded_tokens_per_response`，并校验它只能与非空 `max_recorded_tokens` 一起使用。
2. 为 `AgentWorkflowBudgetTracker` 增加 bounded post-response 计量入口：先提交真实 Token，再返回或抛出稳定终止原因。
3. 请求前检查累计 Token 是否已经达到停止阈值；overshoot 后 remaining Token 固定为 0。
4. 保留 `consume()` 对 request、step、tool、command 等预算的请求前严格语义。

## 2. Runtime 接线

1. 共用一个严格 usage parser，验证 input/output/total 均为非负整数且 `total=input+output`。
2. 完整响应先写 `model.request_completed`，再提交到 post-response tracker；tracker 抛出的终止信号必须携带提交后的 snapshot。
3. usage 缺失或非法时写 `model.request_usage_incomplete`，以 `usage_incomplete` 失败闭合。
4. 单响应超过冻结上界时使用 `budget_contract_violation`，其他触阈保持 `budget_exhausted`。
5. 最终 `AgentBuildNodeResult.usage` 只读取 tracker 的权威 snapshot。

## 3. 验证

1. 扩展 tracker 和 Runtime 单元测试，覆盖 spec 中的所有边界。
2. 新增独立零 Provider gate runner，使用 scripted responses 生成结构化 JSON/Markdown 报告。
3. gate 报告核对 completed-event、node result、请求计数、终止分类、overshoot 和合成费用守恒。
4. 运行 Agent Workflow、Runtime v4、H0/H1 comparison 相邻回归，以及 Ruff 和 format check。
5. 复核 v2 inventory canonical SHA-256 仍为 `fb8f77bf05885dcb2f008fc2799de8361f7dd91af558815b7cff42b01cd5dce8`。

## 4. 阶段终点

通过时生成 `cpp-agent-token-budget-semantics-gate-v1` 报告，更新当前研究状态、工程 handoff 和 Issue #436。随后只准备 v3 是否值得执行的决策说明，在用户审查前不创建 v3 identity，不调用 Provider，也不进入 Workflow+Agent+Jev 新工程链路设计。
