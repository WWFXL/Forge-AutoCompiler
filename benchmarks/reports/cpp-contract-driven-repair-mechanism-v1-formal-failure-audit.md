# 契约驱动修复 mechanism v1 formal marker 封口失败审计

> 本报告从 9 个 create-once 文件做只读冻结；原始 evidence 未修改。首 arm 是未完成 batch 中的单个观测，不能解释为 treatment effect。

## 身份与完整性

- 执行 release：`e5acf5d79209fea8894fc31aad1cbb3ce815b205`。
- Manifest canonical SHA-256：`3a843799109e1163b34f4ed046f0155c7eca91a48ebaecb904e5ad3ed015829f`。
- Evidence：9 files / 66,466 bytes；inventory SHA-256 `24019a372a3b49fe6dc1b141da45f09f764639c253fc1ed16521341f3c6d2fb5`。
- Arm ledger：17 events，末尾 `experiment.completed`，head `87835c97ad556b49e6bb9d5665a00ffe2cbb510d5f19cf0ef8dc249134830c63`。
- 失败后人工只读资源审计：0 managed containers / 0 capture images。

## 已观察执行

| Sequence | Checkpoint | Arm | Requests | Input | Output | Total | Strict endpoint |
|---:|---|---|---:|---:|---:|---:|---|
| 1 | `rnnoise-0.1.1:delivery_target` | T2 | 5 | 44,561 | 8,423 | 52,984 | 是 |

该 arm 的 candidate、functional oracle、provenance、external evaluator v3、clean replay、S0-S5 与 cleanup 均通过，result 与 ledger 已在 marker 缺陷触发前落盘并互相绑定。

## 失败与终态

Runner 在 `after_result_and_experiment_completion_before_attempt_marker_terminalization` 调用 marker helper。Helper 接受单个 `updates` mapping，运行路径却传入 `status=...` 等关键字参数，因此抛出 `TypeError`；batch 异常封口再次调用同一不兼容接口。

- Attempt marker 保持 `started`；
- Batch marker 保持 `running`，completed arm 与 Provider attempt 计数均为 0；
- schedule 在 sequence 2 前停止；
- 当前 identity 视为失败，不允许续跑、重跑、replacement、backfill 或手工修补 marker。

## 解释边界与下一决策

本审计支持首个 T2 arm 在 marker 封口失败前到达预注册严格终点，也支持失败根因位于 runner marker API。它不提供 C0 vs T1、T1 vs T2 或 C0 vs T2 比较，不计算 p 值、项目级估计、总体成功率或模型排名。

修复通过独立 PR 审阅后，需要在“全新 36-arm identity”“显式导入该 arm 的 amendment”与“停止 collection”之间作科研决策；任何选项都不得修改本 evidence。
