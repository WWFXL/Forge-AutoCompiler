# Compile Runtime v7 工程契约

Runtime v7 在既有提交验证与 clean replay 上增加显式 executable verification policy，并通过独立 `external_evaluator_v2.py` 澄清 target artifact 与 support file 的分层语义。冻结的 evaluator v1、既有 Runtime identity、manifest、报告和实验 evidence 均保持只读。本版本只授权工程测试，不授权 Provider 或正式实验。

## executable 验证

- 默认产品路径保持 `-version`、`--version`、`--help` 三旗标顺序，任一退出 0 后固化 command、workdir、exit code、输出预览和完整输出 SHA-256。
- `successful_command_v1` policy 只供受信内部 evaluator 使用。它把每个交付 executable 的相对路径绑定到当前 Session 中一条位于 supporting build 之后、成功且未超时的 `smoke` command。
- 绑定的 command ID、command、workdir、exit code 和输出哈希必须一致；绑定集合必须与交付 executable 集合完全相同。非法、缺失或多余绑定均 fail closed。
- 外部 evaluator 只为单目标 executable 的单条成功 functional oracle 构造该 policy，不依据项目名选择行为。

## clean replay

- `repro/verify.sh` 继续重放显式选中的 verification command。
- artifact comparison 使用候选固化的 command 和 workdir 独立复验 executable，并比较 exit code、输出预览与完整输出 SHA-256。
- 全部交付文件继续严格比较相对路径集合、artifact type、size 和 SHA-256。新增 `smoke_workdir` 字段带空默认值，旧 Session 按 `/workspace` 解释。

## 外部 S2 集合

- Session `/artifacts` 全集是 delivery manifest，也是 clean replay 的严格集合。
- candidate `artifact_paths` 必须全部存在于 delivery manifest；`target_mapping` 仍必须满足唯一 target ID、允许类型和路径 pattern。
- install 额外产生且未逐项声明的 `support_file` 可以留在 delivery manifest。
- 未声明的 executable、shared/static library 或 object 继续触发 `candidate_artifact_set_mismatch`。所有 delivery manifest 文件仍需有效 size 和 SHA-256。

## 边界

本版本不修改 Compiler prompt、模型预算、Provider、停止规则或历史 Phase 5 evidence。Phase 5 v2 的独立 exact-commit build-system qualification 已在 `main@1269d34ccb58f3545ffbd5469c141d321cdc1246` 上通过，结果 SHA-256 为 `df98e57edfea7b42911e8008534b94a62261aa93d7c3d20ae36f6ee8f8343125`。

新的未授权 candidate identity 固化六项目完整 capability 集合及实际 selection；`c-ares` 固化为 capabilities `[cmake, autotools]`、selection `cmake`。candidate 使用独立 v2 evidence 目录与 evaluator v2，且继续保持 0 Provider、0 model、0 formal attempt。真实 reachability 或 batch 必须等待独立 authorized amendment。
