# 固定 Agent continuation 资格 v2 结果

**决定：`stop_before_dynamic_budget_controller_implementation`。**

Q0 reference strict：`9/9`；Q1 classified candidate：`3/3`，strict：`2/3`。

## Q2 正式资格

- Strict success arms：`12/27`；
- 达标 checkpoint：`5/9`；
- 分构建系统达标：`{"autotools": 2, "cmake": 1, "make": 2}`；
- 分深度达标：`{"1": 3, "2": 1, "3": 1}`；
- timeout/budget exhausted：`6/27`；
- Provider requests：`311`；input/output tokens：`3797261/266407`；
- 估算 Provider 成本：`$1.458868`；累计 arm wall clock：`2276732 ms`。

## 门禁

- `classified_terminal`：通过
- `cleanup`：通过
- `cost_and_budget_complete`：失败
- `no_infrastructure_error`：通过
- `parent_checkpoint_binding`：通过
- `post_action_observation`：通过
- `checkpoint_stability`：失败
- `depth_coverage`：失败
- `system_coverage`：失败
- `timeout_budget_bound`：失败

## 解释边界

只评价冻结受控 checkpoint 上固定 Agent continuation 的稳定性、成本完整性和恢复性；不评价动态预算 controller、Jev、自然失败或开放世界。

## Evidence

- Manifest canonical SHA-256：`2714e79f2431633e6267fa21668ca23ab8495f480d08c39999317d6856d3be6c`；
- Inventory canonical SHA-256：`9d749bf76571429b3fb6e7e325e61c1168df78e18e5ffa72d4457caff9c75465`；
- Evidence files：`15373`，`258919192` bytes。
