# 契约驱动修复 mechanism v2 formal checkpoint 构造失败审计

> 本报告从 70 个 create-once 文件只读复算；原始 evidence 未修改。当前是 12/36 arms 的不完整 batch，不构成 treatment effect 证据。

## 身份与完整性

- 执行 release：`fe36cf137dbaa3a0dd29793ae67e74e97a631c61`。
- Manifest canonical SHA-256：`491d877c0d4b94380e4541a23dfd65e7ec83eee2f110d2420c2673597f873609`。
- Evidence：70 files / 689,742 bytes；inventory SHA-256 `5c885b2a9d2bb2156f28913365c73b32d11a60ffcce7804d85d6cae718eb9d11`。
- Batch：`failed`，完成 4/12 checkpoints、12/36 arms，75 requests / 1,068,534 total tokens。
- 失败后只读资源核验：0 managed containers / 0 capture images；无 symlink、`.tmp` 或 partial evidence。

## 已完成 Arms

| Seq | Checkpoint | Arm | Strict | Requests | Input | Output | Total | Terminal |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | `rnnoise-0.1.1:delivery_target` | T2 | 1 | 4 | 39,076 | 7,896 | 46,972 | success |
| 2 | `rnnoise-0.1.1:delivery_target` | C0 | 1 | 6 | 61,424 | 8,879 | 70,303 | success |
| 3 | `rnnoise-0.1.1:delivery_target` | T1 | 1 | 6 | 45,754 | 3,674 | 49,428 | success |
| 4 | `rnnoise-0.1.1:provenance` | C0 | 0 | 8 | 167,480 | 28,067 | 195,547 | budget_exhausted |
| 5 | `rnnoise-0.1.1:provenance` | T1 | 0 | 8 | 141,463 | 26,540 | 168,003 | budget_exhausted |
| 6 | `rnnoise-0.1.1:provenance` | T2 | 0 | 8 | 91,739 | 19,162 | 110,901 | budget_exhausted |
| 7 | `libsoundio:provenance` | T1 | 0 | 8 | 109,682 | 28,497 | 138,179 | budget_exhausted |
| 8 | `libsoundio:provenance` | T2 | 0 | 8 | 70,255 | 7,103 | 77,358 | budget_exhausted |
| 9 | `libsoundio:provenance` | C0 | 0 | 8 | 109,122 | 20,489 | 129,611 | budget_exhausted |
| 10 | `libsoundio:delivery_target` | T2 | 1 | 4 | 27,709 | 3,684 | 31,393 | success |
| 11 | `libsoundio:delivery_target` | T1 | 1 | 4 | 24,266 | 2,170 | 26,436 | success |
| 12 | `libsoundio:delivery_target` | C0 | 1 | 3 | 19,288 | 5,115 | 24,403 | success |

12 个 attempt marker 均为 `complete`，result 与末尾 `experiment.completed` ledger event 相互绑定；所有 arm 均完成 cleanup 且记录 0 managed orphan。严格成功的 6 个 arm 还闭合 candidate、functional oracle、provenance、external evaluator v3、clean replay 与 S0-S5；其余 6 个 arm 是预注册的模型行为 `budget_exhausted` 零 outcome。

## 不完整数据描述

下表 outcome 顺序均为 `C0/T1/T2`。`d01=T1-C0`、`d12=T2-T1`、`d02=T2-C0`，project score 是两个 stratum delta 的均值。

| Project | delivery/target | provenance | d01 | d12 | d02 |
|---|---|---|---:|---:|---:|
| rnnoise-0.1.1 | 1/1/1 | 0/0/0 | 0 | 0 | 0 |
| libsoundio | 1/1/1 | 0/0/0 | 0 | 0 | 0 |

两个完整项目的三个 observed-complete estimate 都是 `0`。余下 8/12 checkpoints 不填零；按预注册最不利/最有利赋值，三个比较的 identification interval 均为 `[-2/3, +2/3]`。由于相关 arm 不完整，`primary_test=null`、`secondary_test=null`，支持性比较也不产生确认性检验或 p 值。

## 失败与终态

Batch 在 checkpoint 5 `lz4:delivery_target` 的 parent capture 阶段以 `FormalFatalError` 停止。冻结 engine 的 `_compiled_target_path` 要求恰有 1 个 target-mapped compiled artifact，而冻结 `lz4` 合同同时要求 executable `bin/lz4` 和 static library `lib/liblz4.a`，因此 checkpoint builder 与多 target 合同不兼容。

- 故障发生在 checkpoint marker/ledger 与 sequence 13 attempt 创建前；
- batch marker 已以 `failed` 封口，24 arms 保持未运行；
- 当前 identity 永久终止，不允许 continuation、rerun、retry、replacement、backfill、schedule extension 或 marker 修补。

## 解释边界与下一决策

本审计支持两个完整项目中 delivery/target 三臂全为 1、provenance 三臂全为 0，也支持所有 observed project score 为零。由于只完成 2/6 projects 且 identification interval 为 `[-2/3, +2/3]`，它不支持“存在或不存在有意义效应”、显著性、总体成功率、Provider 可靠性或模型排名。

下一项研究决策是在“先修复 checkpoint builder 并建立全新独立 identity”与“停止 formal collection”之间选择；任何后续方案都不得修改或导入本 batch 的冻结 evidence。
