# Jev 三臂端到端 canary v5

- Tracking Issue：[#406](https://github.com/WWFXL/Forge-AutoCompiler/issues/406)
- Identity：`cpp-jev-end-to-end-canary-v5`
- Implementation revision：`0618739b231223c75ee7b66802795e8063bf92bd`
- Manifest canonical SHA-256：`29f6ec39cd442e6fc0606dc02321dc758f5eb6a7c621428beb9d14ef76409081`

## 研究问题

在三个受控、已知可恢复的 CMake/Make/Autotools 失败状态上，`AlwaysAgent`、`RuleGate+Agent` 和 `JevGate+Agent` 能否在相同完整 Agent 预算与同一严格 evaluator 下形成闭合终态，并完整记录 Agent 调用、Jev 调用、token、墙钟、升级与严格成功？

本阶段是 canary，只评价运行闭合、指标可采集性和预算可接受性，不估计 treatment effect。

v1 在零 Provider qualification 启动时因父 manifest 常量名错误而在 Docker 动作前失败。
v2 修正常量后通过零 Provider qualification，但 formal sequence 1 在创建 Compile Session
前因本机默认 `/workspace/.compile-sessions` 不可写而停止。两个失败 identity 均为 0 Provider、
0 model token；v2 创建了 1 个 formal attempt marker/result，但未创建 Session。v3 修复 workspace
绑定后完成 9/9 arm 和 cleanup，但 runner 在宿主修改 root-owned 源码，并且未把实验允许的构建
系统写回 session，导致 0 次 Agent 请求和 0/9 strict success。v4 将故障变异移入容器，通过
冻结策略选择 authoritative build system，并把真实 Compile Session 的完整严格链路加入零
Provider qualification；args 与 hoextdown 均严格成功，但 c-ares 的 `make install` 被 post-build
策略识别为新的 build 命令并拒绝。v5 唯一修复是把 c-ares staging 冻结为明确的 `mkdir/cp`
动作。v5 使用全新 identity 和 evidence root，不导入、续跑或改写 v1-v4。

## 样本与顺序

- `args` / CMake / `invalid_build_state` / 预期 `configure`
- `hoextdown` / Make / `wrong_build_target` / 预期 `build`
- `c-ares` / Autotools / `missing_compile_input` / 预期 `dependency`

固定顺序：

1. `args` / `always_agent`
2. `args` / `rule_gate_agent`
3. `args` / `jev_gate_agent`
4. `hoextdown` / `rule_gate_agent`
5. `hoextdown` / `jev_gate_agent`
6. `hoextdown` / `always_agent`
7. `c-ares` / `jev_gate_agent`
8. `c-ares` / `always_agent`
9. `c-ares` / `rule_gate_agent`

三个项目和故障已进入先前 Jev 资格数据，因此本 canary 不支持未见项目泛化；复用只服务于确认端到端接线。

## 三臂

- `always_agent`：故障状态直接升级完整 Agent。
- `rule_gate_agent`：固定选择 `build`；动作失败时升级完整 Agent，动作成功时由确定性 continuation 和同一 evaluator 收口。
- `jev_gate_agent`：Jev 以正序/逆序 Choice 判断动作，经冻结 Platt 门禁后直接执行或升级 Agent；动作失败时升级完整 Agent。

直接动作只执行代码绑定命令，不能生成 Shell，也不能宣告成功。所有候选必须经过 CandidateVerifier、functional oracle、provenance 和 clean replay。

## 固定预算

- 每 arm Agent：最多 24 请求、300000 tokens、1800 秒；
- 全阶段 Agent：最多 216 请求、2700000 tokens；
- Jev：3 请求、最多 60000 input tokens、`$0.00252`；
- Provider retry 均为 0；不存在 replacement 或 backfill。

## 停止规则与结论

identity/evidence 损坏、预算越界、cleanup/orphan 失败立即停止整个 batch。Provider、模型行为、无候选或严格验证失败保留为 arm outcome，并在资源闭合时继续后续 arm。

9 个 arm 均产生可分类终态、指标完整、无预算越界、无历史 evidence 修改且无受管资源残留时，决定 `proceed_to_formal_end_to_end_comparison_design`。否则决定 `stop_and_repair_canary_infrastructure` 或 `stop_before_formal_comparison`。

## 解释边界

Canary 结果不能支持成功率非劣、成本下降、显著性、模型排名、自然失败泛化或动态预算优越性。正式比较必须使用新的未见项目族和独立 identity。
