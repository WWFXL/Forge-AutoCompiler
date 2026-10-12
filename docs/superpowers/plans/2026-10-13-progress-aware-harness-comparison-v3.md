# 进展感知结构化 Harness H0/H1 v3 实施计划

> Tracking Issue：[#438](https://github.com/WWFXL/Forge-AutoCompiler/issues/438)  
> 设计：`docs/superpowers/specs/2026-10-13-progress-aware-harness-comparison-v3-design.md`

## A. 未授权 candidate

- [x] 披露 v2 结果已观察及其正式停止决定。
- [x] 从 v5 选择未进入 v2 H0/H1 arms 的 9 个 checkpoint，并保持三构建系统、三深度覆盖。
- [x] 冻结 H0/H1、模型、schedule、三次重复、指标与停止规则。
- [x] 冻结 `T=300,000`、`R=100,000`、单臂与总体 Token/费用上界。
- [x] 创建 candidate protocol、const Schema、manifest、预注册和聚焦测试。
- [x] 保持 credential、Provider、Docker、正式 attempt 和 evidence write 全部未授权。

## B. candidate 门禁

- [x] 验证 manifest 与 const Schema 确定性一致。
- [x] 验证 9 个正式 checkpoint 和 3 个 canary checkpoint 均不在 v2 Q1/Q2 effect arms 中。
- [x] 验证父 inventory、v2 报告和 Token 预算门禁报告未漂移。
- [x] 验证预算加法、样本分层、schedule、授权边界和执行入口拒绝。
- [x] 运行聚焦测试、相邻回归、Ruff、format 和 diff check。

## C. 后续授权阶段

- [ ] 从审阅后的 candidate 派生独立 authorized identity，绑定 release revision。
- [ ] 先执行 Q0；只有 `9/9` strict 才允许读取 credential。
- [ ] 执行 Q1；只有 `6/6` 闭合且 treatment separation 通过才允许 Q2。
- [ ] 执行 Q2，封存 raw evidence、marker、inventory 和报告。
- [ ] 按预注册判据决定支持同项目跨状态复现，或停止进展感知 Harness 主线。

## 边界

本计划的 A/B 阶段不创建效果 observation。C 阶段尚未授权，不得读取 credential、调用 Provider 或创建正式 evidence。
