# 动态预算多步轨迹 benchmark 资格结果

**决定：`stop_before_agent_continuation_and_controller_implementation`。**

状态：`failed`。本 identity 有 20 个状态记录了 continuation，共记录 40 个禁网 Docker continuation；完整项目和状态分别为 6、20。

## 核心结果

- 已记录成功 continuation：`40/40`；
- 重复一致的完整状态：`20/20`；
- 完整状态 checkpoint 绑定：`20/20`；
- 完整状态预算守恒：`20/20`；
- stop reservation 转移：`2/3`；
- Provider requests：`0`；Agent calls：`0`；
- 已记录 continuation 累计动作 wall clock：`70253 ms`。

## 资格门槛

| 门槛 | 通过 |
| --- | --- |
| `budget_conservation` | 否 |
| `checkpoint_binding` | 否 |
| `clean_continuations` | 否 |
| `cleanup` | 是 |
| `multistep_coverage` | 否 |
| `post_action_observation` | 否 |
| `project_coverage` | 否 |
| `repetition_consistency` | 否 |
| `stop_transfer` | 否 |

## 停止原因

- 分类：`checkpoint_restore_infrastructure_failure`；
- 类型：`LinkOutsideDestinationError`；
- 观察：'src/.libs/libestr.la' would link to '/home/yiwei/work/Forge-AutoCompiler/.compile-sessions/benchmark-evidence-dynamic-budget-trajectory-qualification-v4/states/autotools-libestr-state-3/repetition-1/libestr.la', which is outside the destination。

## 解释边界

本结果只评价轨迹 benchmark 的恢复、重复性、计量与共享预算语义。它不评价动态预算 controller、Jev 或 Agent 的效果，也不支持自然失败或开放世界外推。

当前 identity 已停止。下一步先通过独立的 symlink-safe checkpoint restore 工程门禁，再冻结全新的轨迹资格 identity；不得续跑或补齐当前 evidence。

## Evidence

- Manifest SHA-256：`b127471382146e9bf0dec100a437bffdc715068e2c87976b5c42a6357c6b5b23`；
- Manifest canonical SHA-256：`189b62acbfa844af3bd63886de0aa97570de6847261e64a45c6f49a98699c589`；
- Evidence inventory canonical SHA-256：`e398003b48a2ded0b745900900481a21b2aa5879f3296ba71c06032f50e55294`；
- Evidence files：`1797`，`34453974` bytes。
