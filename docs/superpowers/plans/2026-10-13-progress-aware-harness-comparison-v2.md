# 进展感知结构化 Harness H0/H1 配对比较 v2 实施计划

## A. v1 封口与 v2 冻结

- [x] 保留 v1 Q0/Q1 raw evidence，确认 Q2 不存在并生成 inventory。
- [x] 只读确认 H1 主 events 存在 snapshot/compaction，H0 不存在。
- [ ] 冻结 v2 manifest、Schema、预注册、runner、测试和组件哈希。

## B. 零 Provider 与 canary

- [ ] 重新执行 v2 Q0，要求 9/9 strict、离线 replay 和 cleanup。
- [ ] 执行 v2 Q1 的 6 个 arms，除通用闭合外强制 treatment-separation instrumentation 门禁。

## C. 正式实验与分析

- [ ] Q1 通过后按冻结顺序执行 27 pairs / 54 arms。
- [ ] 计算 strict success、task-cluster bootstrap、成本与长尾指标。
- [ ] seal inventory、生成报告、更新研究状态并运行 evidence audit。

## 边界

v1/v2 evidence 彼此隔离。v1 不续跑、不重分类；v2 不修改 treatment、样本、模型、预算、顺序、裁判或判据。
