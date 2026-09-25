# Phase 5 v2 授权修订实施计划

日期：2026-09-25。设计：`../specs/2026-09-25-phase5-v2-authorized-amendment-design.md`。追踪：Issue #297。

- [x] 创建并回读独立跟踪 Issue，从 `main@03a870ee` 建立开发分支。
- [x] 冻结 authorized amendment 的身份、生命周期、恢复与停止规则。
- [x] 实现 authorized protocol、manifest、Schema 与 allowed-delta 校验。
- [x] 实现 release/Docker/Provider/0-orphan preflight。
- [x] 在模型创建前复核 exact commit、capabilities 与 selected build system。
- [x] 接入 external evaluator v2 和独立 attempt/thread/evidence identity。
- [x] 实现 create-once reachability、连续前缀 batch、报告与 Stage C 决策包。
- [x] 添加确定性与生命周期测试，运行后端相关回归和 lint。
- [x] 更新项目状态快照，提交、推送并创建中文 PR #298。
- [ ] PR 合并后由实验所有者运行真实 preflight、reachability 和六项目 batch。
