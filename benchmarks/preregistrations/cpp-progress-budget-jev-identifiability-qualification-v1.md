# 进展预算感知 Jev 联合 benchmark 可辨识性资格 v1 预注册

## 身份与授权

- Identity：`cpp-progress-budget-jev-identifiability-qualification-v1`；
- Tracking Issue：[#457](https://github.com/WWFXL/Forge-AutoCompiler/issues/457)；
- 工作类型：正式零 Provider benchmark 资格数据采集；
- Evidence root：`.compile-sessions/benchmark-evidence-progress-budget-jev-identifiability-qualification-v1`，create-once；
- Attempt 上限：1；
- 用户已授权持续执行至本阶段关键结论。

本阶段允许公开源码网络、Docker 和新 identity evidence；不读取 credential，不调用 Provider/Jev/真实 Agent，不实现完整 controller，不修改任何历史 evidence。

## 样本与来源冻结

固定 6 个未进入历史 Forge 动作或效果 benchmark 的项目族：

| 构建系统 | 项目 |
|---|---|
| CMake | `p-ranav/argparse`、`Neargye/magic_enum` |
| Make | `kgabis/parson`、`antirez/sds` |
| Autotools | `troglobit/libuev`、`ivmai/libatomic_ops` |

exact commit、commit time、source archive SHA-256、license SHA-256、构建 recipe、产物和 oracle 由 source pool 固定。`rxi/log.c` 与 `tidwall/hashmap.c` 因无项目级构建入口排除；`libdeflate` 因 Make 配额已由原生 Make 项目闭合而未进入。以上排除发生在任何正式 state/action outcome 前。

本 identity 全部作为 benchmark design/qualification 数据。后续 Jev calibration/evaluation 必须使用独立项目族；正式 evaluation 还必须使用晚于本 identity 最大 exact-commit time 的时间后移 commit。

## 设计

每项目 5 个语义状态、4 个动作、2 次独立 branch，共 `6 * 5 * 4 * 2 = 240` 个 action branches；每项目另执行 2 次 reference closure 和 2 次 replay-gap pre-action closure。

状态为 `missing_compile_input`、`invalid_build_state`、`wrong_build_target`、`compound_recovery`、`replay_recipe_gap`。fault identity 仅保存在 hidden mapping，不进入 state ID 或模型输入。复合状态与单一 invalid state 共享末次构建故障表面，但 progress history 不同。

动作顺序固定为 `dependency`、`configure`、`build`、`escalate_agent`。动作成本固定为 `build=1`、`configure=2`、`dependency=3`、`escalate_agent=6`。安全动作必须两次均达到 candidate、functional、provenance 和 clean replay 严格终点。

三个预算 profile 和 Agent planning reservation 由 manifest 固定。每个语义状态派生 3 个 matched decision，共 90 个。路由先最大化严格成功可达性，再最小化 Provider reservation 和动作成本；安全 direct 优先于 Agent，无法在预算内形成安全终点时 stop。

## 基线

- `PhaseBudgetRuleGate`：只读取 phase facts、预算和冻结成本；critical 时 stop，replay-failed 时选 dependency，其他可执行状态固定选 build，不读取日志和 progress history。
- `LogTFIDF+BudgetFit`：只用末次 semantic log 做项目族隔离的 TF-IDF/逻辑回归动作分类，再执行同一预算可行性门禁；不读取结构化 progress history。

## 门槛与停止规则

所有以下门槛必须通过：

1. 6/6 项目、30/30 状态、240/240 branches、90/90 decisions 和 12/12 reference closures 完整；
2. state/action categorical replay 一致率至少 95%；
3. 三个构建系统都出现四类最优动作和 direct/escalate/stop 三种路由；
4. RuleGate route accuracy `< 0.75`；
5. TF-IDF+BudgetFit route accuracy `< 0.95`；
6. 30/30 matched semantic state 至少出现两种 route；
7. replay pre-action rejection `12/12`，dependency recovery strict success `12/12`；
8. 全部执行有界、预算派生可重建、动作后状态闭合、0 credential/Provider/Jev/Agent/model token、cleanup 后 0 managed resource；
9. 模型输入不直接泄露 hidden fault identity 或标签。

全部通过时决定 `proceed_to_jev_progress_budget_calibration_design`。任一失败决定 `stop_before_jev_calibration_and_controller_implementation`。不得结果后修改阈值、动作成本、预算 profile、fault、项目、label 或 baseline；不得 retry、replacement、backfill 或续跑。

## 解释边界

本资格不估计 Jev、Agent 或 controller 效果，不支持成功率非劣、Provider 成本下降、自然失败、开放世界或通用模型路由主张。Agent surrogate 的 reservation 是冻结规划量，实际 Provider 用量仍为 0。
