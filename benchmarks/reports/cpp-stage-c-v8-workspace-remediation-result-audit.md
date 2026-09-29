# Stage C v8 workspace remediation 结果冻结与只读审计

> 本报告由确定性只读审计器从冻结 evidence 生成；原始 evidence 未修改。

## 身份与完整性

- Release：`6682d86cb30cc4e8d7b240bca8922606077a4808`。
- Authorized manifest canonical SHA-256：`df3a8c7ac1e13567b99ec5b7c77d341b6df20f35236cf767e76c06af46835a61`。
- Evidence：16 files / 631,570 bytes。
- Inventory SHA-256：`afe607e075509eee1999a65f4c485b0995959a1f026bf22f3f6ff7673d6b14a7`。
- 四条 ledger 均通过 `ExperimentLedger.verify_path()`，并由唯一末尾 `experiment.completed` 封口；completion 中的 result SHA-256 与实际文件一致。

## 结果

唯一 reachability 通过；四任务按 `theora -> json-c -> libjpeg-turbo -> oatpp` 执行，strict success、S0-S5、bitwise reproducible 与 cleanup 均为 4/4。
完整账本为 37 requests / 260,873 input / 19,115 output / 279,988 total tokens。

| Task | Requests | Tokens | Submit | Rejection | Strict | Bitwise | Cleanup |
|---|---:|---:|---:|---|---:|---:|---:|
| `theora` | 12 | 86,910 | 1 | - | 是 | 是 | 是 |
| `json-c` | 6 | 35,839 | 1 | - | 是 | 是 | 是 |
| `libjpeg-turbo` | 7 | 46,120 | 2 | `target_mapping_invalid` | 是 | 是 | 是 |
| `oatpp` | 11 | 111,037 | 1 | - | 是 | 是 | 是 |

`libjpeg-turbo` 首次提交被 pre-freeze verifier 以 `target_mapping_invalid` 拒绝，并在同一 physical attempt 内修复后第二次提交成功；其余任务均一次提交成功。

## 解释边界

本结果支持：v8 workspace remediation 在这四个固定 canary task 上完成端到端工程闭合；四个候选均通过 external evaluator v4、bitwise replay 与 cleanup；`libjpeg-turbo` 存在一次可观察的同 attempt 修复轨迹。

本结果不替换 Stage C v5 预注册结果，不估计 treatment effect、p 值或总体成功率，不进行 Provider/模型排名，也不外推到未观测项目、环境或实验 identity。一次修复轨迹不能单独证明 verifier 的总体因果效果。

## 决策边界

该 create-once identity 已消费完毕，不允许重跑、retry、replacement、backfill 或续跑。审阅本冻结报告后，再决定扩大确认性样本、设计独立 replication，或停止当前机制路线；任何新实验都需要新的 identity、预算、停止规则和明确授权。
