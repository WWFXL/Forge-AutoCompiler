# 未见项目族 H0/H1/H2 九臂 Provider Canary 设计

> 日期：2026-10-13
> Tracking Issue：[#447](https://github.com/WWFXL/Forge-AutoCompiler/issues/447)
> 工作类型：正式 canary 数据采集与工程资格

## 1. 目的

在 `tinyxml2`、`mjson`、`libcsv` 三个未见项目族上，让 H0/Runtime v3、H1/Runtime v4、H2/Runtime v5
各执行一次。Canary 只回答三臂在共同充分预算下能否形成可审计的真实 Provider 生命周期、完整计量、严格终点和
cleanup，并检查 H2 replay closure 是否被实际触发。

九个 observation 不进入 treatment effect、非劣、成本节省比例或成功率泛化估计。Strict success、Token、费用、
replay rejection 和墙钟只用于决定正式比较是否可执行及预算是否需要重新设计。

## 2. 三臂与执行顺序

- H0：`run_agent_workflow_node_v3`，原始受限 ReAct Agent；
- H1：`run_agent_workflow_node_v4`，进展感知结构化 Harness；
- H2：`run_agent_workflow_node_v5`，H1 加 pre-freeze replay closure。

三项目使用拉丁方顺序：

| 项目 | 顺序 |
| --- | --- |
| CMake `tinyxml2` | H0 -> H1 -> H2 |
| Make `mjson` | H1 -> H2 -> H0 |
| Autotools `libcsv` | H2 -> H0 -> H1 |

每个 arm 从 #445 已冻结并核验的 exact-commit source archive 新建独立 Session，不共享 workspace、artifact、模型上下文
或预算。源码挂载后断开容器网络，三臂使用相同 target、functional oracle、镜像和并行度。

## 3. Provider 与预算

固定 DeepSeek `deepseek-flash`，非流式、thinking 关闭、模型重试 0。每臂最多 36 requests、96 Agent steps、72 tool
calls、48 commands；600,000 recorded tokens 后不再发起下一请求，单响应上界 100,000，单臂授权上界 700,000。
node/evaluator/replay 为 1800 秒，command 900 秒，cleanup 120 秒。

九臂合计最多 324 requests、5,400,000 recorded-token 停止阈值、6,300,000 授权 recorded tokens。按冻结价格
input `$0.30/M`、output `$1.20/M` 取全部授权 Token 均为 output 的保守费用上界 `$7.56`。

## 4. 阶段与门禁

### Q0：零 Provider 身份资格

核对 #445 parent manifest、release、inventory 和三个 source archive；核对 Docker image、当前 release、三臂函数绑定和
零受管资源。Q0 创建 identity 与 result，但不读取 credential、不创建模型、不调用 Provider。

### Q1：九臂 Provider Canary

Q0 通过后才检查 `DEEPSEEK_API_KEY` 并串行执行九臂。每臂 create-once；已出现 attempt marker 但没有 result 时禁止 retry。
每个结果保留 Agent node result、request lifecycle、完整 usage、费用、预算守恒、外部 S0-S5、动作后 Session 状态、
Harness instrumentation、Session evidence 和 cleanup 结果。

Canary 通过要求：

1. 9/9 arm 均得到允许的分类终态，且没有 infrastructure error；
2. request started/terminal 一一闭合，usage 与 node/budget 一致，无 usage incomplete 或预算合同违反；
3. source、manifest、release、image、target 和动作后观察绑定完整，9/9 cleanup 成功；
4. H0 无 progress/compaction/closure 事件，H1/H2 每个已完成请求均有 progress 与 compaction；
5. H0/H1 无 replay-closure 事件，H2 至少实际执行一次 replay closure；
6. 每个 treatment 至少一个 candidate 进入完整六层外部 evaluator，证明对应终点链路被实际覆盖；
7. 整批 request、Token 和费用不超过授权上界。

任一硬门禁失败，决定为 `stop_before_unseen_three_arm_formal_comparison`。全部通过才允许
`proceed_to_unseen_three_arm_formal_comparison_design`。

## 5. 解释边界

Canary 通过只证明正式比较可执行；不证明 H0 增加预算会提高成功率，不证明 H1 或 H2 优于其他臂，也不证明 replay
closure 改善总体成功率或成本。若进入正式阶段，将新建独立 identity，冻结每项目每臂两次的 18-arm schedule、正式 estimand
和判据；canary 数值不并入正式估计。
