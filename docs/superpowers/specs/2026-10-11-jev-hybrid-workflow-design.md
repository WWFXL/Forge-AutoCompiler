# Workflow + Jev + Agent 混合编译链路设计

日期：2026-10-11。追踪：Issue #409。父证据：Issue #408 的 `cpp-jev-formal-comparison-v6`。

## 1. 问题与目标

Forge 当前产品链路已经把 Session 创建、源码获取、构建系统识别和最终清理交给确定性工具，但进入构建阶段后，Compiler Agent 通常持续负责依赖、配置、构建、产物整理和提交。Issue #408 证明 Jev 能在受控失败上安全选择 `dependency`、`configure` 或 `build`，却没有验证多步 Workflow 中的控制权交还。

本阶段实现一个最小混合协调器，回答：

> 确定性 Workflow 能否持有 Compile Session 生命周期和严格终点，在阶段失败时让 Jev 选择代码绑定恢复动作，并在拒答、故障或复杂恢复时调用有界 Agent，随后重新接管执行？

这是工程链路资格与 canary，不估计自然失败总体 treatment effect，也不验证动态预算控制的研究主张。

## 2. 系统边界

### 2.1 Workflow 持有的职责

- 按固定顺序执行正常路径：`dependency/setup -> configure -> build -> smoke -> artifact_stage -> submit/evaluate -> finalize`。
- 从真实命令记录、产物状态和 verifier 状态构造可审计观察。
- 在失败时枚举并绑定有限恢复动作；模型不能生成 Shell、参数或动作 ID。
- 保存循环次数、Jev 请求、直接动作、Agent handoff、验证和终态事件。
- 只有严格验证器可以产生成功终态；协调器、Jev 和 Agent 都不能直接宣告成功。

### 2.2 Jev 持有的职责

- 只在 Workflow 报告可恢复失败时接收 `DecisionState` 和闭集候选。
- 在 `dependency`、`configure`、`build`、`escalate_agent` 中选择。
- 返回正序/逆序选择和完整概率分布，由现有 `jev_controller` 校验身份、顺序一致性、概率合同、候选前置条件、校准阈值和 verifier 能力。
- 任何响应缺失、异常、版本漂移、低校准概率或合同不一致都 fail closed 到 Agent。

### 2.3 Agent 持有的职责

- 只处理 Jev 拒答、直接动作失败、候选不足或需要开放式诊断/修改的恢复节点。
- 使用现有有界 Agent Workflow Node；每次 handoff 有独立 attempt 和预算。
- Agent 可以冻结候选或报告失败，不能把自然语言结果当作严格成功。
- Agent 返回后，Workflow 必须重新读取权威 Session/候选/evaluator 状态，不能信任 Agent 自述推进状态。

### 2.4 严格裁判

CandidateVerifier、functional oracle、provenance 和 clean replay 仍是统一终点。Jev 直接动作和 Agent 候选使用相同裁判，不得因为路由方式不同而放宽验证。

## 3. 最小状态模型

新增 `HybridWorkflowObservation`，包含：

- 单调 `observation_id` 与 `state_id`；
- 当前构建系统与确定性 `phase_facts`；
- 最近失败阶段、错误摘要哈希和当前候选动作；
- 剩余循环、直接动作和 Agent handoff 预算；
- verifier capability；
- 权威终态：`pending`、`strict_success` 或 `terminal_failure`。

偏序义务状态 v1 不恢复。这里的状态只表达当前链路执行事实，不主张其相对简单特征具有新的预测增量。

协调器结果 `HybridWorkflowResult` 至少包含：

- `status`：`strict_success`、`terminal_failure` 或 `budget_exhausted`；
- 决策、直接动作、Agent handoff 和观察次数；
- 每一步的类型、原因、动作族、结果和状态 ID；
- 最终严格验证原因；
- 是否触发 fail-closed 路径。

## 4. 控制流程

```text
读取权威观察
  ├─ strict_success      -> 返回成功
  ├─ terminal_failure   -> 返回失败
  └─ pending failure
         ↓
枚举代码绑定候选
         ↓
请求 Jev（异常视为缺失响应）
         ↓
现有校准门禁 route_next_action
  ├─ direct_execute -> 执行唯一绑定动作
  │                     ├─ 成功 -> 重新观察并恢复 Workflow
  │                     └─ 失败 -> Agent handoff
  └─ escalate_agent -> Agent handoff
                         ↓
                  重新读取权威观察
                         ↓
               严格 verifier 决定终态
```

每个循环最多执行一个 Jev 直接动作和一个 Agent handoff。直接动作失败后不得在同一旧状态上再次请求 Jev。Agent handoff 返回后必须产生新的观察 ID；否则计为无进展并受固定安全预算约束。

## 5. 预算与停止语义

第一版只实现固定安全预算，不把它解释为动态预算机制：

