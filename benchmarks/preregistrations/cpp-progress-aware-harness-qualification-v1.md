# `cpp-progress-aware-harness-qualification-v1` 零 Provider 预注册

## 身份与目的

- Tracking Issue：#433；
- 分支：`yiwei/433-progress-aware-harness-qualification`；
- 类型：工程资格门禁；
- 目的：证明 Progress-aware Runtime v4 的结构化进展、上下文裁剪和动作门禁真实接线，并保持 Forge 严格终点；
- 研究效应：不估计 H1 对真实模型的成功率或成本效果。

## 允许的执行

- 读取 Issue #430 与 v5 的冻结 checkpoint、manifest、report 和 inventory；
- 创建独立 Compile Session 和独立 create-once evidence；
- 使用本地脚本模型驱动 LangGraph `create_agent()`；
- 使用冻结 Docker image 和 checkpoint，在断网 compile container 中执行有界命令；
- 运行 Runtime v3 CandidateVerifier、functional oracle、external evaluator、provenance 和 clean replay；
- 执行 cleanup、audit 和 report。

## 禁止的执行

- 不读取任何 credential；
- 不创建任何 Provider/Jev 请求；
- 不修改、续跑、补齐、replacement 或 backfill 历史 identity；
- 不把工程结果解释为模型、Harness treatment 或动态预算效果；
- 不在失败后覆盖 attempt、result、ledger 或 inventory。

## 唯一 attempt

Runner 使用 create-once marker。开始后无论成功、失败、异常或部分终结，该 identity 均封口；不得原地重跑。实现调试只能使用 pytest 临时目录或显式 `nonformal` 路径，不能写入正式 evidence root。

## 门槛

正式 gate 必须同时满足：

1. manifest、revision、component hash、父 inventory 和 Docker image identity 一致；
2. 全程 credential reads = 0、Provider requests = 0；
3. 脚本模型先在 candidate-ready frontier 请求额外 diagnostic，该调用被 H1 拒绝且没有 Docker side effect；
4. 下一轮模型从 progress snapshot 读取推荐 command ID 和 artifact mapping，成功调用 `submit_candidate_v1`；
5. CandidateVerifier 通过，external evaluator S0-S5 strict success，clean replay 通过；
6. evidence 中至少存在一次 progress snapshot、一次 context compaction、一次 ready guard rejection 和一次 accepted submit；
7. 所有预算计数守恒，Session 终结并 cleanup，受管容器为 0；
8. 冻结父 evidence 的 inventory hash 不变。

## 决定

- 全部门槛通过：`proceed_to_h0_h1_provider_comparison_design`；
- 任一门槛失败：`stop_before_h0_h1_provider_comparison`。

通过只授权设计和审查 Provider 比较，不自动授权 credential 读取或 Provider 调用。Provider 实验必须另行冻结身份、最大 18 arms、总 token/费用上限、顺序和停止规则。
