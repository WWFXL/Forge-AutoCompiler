# 动态预算多步轨迹 benchmark 零 Provider 资格预注册

本 identity 承接 Issue #421 的停止结论和 Issue #423。目标是判断新的跨构建系统轨迹 benchmark 是否具备可恢复 checkpoint、重复 continuation、逐动作六维预算和共享预算转移，不评价 controller 效果。

## 冻结设计

- Identity：`cpp-dynamic-budget-trajectory-benchmark-qualification-v1`。
- CMake、Make、Autotools 各 3 个固定 exact-commit 项目，每项目 3 个有序动作。
- 每个状态从同一 checkpoint 派生 2 个禁网 Docker continuation，共 27 个状态、54 个 continuation。
- 同一状态两次 continuation 必须 exit 0，且 successor observation、workspace tree、artifacts tree 和声明产物 hash 一致。
- direct 失败不能在同一 action 内升级或拼接 Agent。
- 六维预算逐状态记录 `before / delta / after`；Provider request、input/output token 和费用必须为 0。
- 每个构建系统一个共享预算 block。第三项目只能消费由固定 `stopped-reservation` 释放的 6 次 build executions 和 300 秒 allowance。
- evidence 只写入 `.compile-sessions/benchmark-evidence-dynamic-budget-trajectory-qualification-v1`，create-once，失败和部分结果均保留。

## 分析顺序

1. 校验 manifest、exact image、source identity、evidence absent 和零残留容器；
2. 按 `cmake -> make -> autotools`、各自 manifest 项目顺序串行执行；
3. 先检查项目/状态/checkpoint/continuation 完整性；
4. 再检查重复一致性与 direct 后 observation；
5. 再检查六维预算守恒和 stop reservation 转移；
6. 最后检查 cleanup，并产生唯一资格决定。

不得在看到结果后更换项目、命令、声明产物、阈值、预算或比较字段。未执行项目记为未观察，不填零，不 replacement 或 backfill。

## 决定

所有冻结门槛通过时：

`proceed_to_agent_continuation_qualification_design`

任一门槛失败时：

`stop_before_agent_continuation_and_controller_implementation`

通过只授权设计独立的 Agent continuation 资格，不自动授权 Provider，不自动实现动态预算 controller。

## 权限

用户已授权本阶段的实现、测试、Docker 零 Provider 采集、报告、提交、推送和 PR，直至得到关键结论。明确禁止 credential read、Jev/Agent/Provider request、模型 token、历史 evidence 修改和 controller 实现。
