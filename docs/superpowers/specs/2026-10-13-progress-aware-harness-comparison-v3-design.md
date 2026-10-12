# 进展感知结构化 Harness H0/H1 v3 确认性复现设计

> 日期：2026-10-13  
> Tracking Issue：[#438](https://github.com/WWFXL/Forge-AutoCompiler/issues/438)  
> 工作类型：结果观察后的确认性复现设计与零 Provider 基础设施门禁

## 1. 研究问题

`cpp-progress-aware-harness-comparison-v2` 在 9 个项目、27 个配对上观察到 H1 相对 H0 更高的严格成功率和更低的 Provider 成本，但 8 个 H0 arm 的最后一次已完成响应没有进入权威 node usage，触发预注册的预算完整性硬门禁。v2 的正式决定因此保持为 `stop_progress_aware_harness_as_primary_mechanism`。

Issue #436 已修复该工程缺陷。v3 要回答的唯一问题是：在新预算语义和未进入 v2 H0/H1 arms 的 checkpoint 上，v2 的进展感知结构化 Harness 正向信号能否复现。

## 2. 复现类型与样本

v3 是 **post-observation、同项目族、跨状态深度的确认性复现**。设计时已经知道 v2 的结果，因此不得把 v3 描述为首次盲验证。

- 保留 v2 的 9 个 exact-commit 项目族、三种构建系统和三次重复，以控制项目与源码差异。
- 不复用 v2 Q1/Q2 的 12 个 H0/H1 effect checkpoint。
- 对每个正式任务应用冻结的深度变换：`state-1 -> state-3`、`state-2 -> state-1`、`state-3 -> state-2`。
- 新正式 checkpoint 为 CMake、Make、Autotools 各 3 个，且每个构建系统继续覆盖 state 1、2、3。
- Q1 canary 使用 `cmake-cli11-state-3`、`make-tiny-aes-c-state-3`、`autotools-libfastjson-state-3`，也不进入正式估计。
- 所有 checkpoint 已在 `cpp-dynamic-budget-trajectory-benchmark-qualification-v5` 中通过双重复、恢复、预算守恒和 successor 等价资格。

该设计增强的是同项目内跨进展深度的复现性，不能支持未见项目族、自然失败或开放世界泛化。Issue #430 已观察过这些项目上的固定 Agent continuation；checkpoint 选择只由 v2 深度和机械变换决定，历史 outcome 不参与选择，也不进入 v3 effect estimate。

## 3. Treatment 与唯一机制变化

- H0：Runtime v3 的原始受限 ReAct Agent。
- H1：Runtime v4 的进展感知结构化 Harness，包括权威 progress snapshot、最近交互裁剪、candidate-ready guard、无进展诊断熔断和 replay command 建议。
- 两臂共享模型、checkpoint、初始预算、工具、命令权限、CandidateVerifier、functional oracle、provenance、clean replay、evaluator 和 cleanup。

Treatment 定义不变。相对 v2 的工程变化仅为 Issue #436 的 Token 后付费计量语义；相对 v2 的采样变化仅为机械选择新的 checkpoint 深度。不得加入 Jev、动态预算 controller、额外修复反馈或新的 Agent 工具。

## 4. Token 与费用合同

每臂冻结：

- 下一请求停止阈值 `T = 300,000` recorded tokens；
- 单响应声明上界 `R = 100,000` recorded tokens；
- 派生单臂授权上界 `T + R = 400,000`；
- 24 次模型请求、64 Agent steps、48 工具调用、32 条命令；
- node 1800 秒、单命令 900 秒、evaluator/replay 1800 秒、cleanup 120 秒。

v2 的 538 个 Q2 已完成响应中，单响应最大值为 60,594 tokens。`R=100,000` 是在已观察 v2 后冻结的保守上界，不是效果结果。若响应超过 R，实际 usage 和费用仍完整记录，arm 分类为 `budget_contract_violation`，v3 整体失败。

60 个 Provider arms 包含 6 个 canary arms 和 54 个正式 arms。总体上限为 1,440 次请求、18,000,000 Token 停止阈值总和、24,000,000 Token 授权上界。按冻结的最高输出单价 `$1.20 / 1M tokens`，Provider 费用授权上界为 `$28.80`。

## 5. 阶段、指标与停止规则

1. Q0：9 个新正式 checkpoint 的零 Provider reference closure，要求 `9/9` strict。
2. Q1：三种构建系统各一个 H0/H1 canary，要求 `6/6` arms 分类、计量、treatment separation 和 cleanup 闭合；canary 不进入效果估计。
3. Q2：27 个配对、54 个正式 arms。每个项目三个重复，臂顺序按冻结 schedule 交替。

主要判据保持 v2 原值：H1-H0 strict success 的 task-cluster 单侧 95% bootstrap 下界不低于 `-0.10`，同时 H1 Provider cost 至少降低 20%。每个构建系统不得出现 H1 strict 计数低于 H0。替代路径仍要求 strict success 下界大于 0、成功率至少提高 10 个百分点，且费用增幅不超过 10%。

任一硬门禁失败即停止并保留全部失败或部分 observation：

- events、tracker、node result、报告 Token 或费用不一致；
- 请求 started/completed/failed/incomplete 生命周期不守恒；
- 单响应超过 R、usage 缺失或非法；
- checkpoint/source/parent 绑定漂移；
- 严格终点、动作后观察、离线 replay 或 cleanup 不闭合；
- infrastructure error、replacement、backfill 或结果后阈值修改。

## 6. 当前 candidate 边界

本阶段只创建 `cpp-progress-aware-harness-comparison-v3-candidate`。候选授权为 0 credential read、0 Provider、0 model token、0 Docker、0 formal attempt、0 evidence write。candidate 只允许生成、验证和展示计划；Q0/Q1/Q2 必须由后续独立 authorized identity 和 runner 开放。

candidate 门禁通过只说明设计完整、样本关系和预算合同可静态审计，不说明 H1 有效。正式运行必须由研究负责人在审阅本设计后单独授权。
