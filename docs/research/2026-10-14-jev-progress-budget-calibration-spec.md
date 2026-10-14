# 进展预算感知 Jev 离线校准实验规格

## 1. 阶段定位

- Tracking Issue：[#459](https://github.com/WWFXL/Forge-AutoCompiler/issues/459)；
- 父资格 identity：`cpp-progress-budget-jev-identifiability-qualification-v1`；
- 父报告：`benchmarks/reports/cpp-progress-budget-jev-identifiability-qualification-v1.{json,md}`；
- 当前文档状态：spec-only，尚未创建 Provider execution identity；
- 当前权限：0 credential read、0 Provider/Jev/Agent call、0 model token、0 formal attempt/evidence。

本阶段设计一个独立的 Jev 离线校准实验，回答固定版本 Jev 能否从真实构建失败状态中选择类型化动作，并由确定性预算门禁把动作判断转换为 `direct`、`escalate_agent` 或 `stop`。本阶段只评价动作判断、校准和离线路由，不实现完整 controller，也不估计端到端编译成功率或 Agent 成本收益。

研究贡献定位为自动化编译领域的语义动作判断与预算路由方法资格。Jev、Platt scaling、选择性分类和预算门禁本身均有既有方法基础；可能新增的价值来自跨 CMake、Make、Autotools 的真实动作 outcome、严格 replay closure、项目族隔离校准以及预算条件下的联合评价。

## 2. 父证据与研究缺口

Issue #457 已建立 6 个项目族、30 个语义状态、240 个真实 action branches 和 90 个 matched budget decisions。120/120 个状态-动作对重复一致，30/30 个状态随预算改变最优路由；RuleGate route accuracy 为 `0.6000`，TF-IDF+BudgetFit 为 `0.8667`。

该结果证明任务可辨识，但尚未回答：

1. Jev 在新状态表示上能否选择最低成本安全动作；
2. Jev 概率能否经项目族隔离校准后支持低风险 direct；
3. Jev+BudgetFit 是否比强轻量基线提供足以承担 Provider 成本的增量；
4. 动作顺序敏感性和 Provider 失败是否会破坏安全门禁。

旧 `cpp-jev-offline-qualification-v6` 的阈值、预测和效果不得导入。它只为 API 合同、概率规范、正反顺序问题和校准实现提供工程先例。

## 3. 研究问题与假设

### RQ1：动作判断

Jev 是否能在 `dependency`、`configure`、`build`、`escalate_agent` 中选择由真实 outcome 支持的最低成本安全动作？

假设 H1：evaluation 上精确最优动作至少 `12/15`，且每个构建系统至少 `4/5`；所选动作安全率至少 `14/15`。

### RQ2：选择性执行与校准

仅使用 calibration 项目族拟合的安全概率和阈值，能否在 evaluation 上达到至少 30% 的 direct route coverage，并把错误 direct action 率控制在 10% 以内？

假设 H2：calibrated Jev 的 direct route coverage 至少 `14/45`，错误 direct action 率不超过 `0.10`。

### RQ3：联合路由增量

将 Jev 动作判断与确定性 BudgetFit 组合后，是否比 RuleGate 明显更准确，并相对 TF-IDF+BudgetFit 在 route/action joint accuracy 或同风险 direct coverage 上产生实质增量？

假设 H3：Jev+BudgetFit 至少达到 `32/45` joint correct，比 RuleGate 的 `27/45` 高 5 个决策；同时相对 TF-IDF+BudgetFit 满足第 10 节定义的增量门槛。

### RQ4：顺序稳定性

正序与逆序动作 criteria 是否在同一状态上给出一致 top-1？

假设 H4：evaluation 顺序一致至少 `14/15`；不一致状态必须拒绝 direct。

## 4. 数据与项目族隔离

数据只读绑定父报告及其 inventory canonical SHA-256：

`2e4209fb52c07af949789ae7880db478f5a6d9326b4496de7fcff45ad64da9e9`

项目角色按父 source pool 中每种构建系统的冻结顺序机械划分，不依据动作标签、基线错误或 Jev 结果选择：

| 构建系统 | Calibration family | Evaluation family |
| --- | --- | --- |
| CMake | `github.com/p-ranav/argparse` | `github.com/neargye/magic_enum` |
| Make | `github.com/kgabis/parson` | `github.com/antirez/sds` |
| Autotools | `github.com/troglobit/libuev` | `github.com/ivmai/libatomic_ops` |

每个 family 有 5 个状态，因此 calibration 和 evaluation 各包含 15 个状态。每个状态对应 `critical`、`local_only`、`agent_capable` 三个预算 profile，形成各 45 个 route decisions。

本实验不另设 Provider design split。问题 schema、action description、输入字段和响应解析必须在任何真实请求前通过 mock/fixture 冻结。Calibration 可拟合概率和选择阈值，但不得修改 prompt、字段、动作描述或模型版本；evaluation 只执行和分析一次。

## 5. Jev 输入与 Choice 合同

### 5.1 固定模型与请求

- 模型：`jev-1.13.0`，禁止 alias；
- API：`POST /v1/systemone`；
- SDK：继承已审计版本，`max_retries=0`，timeout 30 秒；
- 每个状态恰好一个物理请求；
- 同一请求包含正序和逆序两个语义相同的 Choice；
- 响应 `model` 必须精确为 `jev-1.13.0`；
- 保存完整 probabilities、confidence、request ID、usage、latency 和响应模型版本；
- 原始响应先 create-once 落盘，再做语义校验。

概率必须逐项有限且位于 `[0,1]`。原始概率和须满足 `abs(sum - 1) <= 0.005`，随后按原始和归一化用于指标和校准。Choice 与概率最大项必须一致；confidence 只校验官方公式，不直接作为安全概率。

### 5.2 Provider state

发送字段：

- `build_system`；
- `phase_facts`；
- `progress_facts`；
- 原文 `semantic_failure_log`。

不得发送：

- `state_id`、project ID、project family、commit、fault 名称或 fault index；
- hidden fault mapping、最优动作、安全动作集合或 route label；
- bound commands、动作执行结果、动作成本或预算 profile；
- 父基线预测和任何 evaluation 统计。

预算不进入 Jev。精确计数、可行性判断和 route 决策由代码负责，避免要求 Jev 做算术或把 BudgetFit 能力误算为模型能力。

### 5.3 动作 Choice

固定动作顺序：

`dependency -> configure -> build -> escalate_agent`

敏感性顺序为完全逆序。动作说明继承已验证语义：

- `dependency`：执行已绑定的输入或依赖恢复动作，再继续严格验证；
- `configure`：重新生成损坏或过期的构建系统状态，再继续严格验证；
- `build`：不改变依赖或配置，执行已绑定的正常构建动作；
- `escalate_agent`：当前证据不足以安全支持单一直接动作，升级完整 Agent。

instructions 要求选择最可能以最低动作成本到达严格终点的单一动作，禁止生成命令、参数或解释。正反顺序 top-1 不一致时，该状态标记为 abstain，不能 direct。

## 6. 标签与校准

### 6.1 动作标签

父 outcome matrix 定义：

- `safe_actions`：两次重复均达到严格终点的动作；
- `optimal_action`：安全动作中冻结成本最低者；
- `optimal_route`：由安全动作和 matched budget feasibility 派生的 direct、escalate_agent 或 stop。

父阶段的 `escalate_agent` 由零 Provider surrogate 验证动作空间。该标签表示“局部动作不足且具备 Agent reservation”，不表示真实 Agent 一定成功。

### 6.2 Platt scaling

Calibration 的每个状态为三个 local actions 产生一行：

- 输入：`logit(Jev probability[action])`；
- 标签：该 action 是否属于 `safe_actions`；
- 共 `15 x 3 = 45` 行；
- 模型：`LogisticRegression(C=1.0, solver="liblinear", random_state=459, max_iter=1000)`。

只校准 local action 的安全概率。`escalate_agent` 不作为 direct executor，不拟合 direct safety probability。

### 6.3 阈值选择

Calibration 候选必须同时满足：

- 正反顺序 top-1 一致；
- top-1 为 local action；
- 该动作具有可计算的 calibrated safe probability。

在全部唯一 calibrated probability 中选择能够保持 **0 个 observed unsafe direct action** 且覆盖状态最多的阈值；覆盖相同取更高阈值。阈值门禁要求至少覆盖 `5/15` calibration states，并且三个构建系统各至少覆盖 1 个状态。未达到时停止，不执行 evaluation。

原始概率基线使用相同候选、相同零错误最大覆盖规则，在 calibration 上独立选择 raw threshold；evaluation 后不得调整任何阈值。

## 7. 确定性 BudgetFit

对每个状态的三个 matched budget profile，按以下顺序计算路由：

1. 若正反顺序一致、Jev top-1 是 local action、calibrated safe probability 达阈值，且父报告中的剩余预算能够容纳该动作及严格 closure，则 route=`direct`；
2. 否则若 top-1 为 `escalate_agent` 或 direct 被拒，并且冻结 Agent reservation 可行，则 route=`escalate_agent`；
3. 其他情况 route=`stop`。

BudgetFit 只读取父报告中冻结的动作成本、planned charge 和 remaining budget，不读取标签决定当前预测。每次预测后再与 `optimal_route` 和 `optimal_action` 比较。

本离线实验中的 Jev 请求是被测分类器开销，不回填或改写父 benchmark 的 continuation budget。因此 route 指标评价的是“取得 Jev 响应后的动作/升级/停止选择”。Provider 请求、token、费用和延迟单独报告；任何端到端成本节省主张必须在后续 controller 实验中把 Jev 开销计入共同预算。

## 8. 比较对象

1. `RuleGate`：父报告冻结预测；evaluation 为 `27/45` joint correct、30 个 direct、18 个错误 direct；
2. `TF-IDF+BudgetFit`：父报告的项目族隔离预测；evaluation 为 `39/45` joint correct、18 个 direct、0 个错误 direct，每个构建系统 `13/15`；
3. `JevRaw+BudgetFit`：使用 calibration 上冻结的 raw probability threshold；
4. `JevCalibrated+BudgetFit`：使用 Platt safe probability 和冻结阈值；
5. `OracleBudgetFit`：只作为 ceiling，evaluation 最优路由为 direct `24`、escalate_agent `3`、stop `18`，不作为可部署基线。

不新增通用 LLM baseline。当前问题是 Jev 是否相对零 Provider 基线提供增量；引入另一付费模型会扩大预算和研究问题，留待 Jev 先通过资格后再决定。

## 9. 指标

### 9.1 动作判断

- exact optimal-action top-1 accuracy；
- safe-action accuracy；
- Macro-F1 和分动作 F1；
- multiclass Brier score；
- 5-bin ECE；
- action cost regret；
- 正反顺序一致率；
- 按构建系统分层结果。

### 9.2 校准与路由

- binary safe-action Brier 和 ECE，分别报告 raw 与 calibrated；
- risk-coverage curve；
- direct route coverage；
- wrong-direct count 与 wrong-direct risk；
- route/action joint accuracy：route 必须匹配；route 为 direct 时 action 也必须匹配 `optimal_action`；
- escalate_agent、stop 的 precision/recall 与混淆矩阵；
- 相对 RuleGate 和 TF-IDF+BudgetFit 的 joint accuracy 与 coverage 差值。

### 9.3 Provider 与完整性

- physical requests、有效响应、request ID 唯一性；
- input/output tokens、费用；
- mean/median/p95 latency；
- transport/API/schema/model-version failure；
- credential、Authorization header 和历史 evidence 修改均为 0；
- create-once marker、inventory 和 cleanup 完整性。

比例报告 Wilson 95% 区间，但 3 个 evaluation families 不支持显著性、总体泛化或模型排名声明。

## 10. 资格门槛与决定

### 10.1 Calibration 门槛

- 15/15 请求和响应生命周期闭合；
- 固定模型、概率、Choice、usage 和泄漏审计全部通过；
- Platt 数据同时包含正负标签；
- 零 observed unsafe direct 的阈值覆盖至少 `5/15`，且三系统各至少 1 个。

失败决定：`stop_before_progress_budget_evaluation`，不执行 evaluation。

### 10.2 Evaluation 核心门槛

- 15/15 固定模型有效响应；
- exact optimal action 至少 `12/15`，每系统至少 `4/5`；
- safe action 至少 `14/15`；
- 正反顺序一致至少 `14/15`；
- calibrated direct route coverage 至少 `14/45`；
- wrong-direct risk 不超过 `0.10`；
- route/action joint accuracy 至少 `32/45`，即相对 RuleGate 至少增加 5 个正确决策。

任一失败决定：`stop_jev_progress_budget_routing_before_controller`。

### 10.3 Jev 增量门槛

在核心门槛全部通过后，还必须相对 TF-IDF+BudgetFit 满足：

- 每个构建系统 joint correct 不低于 `13/15`；并且
- 以下至少一项成立：
  - 总 joint correct 至少 `42/45`，比 TF-IDF 增加 3 个；
  - 在 wrong-direct risk 不超过 `0.10` 时，direct coverage 至少 `21/45`，比 TF-IDF 增加 3 个，同时总 joint correct 不低于 `39/45`。

核心通过但增量门槛失败，决定为 `stop_jev_as_incremental_component_keep_semantic_budget_method`：保留 benchmark、BudgetFit 和轻量路由方向，不进入 Jev controller。

全部通过，决定为 `proceed_to_frozen_response_progress_budget_controller_replay_design`。该决定只授权下一阶段设计，不自动授权 controller 实现或新的 Provider 调用。

## 11. Provider 预算与失败处理

未来 authorized identity 的上限：

- Calibration：15 个物理请求；
- Evaluation：15 个物理请求；
- 总物理请求：30；
- 最大 input tokens：200,000；
- 最大 output tokens：50,000；
- 按 `$42 / 10^9` input tokens 计，最大模型费用：`$0.0084`；
- SDK retry：0；
- 单请求 timeout：30 秒。

Calibration 任一请求缺失、transport/API/schema/model-version 失败均停止在 evaluation 前。Evaluation 的单状态失败不得 retry、replacement 或 backfill；按固定 schedule 记录后续状态，但完整响应门槛必然失败。401/403、credential 异常或模型版本漂移立即全局停止。任何已发生请求的 usage 和费用必须保留，不能因语义校验失败而删除。

## 12. Evidence 与执行边界

实施阶段必须另行建立：

- candidate manifest、const schema、preregistration 和 runner；
- 父报告、inventory、split、模型输入和基线预测的哈希绑定；
- create-once attempt、逐请求 response/usage ledger、calibration、evaluation、terminal marker 和 inventory；
- credential presence/mode 检查、敏感信息扫描和零残留资源检查。

在读取 `jev-apikey.txt` 前，candidate 必须提交并推送，authorized amendment 必须绑定 exact revision、模型、30 请求、token/费用上限、停止规则和 evidence 路径，并获得明确授权。credential 值和 Authorization header 不得进入命令输出、日志、Issue、PR、evidence 或 Git。

所有 Issue #457 和更早 identity、报告、marker、inventory 与 raw evidence 永久只读。新 identity 不导入旧 Jev Provider response，不复用旧阈值，不对 evaluation 做结果后 prompt、split、阈值或标签修改。

## 13. 结论边界与下一交付

正向结果最多支持：在当前 6 个受控项目族和冻结状态上，Jev 的语义动作概率经独立项目族校准后，能与确定性预算门禁组合，并相对简单规则和强轻量基线表现出离线增量。

结果不能支持：

- 真实 Agent 升级一定成功；
- 端到端编译成功率非劣或 Provider 总成本下降；
- 动态预算 controller 已有效；
- 自然失败、开放世界、跨时间或更多构建系统泛化；
- Jev 相对所有通用 LLM 或分类器具有普遍优势。

本 spec 审查通过后的下一交付是 candidate plan、manifest、schema、preregistration、runner 和零 Provider mock/preflight。Provider calibration 需要独立 authorized identity，不由本 spec 自动启动。
