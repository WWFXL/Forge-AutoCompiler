# Jev 逐动作安全判断问题分解资格实验规格

## 1. 研究目的

Issue #463 的 `cpp-jev-progress-budget-calibration-v1` 在 15 个 calibration
状态上 11 次选择 `escalate_agent`，四选一正反顺序只有 7/15 一致。只读事后
诊断表明，若忽略 `escalate_agent` 并只在三个局部动作中取最高概率，精确最优
动作从 4/15 上升到 7/15，局部动作顺序一致性从 7/15 上升到 14/15；但仍有
5/15 个强制局部动作不安全。

本实验回答一个更窄的机制问题：

> Jev 的保守升级主要是四选一问题结构造成的，还是因为逐动作判断仍缺少具体动作
> 上下文，或者 Jev 对该任务本身缺乏足够能力？

本实验是离线资格与结果分析，不是 controller 或端到端 treatment experiment。

## 2. 身份与证据边界

- Tracking Issue：[#465](https://github.com/WWFXL/Forge-AutoCompiler/issues/465)
- Formal identity：`cpp-jev-action-safety-decomposition-v1`
- 父 outcome identity：`cpp-progress-budget-jev-identifiability-qualification-v1`
- 历史对照 identity：`cpp-jev-progress-budget-calibration-v1`
- 新 evidence：`.compile-sessions/benchmark-evidence-jev-action-safety-decomposition-v1`

父 benchmark 的状态、动作 branch、预算决策和标签只读。#463 的请求、响应、校准、
报告和 evidence 只读，不在本实验中运行它的 evaluation、降低它的阈值或补齐它的
停止分支。

## 3. 数据角色

继续使用父 benchmark 机械冻结的项目族隔离：

| 角色 | CMake | Make | Autotools | 状态数 |
| --- | --- | --- | --- | ---: |
| calibration | `p-ranav/argparse` | `kgabis/parson` | `troglobit/libuev` | 15 |
| evaluation | `neargye/magic_enum` | `antirez/sds` | `ivmai/libatomic_ops` | 15 |

每个状态的三个局部动作都已有两次隔离 clean branch。只有两次都通过 strict endpoint
的动作才标记为 safe；最低成本 safe 动作是 optimal action。标签不来自历史 Agent
轨迹或人工期望。

calibration 只用于拟合 Platt 模型和选择阈值。evaluation 项目族从未被 #463 调用
Provider，本实验只执行和分析一次。该隔离支持项目族 holdout，不支持时间泛化、
自然失败总体或开放世界声明。

## 4. 实验条件

### 4.1 冻结历史对照

`four_way_choice_frozen_reference` 只读取 #463 的 15 个 calibration 响应及其正式
分析。它不产生新请求，只用于描述问题分解前的保守升级和顺序敏感性。

### 4.2 `action_noul`

Provider state 只包含：

- build system；
- phase facts；
- progress facts；
- 原始 semantic failure log。

同一请求对 `dependency`、`configure`、`build` 分别提出 Noul 命题：执行已经绑定
的该局部动作，并继续冻结的 deterministic continuation 与 strict endpoint，是否是
安全的下一步。`true` 明确指两次 clean branch 均可达到 strict endpoint；`false`
指动作失败、停滞、破坏状态或仍需要未绑定修复。

### 4.3 `action_card_noul`

问题与 `action_noul` 相同，额外在 state 中提供三个规范化 `ActionCard`：

- `action_family`；
- `operation_summary`；
- `bound_step_count`；
- `workspace_effect`；
- `expected_frontier_transition`；
- `expected_evidence`。

ActionCard 由冻结 bound command 机械归纳，只说明动作将做什么。禁止出现：

- 原始 Shell、参数和 base64 内容；
- 项目名、commit、state ID 或项目族；
- hidden fault 名称；
- action outcome、safe/optimal label 或预算；
- 历史 Agent 行为。

## 5. 顺序敏感性与请求合同

每个 Noul condition 对每个状态只发一个物理请求。请求中包含六个 Noul：

1. 按 `dependency -> configure -> build` 顺序提出三个主问题；
2. 按 `build -> configure -> dependency` 顺序重复相同的三个问题。

每个动作得到两个真概率。冻结的保守原始分数为：

```text
raw_action_score = min(primary_noul, reversed_noul)
```

这样问题顺序带来的任一低判断都会阻止该动作直接执行。实验同时报告每个动作两次
概率的绝对差和每状态最大差，但不在看到结果后修改组合规则。

## 6. 校准与动作选择

每个 Noul condition 独立产生 `15 states x 3 actions = 45` 个 calibration rows：

```text
logit(clipped raw_action_score) -> action is safe
```

使用 `sklearn.linear_model.LogisticRegression` 做一维 Platt scaling，参数冻结为：

- `C=1.0`
- `solver=liblinear`
- `random_state=465`
- `max_iter=1000`
- clipping epsilon `1e-6`

阈值不是预设概率。对 calibration 中所有校准后动作概率逐一作为候选阈值，并按以下
过程选择：

1. 每个状态保留概率不低于候选阈值的动作；
2. 按 `build=1, configure=2, dependency=3` 选择最低成本动作；
3. 没有动作通过时选择 `escalate_agent`；
4. 排除任何产生已观察 unsafe direct 的阈值；
5. 在剩余阈值中选择 direct state 覆盖最多者；
6. 覆盖相同时选择更高阈值。

这选择的是“整个确定性动作选择器”的安全阈值，而不是逐行分类阈值。

## 7. BudgetFit

Jev 不接收预算。冻结动作选择器产生 local action 或 `escalate_agent` 后，代码复用父
benchmark 的六维 direct charge、Agent reservation 和三个预算 profile：

```text
accepted local action and direct charge fits -> direct
otherwise Agent reservation fits            -> escalate_agent
otherwise                                  -> stop
```

所有 route 与父 benchmark 的 45 个 evaluation budget decisions 比较。不得让模型
做算术、成本比较或 stop 判断。

## 8. 指标

每个 Noul condition 报告：

- 45 个 action rows 的 ROC-AUC、Brier 和 safe/unsafe 分布；
- 主/逆序 Noul 的平均和最大绝对差；
- calibration 阈值、direct coverage、错误 direct 和分系统覆盖；
- evaluation 的 exact optimal action、safe selected action、direct coverage、错误
  direct risk、分系统覆盖；
- 45 个 budget decisions 的 joint correct、route accuracy、direct count 和 wrong direct；
- 请求数、input/output tokens、费用和延迟。

冻结基线为 evaluation 上：

- `TF-IDF+BudgetFit` action top-1 `12/15`；
- `TF-IDF+BudgetFit` joint correct `39/45`，direct `18/45`，wrong direct `0`；
- `RuleGate` joint correct `27/45`。

## 9. 资格门槛与关键结论

一个 Noul condition 的核心资格要求全部满足：

- calibration：15/15 有效响应、45 行含正负类、零 observed unsafe direct、direct
  至少 5/15，三个构建系统各至少 1 个；
- evaluation：15/15 有效响应、direct 至少 5/15，三个构建系统各至少 1 个，wrong
  direct risk 不超过 10%，exact optimal action 至少 10/15；
- BudgetFit：joint correct 至少 32/45，且三个系统各至少 10/15。

匹配强轻量基线要求：action exact 至少 12/15、joint correct 至少 39/45、wrong
direct 不超过 TF-IDF 的 0。实质增量要求在保持上述安全性时满足下列至少一项：

- action exact 至少 13/15；
- joint correct 至少 40/45；
- joint correct 不低于 39/45 且 direct 多于 18/45。

关键结论按固定优先级产生：

1. `action_noul` 核心通过：问题分解本身足以恢复低风险 direct；
2. `action_noul` 失败但 `action_card_noul` 核心通过：只有 ActionCard 上下文增强足够；
3. 两者核心均失败：当前 Jev 逐动作路径停止在 controller 前；
4. 对任何核心通过条件，若未匹配 TF-IDF，则 Jev 只保留为实现/消融；匹配但无实质
   增量时不主张 Jev 优于轻量基线。

## 10. Provider 与停止规则

- `typesafe-sdk==0.7.3`
- 固定模型 `jev-1.13.0`，拒绝 alias 或响应版本漂移
- timeout 30 秒，SDK `max_retries=0`
- 两个条件各 30 个状态请求，共最多 60 个物理请求
- 最多 400,000 input tokens、100,000 output tokens、`$0.0168`
- 请求前 create-once 写 attempt；响应后先写不含 raw body 的 observation，再校验语义
- credential、HTTP 401/403、模型、响应合同或预算漂移立即失败关闭
- 禁止 retry、replacement、backfill、结果后改 prompt/split/calibrator/threshold/label

Provider 前必须完成零调用 mock、父 evidence hash 审计、credential 元数据检查、egress
检查、测试、提交和推送，并由 authorized manifest 绑定 exact implementation revision。

## 11. 解释边界

正向结果最多支持：在 6 个冻结项目族、30 个受控构建状态和固定模型版本上，逐动作
Noul 加确定性动作选择和 BudgetFit 能形成低风险 direct，并说明 ActionCard 是否提供
必要信息。它不支持 controller treatment effect、严格成功率非劣、端到端成本下降、
自然失败、时间泛化、开放世界或通用模型排名。
