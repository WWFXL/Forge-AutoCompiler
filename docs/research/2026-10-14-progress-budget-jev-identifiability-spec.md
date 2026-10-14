# 进展预算感知 Jev 联合 benchmark 可辨识性规格

## 1. 阶段定位

本阶段建立一个零 Provider、真实执行的资格 benchmark，判断新的联合机制是否具备进入 Jev 校准和控制器实现的可辨识空间。它不是模型效果实验，也不把固定阈值、预算计数或 clean replay 单独主张为研究创新。

联合机制的候选数据流为：

```text
权威构建状态与有限失败日志
-> 代码枚举的类型化动作
-> 语义动作判断
-> 进展/预算策略选择 direct、escalate_agent 或 stop
-> 动作后重新观察
-> 严格 verifier 与 pre-freeze replay closure
-> 成功、拒绝后有界恢复或停止
```

H1 结构化 Harness 是共同执行基础；H2 replay closure 是共同安全终点；Jev 负责闭集语义判断；预算策略决定是否把剩余资源用于局部动作、Agent 升级或停止。后续主张必须验证这四部分的组合，不能直接合并历史实验结论。

## 2. 研究问题

1. 在 CMake、Make、Autotools 的未见项目族上，相同 coarse phase 是否存在需要 `dependency`、`configure`、`build` 或 `escalate_agent` 的不同状态？
2. 同一语义状态在不同六维剩余预算下，最优路由是否会在 `direct`、`escalate_agent` 和 `stop` 之间改变？
3. 当前工作区成功但 recipe 不闭合的状态能否被 clean replay 拒绝，并由一个受限动作恢复？
4. 只读 phase/budget 的 RuleGate 和只读日志的轻量文本分类器是否仍会饱和任务？

## 3. 状态、动作与路由

每个项目建立五个状态：缺少真实编译输入、损坏生成构建状态、错误目标、复合恢复以及 replay recipe 缺口。前四个状态共享 `build_attempted=true`、`build_succeeded=false`；复合恢复与单一构建状态损坏保留相同末次构建错误，但通过动作历史和进展事实区分。replay 缺口状态满足工作区 build、stage 和 functional oracle 已通过，但 `replay_closure_ready=false`。

候选动作始终为 `dependency`、`configure`、`build`、`escalate_agent`。所有命令由代码预绑定，模型不得生成 Shell 或参数。`escalate_agent` 在本阶段由确定性零 Provider surrogate 执行，仅验证动作空间和预算语义，不代表真实 Agent 能力。

每个语义状态派生三个 matched budget profile：

- `critical`：只保留一个 build execution，无法同时执行修复和严格 closure；
- `local_only`：允许本地动作和严格 closure，但没有 Provider 预算；
- `agent_capable`：在本地预算外预留 12 requests、150,000 input tokens、15,000 output tokens 和 60,000 microusd 的 Agent 容量。

路由标签先由两次真实 action branch 的严格结果确定安全动作，再按预算可行性和冻结成本选择：安全 direct 优先；没有安全 direct 且 Agent 预算充分时升级；否则停止。Agent 预算是规划 reservation，不伪装成本阶段的实际 Provider 用量。

## 4. 严格结果与进展记录

每个 action branch 都从同一 checkpoint 副本开始，记录动作前状态、动作结果、continuation、动作后状态、wall clock 和 build execution 增量。成功必须经过产物结构、functional oracle、exact-commit provenance 和 clean replay。

replay recipe 缺口使用未记录的生成头文件或编译器 wrapper 制造：当前工作区可完成 build 和 oracle，但 clean source 缺少生成步骤。pre-action closure 必须拒绝；`dependency` 动作把生成步骤加入 recipe 后，新的 clean replay 必须通过。验证器和 oracle 不因 treatment 放宽。

## 5. 资格判据

通过要求：

- 6 个项目、30 个语义状态、240 个 action branches、90 个 matched budget decision 全部有界终结；
- reference closure、重复一致性、预算守恒、动作后观察和 cleanup 通过；
- 三个构建系统均出现四类最优动作以及 direct/escalate/stop 三种路由；
- RuleGate route accuracy 严格低于 75%；
- 日志 TF-IDF/逻辑回归加预算可行性门禁的 route accuracy 严格低于 95%；
- 每个语义状态至少因一个预算变化改变路由；
- 12/12 pre-action replay closure 被拒，12/12 `dependency` recovery branch 通过严格 closure；
- 0 credential、0 Provider/Jev/Agent、0 model token，历史 evidence 保持只读。

任一门槛失败即决定 `stop_before_jev_calibration_and_controller_implementation`。全部通过才允许设计独立 Provider calibration；本 identity 不能续跑、替换或结果后调整阈值。

## 6. 结论边界

通过只说明 benchmark 能区分语义动作、预算路由和 replay recovery，且简单基线未完全饱和；不说明 Jev 已有效、动态预算提高成功率、Agent reservation 合理或端到端控制器有 treatment effect。失败评价的是该 benchmark 与联合问题的可辨识性，不直接否定 Jev、预算控制或 H2 工程价值。
