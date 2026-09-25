# Phase 5 v3 独立授权评测实施计划

日期：2026-09-25。设计：`../specs/2026-09-25-phase5-v3-independent-evaluation-authorized-design.md`。追踪：Issue #303。

- [x] 回读知识库 Stage B 判定与单 Agent Workflow Node 规格。
- [x] 审计 Phase 5 v2 manifest、runner、审计报告和 evaluator v3 identity。
- [x] 创建并回读中文 Issue，从干净主干建立独立分支。
- [x] 实现 v3 authorized protocol、const Schema 和确定性 manifest。
- [x] 实现 frozen v2 runner 到 evaluator v3 的薄适配器。
- [x] 添加 allowed-delta、独立 identity、绑定恢复、异常保真和报告合同测试。
- [x] 生成并验证 manifest/Schema，运行 Phase 5 相邻回归与 Ruff。
- [x] 更新项目状态快照并完成中文提交前审计。
- [ ] 中文提交、推送并创建 PR。
- [ ] PR 合并后运行零 Provider preflight。
- [ ] preflight 通过后，由实验所有者执行唯一 reachability 和六任务 batch。
