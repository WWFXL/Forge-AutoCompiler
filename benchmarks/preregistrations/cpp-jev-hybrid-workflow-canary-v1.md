# Workflow + Jev + Agent 混合链路 Provider canary v1 预注册

日期：2026-10-11。追踪：Issue #409。身份：`cpp-jev-hybrid-workflow-canary-v1`。

## 研究问题

在零 Provider qualification v3 已证明工程链路闭合后，真实 Jev `jev-1.13.0` 与真实 `deepseek-flash` Compiler Agent 能否接入同一混合协调器，并在 CMake、Make、Autotools 三类受控失败中保持请求预算、控制权交还、严格 S0-S5 终点和 cleanup？

该阶段是 Provider canary，不估计自然失败总体成功率或成本收益。

## 固定 Case 与路由

- CMake `args@fe4450b`：注入无效 build state，真实 Jev 在闭集动作中决策，满足门禁时直接执行。
- Make `hoextdown@1ef9a71`：注入错误 target；仍执行一次真实 Jev 请求，但所有直接候选的代码前置条件固定为 false，保证进入一次真实 Agent handoff。
- Autotools `c-ares@589b588`：删除编译输入，真实 Jev 在闭集动作中决策，满足门禁时直接执行。

Jev 不生成 Shell。直接命令来自冻结 task contract。Agent 只能通过现有 Candidate Service 提交，返回后 Workflow 必须重新观察；Jev、直接 executor 和 Agent 的自报成功均不能替代 S0-S5 evaluator。

## Provider 与预算

- Jev：`jev-1.13.0`，最多 3 请求，0 retry，30 秒单请求超时；总 input tokens 不超过 60,000，总费用不超过 `$0.00252`。
- Agent：`deepseek-flash`，每 case 最多 24 请求、300,000 recorded tokens、64 steps、48 tool calls、32 commands；总计不超过 72 请求和 900,000 recorded tokens，0 retry。
- 混合协调器：每 case 最多 2 cycles、1 直接动作、1 Agent handoff、3600 秒墙钟。
- 三个 formal attempt，各 case 恰好一次；不 retry、replacement 或 backfill。
- case 失败在 cleanup 和总预算仍有效时保留并继续，以观察三种构建系统；identity、预算、cleanup 或受管资源异常立即停止整个 batch。

## 通过门槛

以下条件必须同时成立：

- 三个 case 都有真实 Jev 响应及完整 usage；
- 至少一次真实 Agent handoff，且 handoff 后 Workflow 至少再观察一次；
- 三个 case 全部通过同一个 S0-S5 严格终点；
- 三个 case cleanup 均成功，结束后受管资源为 0；
- 总 Provider 使用不超过冻结预算；
- qualification、父 manifest/report 和实现组件哈希没有漂移。

全部通过时决定为 `proceed_to_natural_failure_evaluation_design`。任一门槛失败时决定为 `stop_and_repair_hybrid_workflow`。

## 结论边界

三个项目和故障均来自既往资格数据，Make case 还人为禁用直接执行以保证 handoff。因此 canary 通过只能证明真实 Provider 接线、控制权交还、严格终点、预算和 cleanup 闭合；不能说明自然失败成功率非劣、成本下降、Jev 相对基线优势、模型排名、未见项目泛化或动态预算有效。
