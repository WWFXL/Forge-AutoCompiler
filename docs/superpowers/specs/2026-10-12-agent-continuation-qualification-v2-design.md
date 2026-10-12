# 固定 Agent continuation 资格 v2 设计

## 研究问题

Issue #427 已证明 CMake、Make、Autotools 的 27 个多步 checkpoint 可恢复、可重复并可记录六维预算，但没有 Agent observation。Issue #430 要回答：从冻结 checkpoint 接管后，固定 Compiler Agent 能否稳定到达 Forge 严格终点，并形成完整、可比较的成本轨迹。

本阶段是资格数据采集，不比较 controller 效果。Jev、动态预算决策和自然失败均不进入运行链路。

## v2 工程修复

v1 的首个 Q0 case 中，reference configure/build/artifact-stage 与 functional oracle 实际均成功，但 CandidateVerifier 接收了 checkpoint 恢复后的旧内存 Session。oracle 保存 smoke 命令时覆盖了权威命令历史，使 external evaluator 在 S1 无法解析 candidate 引用。v2 在构造 CandidateService 前重新加载权威 Session，并要求回归证明 oracle 保存后四类命令仍完整。该修复不改变样本、reference recipe、Agent、预算、门槛或解释边界。

v1 identity、runner 和 252 文件 evidence 永久只读。v2 使用独立 create-once evidence，不续跑、不补齐、不 backfill v1。

## 三层门禁

### Q0：零 Provider strict closure

从 v5 的 27 个 checkpoint 中冻结 9 个，每种构建系统覆盖 state 1、2、3。Reference recipe 在独立 Compile Session 中恢复 checkpoint，重新执行形成完整 clean replay 所需的命令，并经过 Runtime v3 CandidateVerifier、系统 functional oracle、S0-S5 external evaluator、provenance 和 clean replay。

CLI11 与 cxxopts 是 header-only 项目，reference recipe 必须编译使用真实项目头文件的最小 consumer ELF。kilo 的交互式程序不适合稳定 smoke，reference recipe 将其项目源码编译为静态库，并用符号 oracle 检查。其他项目提交真实 ELF 或 `ar`。

Q0 必须 9/9 strict。失败时身份封口，Q1/Q2 在 credential 读取和模型创建前拒绝。

### Q1：三状态 Provider canary

CMake、Make、Autotools 各冻结一个不进入 Q2 统计的 checkpoint。每个 checkpoint 只运行一次固定 Agent。Canary 只验证模型接线、checkpoint 恢复、逐请求 token、动作后观察、候选评估、控制权回收和 cleanup；不估计成功率或方差。

Q1 必须 3/3 形成候选和 S0-S5 分类终态，成本完整且无基础设施错误。严格成功不是 Q1 的效果门槛。

### Q2：正式 Agent continuation qualification

9 个 checkpoint 各做 3 次独立 continuation，共 27 arms。每个 arm 使用独立 thread、Session、workspace、artifacts、candidate、evaluator 和 ledger。Agent 只接收 checkpoint 状态、目标合同和剩余预算，不接收 reference recipe 或 Q0 命令。

## 固定运行合同

- 模型：`deepseek-flash`，非 streaming，thinking 关闭，provider retry=0；
- 单臂：24 model requests、300,000 recorded tokens、64 agent steps、48 tool calls、32 commands、1,800 秒；
- Q1+Q2 总上限：720 requests、9,000,000 recorded tokens；
- 价格只用于冻结估算：input `$0.30/M`、output `$1.20/M`；
- 编译镜像：v5 的 exact image ID；checkpoint 恢复后断开 compile container 网络；
- strict endpoint：Runtime v3 CandidateVerifier + functional oracle + S0-S5 + clean replay；
- 任一 provider request 缺少 input/output token 时，成本完整性失败，不估算回填。

六维预算为 wall clock、provider requests、input tokens、output tokens、provider cost microusd 和 build executions。每个 arm 保存 parent checkpoint 的 `before`、本 arm 的 `delta` 和 `after`，并在 Agent 返回后从权威 Session 重新观察终态、命令和 artifacts。

## Q2 判定

硬门禁：27/27 分类终态、27/27 token 与六维预算完整、27/27 父 checkpoint 绑定、27/27 动作后观察、27/27 cleanup，且无跨 arm 写入或资源残留。

行为资格：

- 至少 6/9 checkpoint 在三次中 strict success `>=2/3`；
- 每种构建系统至少 2/3 checkpoint 达标；
- state 1、2、3 每个深度至少 2/3 checkpoint 达标；
- timeout 或 budget exhausted 不超过 3/27。

全部满足时决定为 `proceed_to_matched_outcome_matrix_design`。否则决定为 `stop_before_dynamic_budget_controller_implementation`。

## 证据边界

v1-v5 evidence 只读。Q0 是 reference 闭合门禁，Q1 是工程 canary，二者不进入 Q2 成功率分母。Q2 只能说明当前 9 个受控项目族、冻结 checkpoint、模型和预算下的 Agent continuation 资格，不能说明动态预算 controller、Jev、自然失败或开放世界效果。

