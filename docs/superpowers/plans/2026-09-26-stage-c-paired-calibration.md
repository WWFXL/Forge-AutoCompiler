# Stage C 十二项目配对校准实施计划

日期：2026-09-26。设计：`../specs/2026-09-26-stage-c-paired-calibration-design.md`。追踪：Issue #310。

## C0：协议设计

- [x] 核验 Phase 5 v5 decision、跨 run adjudication 和 0 managed resources。
- [x] 冻结受控系统比较、A/B 方法边界和 Stage B 排除规则。
- [x] 冻结 12 projects × 2 replicates × 2 arms 的 counterbalanced 结构。
- [x] 冻结候选预算、ITT/paired estimand、删失与停止规则。
- [x] 明确 Stage C execution 保持未启动。

## C1：任务与环境资格

- [ ] 建立结果盲来源池，排除 Stage B 和已有 A/B 模型结果项目。
- [ ] 实现确定性分层、seed 排序和排除审计。
- [ ] 冻结 12 个 exact-commit task、submodule 和 source snapshot。
- [ ] 为每项冻结 target、required artifacts、S3 oracle 和 bitwise 条件。
- [ ] 构建绑定 package repository snapshot 的不可变 Stage C image。
- [ ] 执行零 Provider reference qualification，并生成 qualification receipt。

## C2：统一 runner 候选

- [ ] 为 CXXCrafter-style baseline 实现受控环境与统一 candidate adapter。
- [ ] 复用 Stage B Agent Workflow Node，不增加 fast path 或 evaluator feedback。
- [ ] 统一 attempt ledger、request/token accounting、external evaluator 和 cleanup。
- [ ] 实现 24 pairs / 48 arms 的 counterbalanced schedule 与 pair-boundary budget gate。
- [ ] 生成未授权 manifest、const Schema、protocol 和 runner。
- [ ] 将 Provider、credential、model creation、Docker、attempt 和 evidence write 设为 false/0。

## C3：零 Provider 门禁

- [ ] 用 scripted/fake model 覆盖 A/B success、no-submit、budget exhaustion 和 candidate rejection。
- [ ] 验证第一 arm 普通失败后仍执行第二 arm。
- [ ] 验证 identity/evidence/cleanup/orphan 缺陷 fail closed。
- [ ] 用真实 Docker 覆盖 CMake、Make、Autotools、oracle、clean replay 和 cleanup。
- [ ] 验证任务选择、manifest、schema、schedule 和报告确定性。
- [ ] 运行相邻回归、完整后端测试、lint 和 frozen identity 检查。

## C4：执行候选与授权

- [ ] 发布未授权 candidate PR，并保持 0 Provider / 0 formal evidence。
- [ ] 只读审计历史成本，确认或修订 300,000-token 单臂候选上限。
- [ ] 单独派生 authorized amendment，绑定 release、image ID、模型、网络介质、evidence 目录和总 token ceiling。
- [ ] 获得实验负责人明确的 Provider、14,405,000-token 最坏上限和 48-arm 授权。

## C5：正式执行与分析

- [ ] 执行唯一 reachability；失败即停止且不创建 attempt。
- [ ] 按冻结顺序串行执行 24 pairs，每个 pair 后核验预算、证据和 0 managed resources。
- [ ] 生成 create-once deployment、paired、attrition、cost、bitwise 和 inventory 报告。
- [ ] 只读复算全部哈希、终态和分析结果。
- [ ] 根据最小有意义效应、区间宽度、成本和失败结构决定是否扩样。

本 Issue 只完成 C0。C1 及之后必须分别建立可审查的实现 Issue/PR；C5 不属于本次授权。
