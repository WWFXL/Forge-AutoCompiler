# 进展预算感知 Jev 离线校准 candidate v1 预注册

## 身份与研究边界

- Candidate identity：`cpp-jev-progress-budget-calibration-candidate-v1`
- Tracking Issue：[#461](https://github.com/WWFXL/Forge-AutoCompiler/issues/461)
- Spec Issue：[#459](https://github.com/WWFXL/Forge-AutoCompiler/issues/459)
- Parent identity：`cpp-progress-budget-jev-identifiability-qualification-v1`
- 当前状态：`candidate_zero_provider`
- 工作类型：实验基础设施

本 candidate 冻结未来 Jev 离线校准实验的输入、Provider 合同、校准器、BudgetFit、门槛、预算和停止规则。本阶段不读取 credential 内容，不调用 Provider/Jev/Agent，不创建正式 attempt/evidence，不实现 controller，也不产生模型效果或端到端效果结论。

## 研究问题

父资格实验已证明 6 个项目族、30 个状态和 90 个 matched budget decisions 可以区分语义动作与预算路由。当前实验拟回答：

1. 固定版本 Jev 能否从确定性进展事实和真实失败日志中选择最低成本安全动作？
2. 仅在项目族隔离 calibration 上拟合的安全概率，能否在 evaluation 上支持低风险 direct？
3. Jev+BudgetFit 是否相对 RuleGate 和强轻量 TF-IDF+BudgetFit 基线提供实质增量？
4. 正序与逆序 Choice 是否足够稳定，能够支持 direct 门禁？

Jev 不负责计算预算，不生成 Shell 命令，不判断严格终点。直接动作与 Agent 路径在未来 controller 中仍必须通过 CandidateVerifier、functional oracle、provenance 和 clean replay。

## 父证据绑定

父证据只读绑定：

- 报告：`benchmarks/reports/cpp-progress-budget-jev-identifiability-qualification-v1.json`
- 报告文件 SHA-256：`1ec00e9d9940ccabce5740a085da52b2f2dc82973b9c1554f026b3abeb4c1ccc`
- Manifest canonical SHA-256：`fed83243b439df16e10b9ef1940b0158ba269a4c03799e706dd1e2dcb290bc76`
- Evidence inventory canonical SHA-256：`2e4209fb52c07af949789ae7880db478f5a6d9326b4496de7fcff45ad64da9e9`
- 父正式决定：`proceed_to_jev_progress_budget_calibration_design`

candidate runner 必须逐文件重新审计父 inventory。任何父文件、report、manifest、completed marker 或 inventory 漂移都停止，不允许重建或修改父 evidence。

## 项目族隔离

按父 source pool 中每种构建系统的冻结顺序机械划分：

| Build system | Calibration | Evaluation |
| --- | --- | --- |
| CMake | `github.com/p-ranav/argparse` | `github.com/neargye/magic_enum` |
| Make | `github.com/kgabis/parson` | `github.com/antirez/sds` |
| Autotools | `github.com/troglobit/libuev` | `github.com/ivmai/libatomic_ops` |

每侧 3 个项目族、15 个状态和 45 个 matched budget decisions。Calibration/evaluation 不共享项目族或状态。Evaluation 只分析一次，不允许结果后修改 prompt、模型、split、校准器、阈值、标签或门槛。

candidate manifest 分别固定两个 split 的 state、provider state、action label、budget decision、RuleGate 和 TF-IDF 行的 canonical SHA-256。父 action outcome 和 hidden fault mapping 只用于冻结标签审计，不进入 Provider state。

## Provider state 与 Choice

每个状态只向 Jev 发送：

- `build_system`
- `phase_facts`
- `progress_facts`
- 原文 `semantic_failure_log`

禁止发送 state/project/fault/commit identity、候选动作目录、绑定命令、action outcome/cost、safe/optimal label、预算 profile/remaining budget 和基线预测。

每个状态恰好一个物理请求；同一请求包含：

1. `next_action_primary`：`dependency -> configure -> build -> escalate_agent`
2. `next_action_order_sensitivity`：完全逆序

两题共享相同 state、instructions 和动作语义，只允许 criteria 顺序不同。正反顺序 top-1 不一致时必须拒绝 direct。Jev 只选择闭集动作，不生成命令、参数或解释。

## Provider 与响应合同

- Endpoint：`POST https://api.typesafe.ai/v1/systemone`
- SDK：`typesafe-sdk==0.7.3`
- Model：`jev-1.13.0`
- Timeout：30 秒
- SDK retry：`max_retries=0`
- SDK debug log：关闭
- Credential：未来只通过 `TYPESAFE_API_KEY` 注入

禁止 `jev-latest` 和 `jev-preview`。响应 `model` 必须精确等于请求模型。每个响应必须保存 request ID、usage、latency、模型版本、两题完整原始/归一化概率和 confidence；不得保存 raw credential 或 Authorization header。

四个概率必须有限且位于 `[0,1]`，key 必须完整，原始概率和满足 `abs(sum - 1) <= 0.005`。先完成该校验，再归一化用于指标和校准。Choice 必须是概率 argmax；confidence 按 `(p_max - 0.25) / 0.75` 复算，绝对容差为 `0.02`。

任何 transport、timeout、HTTP、schema、usage、概率或模型版本失败都保留已发生请求并停止相应批次。401/403、credential 异常和模型版本漂移立即全局停止。不得物理 retry、replacement 或 backfill。

## Calibration

Calibration 的 15 个状态分别为三个 local actions 产生一行，共 45 行：

- 输入：裁剪到 `[1e-6, 1-1e-6]` 后的 `logit(Jev probability[action])`
- 标签：该动作是否在父 `safe_actions` 中
- Estimator：`sklearn.linear_model.LogisticRegression`
- 参数：`C=1.0, solver="liblinear", random_state=459, max_iter=1000`

标签必须同时包含正负类。`escalate_agent` 不拟合 direct safety probability。

对顺序一致且 top-1 为 local action 的 calibration 状态，枚举观测到的唯一概率阈值，选择在 0 个 observed unsafe direct 下覆盖状态最多的阈值；覆盖并列选择更高阈值。Calibrated probability 与 raw probability 分别独立选择阈值。

Calibration 必须满足：

- 15/15 有效请求和响应闭合；
- Platt 数据同时有正负标签；
- calibrated threshold 覆盖至少 `5/15`；
- CMake、Make、Autotools 各至少覆盖 1 个状态；
- observed unsafe direct 为 0。

任一失败即决定 `stop_before_progress_budget_evaluation`，不执行 evaluation。

## BudgetFit

预算不进入 Jev。对每个状态的 `critical`、`local_only` 和 `agent_capable` 决策，代码按固定顺序路由：

1. 正反顺序一致、top-1 为 local action、calibrated safe probability 达阈值，且剩余预算容纳该动作及严格 closure，路由为 `direct`；
2. 否则若冻结 Agent reservation 可行，路由为 `escalate_agent`；
3. 否则路由为 `stop`。

预算 profile、direct charge 与 Agent reservation 原样绑定父 manifest。Jev 请求是本实验的分类器开销，不回填父 continuation budget。Provider 请求、token、费用和延迟单独报告；未来端到端实验必须把 Jev 开销纳入共同预算。

## 基线与冻结数值

Evaluation 冻结基线：

- RuleGate：`27/45` joint correct，30 direct，18 wrong direct；每个构建系统 `9/15`
- TF-IDF+BudgetFit：`39/45` joint correct，18 direct，0 wrong direct；每个构建系统 `13/15`
- OracleBudgetFit：24 direct、3 escalate_agent、18 stop

比较 `JevRaw+BudgetFit` 与 `JevCalibrated+BudgetFit`。不新增通用 LLM baseline；当前研究问题是 Jev 相对零 Provider 基线是否有增量。

## Evaluation 门槛

核心门槛全部通过才继续判断增量：

- 15/15 固定模型有效响应；
- exact optimal action 至少 `12/15`，每构建系统至少 `4/5`；
- safe action 至少 `14/15`；
- 正反顺序一致至少 `14/15`；
- calibrated direct decision coverage 至少 `14/45`；
- wrong-direct risk 不超过 `0.10`；
- route/action joint correct 至少 `32/45`。

任一失败的决定为 `stop_jev_progress_budget_routing_before_controller`。

核心通过后，三个构建系统 joint correct 均须至少 `13/15`，并至少满足：

- 总 joint correct 至少 `42/45`；或
- direct 至少 `21/45`、wrong-direct risk 不超过 `0.10`，且 joint correct 不低于 `39/45`。

增量失败的决定为 `stop_jev_as_incremental_component_keep_semantic_budget_method`：停止 Jev 组件，保留 benchmark、BudgetFit 和轻量路由方向。全部通过才记录 `proceed_to_frozen_response_progress_budget_controller_replay_design`，该决定只允许下一阶段设计，不授权 controller 或新 Provider 调用。

## 未来 Provider 预算

当前 candidate 不授权以下预算。未来 authorized identity 的硬上限为：

- Calibration：15 个物理请求
- Evaluation：15 个物理请求
- 总请求：30
- Input tokens：200,000
- Output tokens：50,000
- 按 `$42 / 10^9` input tokens 计的模型费用：`$0.0084`

candidate 必须先提交和推送。authorized amendment 必须绑定 exact Git revision、模型、预算、create-once evidence 路径、停止规则和本预注册，并获得独立执行授权。

## 当前权限边界

本 candidate 仅授权父证据只读审计、协议生成、mock HTTP/SDK、纯函数校准/BudgetFit 测试、credential presence/mode metadata 检查和零 Provider preflight。明确不授权：

- 读取 `jev-apikey.txt` 内容或 `TYPESAFE_API_KEY` 值；
- 调用 `/v1/models`、`/v1/systemone` 或完整 Agent；
- 创建 formal attempt 或写 Provider evidence；
- 实现 controller；
- 修改历史 evidence；
- 根据 evaluation 调整任何冻结设计。

本阶段通过只说明 candidate 协议与工程门禁闭合，不支持 Jev 判断准确、校准可迁移、动态预算有效、真实 Agent 升级成功、端到端成本下降或自然失败泛化。
