# 进展预算感知 Jev 正式离线校准 v1 独立审计

## 审计对象

- Formal identity：`cpp-jev-progress-budget-calibration-v1`
- Tracking Issue：[#463](https://github.com/WWFXL/Forge-AutoCompiler/issues/463)
- Implementation revision：`039f6226b93709d8065387a4a0ebdb3fe18c7eee`
- Authorized manifest canonical SHA-256：`ffbdc6dfd9f940d327214c5bb3060fc798b455a44b67d5e7240db67574975116`
- Raw evidence：`.compile-sessions/benchmark-evidence-jev-progress-budget-calibration-v1`
- 正式决定：`stop_before_progress_budget_evaluation`

本审计在 formal marker 和 inventory 封存后只读执行。它不修改、不补写或重算正式
observation，不运行 evaluation，也不改变预注册门槛。

## 生命周期与预算

- Calibration attempt / observation / normalized response 为 `15/15/15`；request ID 为
  `15/15` 唯一，attempt、observation 和 normalized response 一一对应。
- Evaluation attempt 为 `0`，且不存在 evaluation evidence 目录。
- 用量为 15 个物理请求、14,552 input tokens、1,557 output tokens，模型费用
  `$0.000611184`；全部低于 30 requests、200,000 input、50,000 output tokens 和
  `$0.0084` 的授权上限。
- 独立浮点求和得到 `$0.0006111840000000001`，与 JSON 中的
  `$0.000611184` 在 `1e-15` 绝对容差内一致。该差异只是二进制浮点表示，不是计量缺口。

## Calibration 结果复核

15 个 calibration 状态的 primary Choice 分布为：

| Choice | 数量 |
| --- | ---: |
| `dependency` | 1 |
| `configure` | 3 |
| `build` | 0 |
| `escalate_agent` | 11 |

- 精确最优动作：`4/15`；按 CMake / Make / Autotools 分别为 `2/5`、`1/5`、`1/5`。
- 所选动作属于安全集合：`14/15`。高安全率主要来自 11 次保守升级，不能等同于低成本
  direct 能力。
- 正反顺序一致：`7/15`；按三个系统分别为 `4/5`、`2/5`、`1/5`。
- Platt 数据为 45 行，正类 18、负类 27，满足双类拟合合同。
- 校准后零 observed unsafe direct 阈值为 `0.7483803833712858`，只覆盖 `2/15`；
  raw threshold `0.57` 也只覆盖同两个状态。
- 两个可 direct 状态均来自 CMake；Make 和 Autotools 覆盖均为 0。覆盖低于预注册
  `5/15`，并违反三个构建系统各至少覆盖 1 个状态的门槛。

导致阈值收缩的关键相邻状态是：CMake 中两个安全 local Choice 的校准分数分别为
`0.74838` 和 `0.91196`，一个 unsafe `configure` Choice 的分数为 `0.72680`。
若降低阈值以纳入更多 local Choice，会先纳入该 unsafe action；Platt scaling 不能在不违反
零观察错误规则的情况下恢复覆盖。

## Evidence 完整性

- Inventory：51 files / 114,705 bytes；canonical SHA-256
  `83e6e5830ef551e4a2547666c98c4de8dcbeadd165c5f35cb876d25807482582`。
- Terminal marker SHA-256：`ace66d9f5ac800065de397762e00beaec665ffabc5bfe2a6b42ef9f09eaa1648`。
- JSON report SHA-256：`fcda7993369100d51409c2595853c7f03439c6b5f31eb2d6020103e6e149c4d0`。
- Inventory 逐文件大小和 SHA-256 已重算并匹配；marker、result 与报告决定一致。
- Evidence 和版本化报告中的 API key 精确值、`Authorization:` 与 `Bearer ` 命中均为 0。
- 父 evidence 的 702 个文件保持不变，inventory canonical SHA-256 仍为
  `2e4209fb52c07af949789ae7880db478f5a6d9326b4496de7fcff45ad64da9e9`。
- 本 identity 未创建受管 Docker 资源；共享 egress 保持冻结配置。

## 能够与不能得出的结论

本实验支持以下结论：固定 `jev-1.13.0` 在当前 calibration 项目族上倾向于安全但保守的
`escalate_agent`，动作顺序敏感性较高，无法在零 observed unsafe direct 规则下形成跨
CMake、Make、Autotools 的最低 direct 覆盖。因此当前 Jev typed Choice 不能进入
evaluation，更不能进入 controller。

本实验没有观察 evaluation holdout，因而不能判断 evaluation top-1、相对 RuleGate 或
TF-IDF+BudgetFit 的 holdout 增量，也不能估计 controller treatment effect、严格成功率、
端到端成本、统计显著性、跨时间泛化或自然失败总体表现。

该停止决定针对当前 Jev 输入、Choice 问题和校准门禁，不否定父 benchmark 已证明可辨识的
进展状态与确定性 BudgetFit。下一研究决策应在审阅该负结果后，选择保留语义进展与预算方法、
以零 Provider 轻量分类器为默认路由，或另行设计能够减少保守升级和顺序敏感性的全新 Jev
问题分解；不得续跑、补齐或降低本 identity 的阈值。