- `max_cycles`：混合恢复循环上限；
- `max_direct_actions`：直接动作上限；
- `max_agent_handoffs`：Agent handoff 上限；
- `wall_clock_seconds`：协调器总墙钟上限。

预算在任何 Provider 或执行回调前检查。Jev 的 `DecisionState.remaining_actions` 和 `remaining_wall_clock_seconds` 来自协调器快照。预算耗尽返回 `budget_exhausted`，不能升级为成功或通过隐式重试延长。

动态预算控制需要未来独立研究问题、动作空间、基线和预注册；本实现中的固定计数器只是安全边界。

## 6. 故障与恢复合同

- Jev Provider 异常：记录稳定错误类别，升级 Agent，不在协调器内重试 Provider。
- 候选为空或不唯一：升级 Agent。
- 直接 executor 抛出异常或报告失败：只允许一次 Agent handoff，然后重新观察。
- Agent runner 抛出异常、无提交或预算耗尽：重新观察；若没有权威进展或预算耗尽则失败。
- verifier capability 不完整：禁止直接执行并升级 Agent；最终仍不能绕过缺失 verifier 获得成功。
- observer、ledger 或 identity 错误：终止为 `terminal_failure`，避免在未知状态继续产生副作用。
- finalize/cleanup 由调用层的 `finally` 保证，协调器结果不覆盖 cleanup 失败。

## 7. 实现位置与兼容边界

新增核心模块：

- `backend/packages/harness/deerflow/compile/hybrid_workflow.py`
- `backend/tests/test_hybrid_workflow.py`

协调器通过小型 callback/Protocol 接入 observer、Jev、直接 executor 和 Agent runner，不导入 `app.*`，也不读取 credential。现有 `jev_controller.py`、`agent_workflow_runtime*.py`、Compile Session 和 evaluator 继续复用。

本阶段先提供内部候选 API和实验 runner，不立即改变 Lead Agent 的公开入口。只有资格和 canary 证明控制权、验证与 cleanup 闭合后，才另行决定产品默认接线。历史 `run_compile_workflow` 不作为兼容接口恢复。

## 8. 验证阶段

### 8.1 零 Provider 单元资格

使用 scripted callbacks 覆盖：

1. Jev 高置信度直接动作成功后重新观察并严格成功；
2. 低置信度、顺序不一致、响应缺失和异常全部升级 Agent；
3. 直接动作失败后只升级一次 Agent；
4. Agent 自述成功但 observer 未确认时不能成功；
5. 状态未推进、预算耗尽、verifier 缺失和 executor 异常 fail closed；
6. trace 能重建每一次选择、执行、handoff 和终态。

### 8.2 真实 Docker 资格

使用 CMake、Make、Autotools 三个最小独立 fixture，在真实 Compile Session 中验证：

- bound action 只执行允许命令；
- Workflow 在直接动作或 scripted Agent 后重新接管；
- 产物必须经过 functional oracle、provenance 和 clean replay；
- 三类项目均能 cleanup 且 0 managed resources；
- 资格阶段 0 credential read、0 Provider request、0 formal attempt。

### 8.3 Provider canary

仅在前两级通过后创建独立 `cpp-jev-hybrid-workflow-canary-v1`。调用前必须冻结 exact commit、模型 `jev-1.13.0`、Agent Provider、样本、最大请求/token/费用、单臂超时、停止规则和 create-once evidence 目录。

最小 canary 至少让三种构建系统各出现一次 Jev 决策，并让整个批次至少出现一次 Agent handoff，以验证控制权交还；若自然数据没有触发 handoff，不得人为把“0 handoff”解释为 Agent 回退已验证。

## 9. 通过与停止条件

进入自然失败对照实验的必要条件：

- 所有零 Provider 合同测试通过；
- 三个 Docker fixture 严格成功、cleanup 成功且 0 managed resources；
- canary 中所有 Jev 直接动作均经过相同严格终点；
- Jev/Agent 故障均能 fail closed；
- 至少一次 Agent handoff 后 Workflow 成功重新观察并继续，或明确得到可解释失败；
- 无 identity、预算、ledger 或父 evidence 漂移。

以下任一情况停止并修复，不进入自然失败效果比较：

- Agent 返回后无法可靠恢复 Session 状态；
- 直接动作可以绕过严格验证或宣告终态；
- cleanup/orphan 不闭合；
- 必须修改冻结 evidence 才能运行；
- Jev/Agent Provider 故障导致未受控重试或预算越界；
- 三类构建系统中任一类无法形成同一协调合同。

## 10. 结论边界

即使本阶段通过，也只证明混合链路在限定资格/canary 场景中可执行、安全回退且严格终点闭合。它不证明自然失败成功率、成本收益、动态预算优势或开放世界泛化。后续 treatment effect 必须使用新的未见项目族、时间隔离、对照臂和独立正式 identity。
