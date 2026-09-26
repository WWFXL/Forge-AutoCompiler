# Stage C 十二项目配对校准实施计划

日期：2026-09-26。设计：`../specs/2026-09-26-stage-c-paired-calibration-design.md`。设计追踪：Issue #310。实现追踪：Issue #312。

## C0：协议设计

- [x] 核验 Phase 5 v5 decision、跨 run adjudication 和 0 managed resources。
- [x] 冻结受控系统比较、A/B 方法边界和 Stage B 排除规则。
- [x] 冻结 12 projects × 2 replicates × 2 arms 的 counterbalanced 结构。
- [x] 冻结候选预算、ITT/paired estimand、删失与停止规则。
- [x] 明确 Stage C execution 保持未启动。

## C1：任务与环境资格

- [x] 建立结果盲来源池，排除 Stage B 和已有 A/B 模型结果项目。
- [x] 实现确定性分层、seed 排序和排除审计。
- [x] 冻结 12 个 exact-commit task、submodule 和 source snapshot。
- [x] 为每项冻结 target、required artifacts、S3 oracle 和 bitwise 条件。
- [x] 修正资格探针暴露的版本敏感 reference recipe：为 libsndfile Autotools 路径补齐 GNU AutoGen，为 civetweb 固定损坏提交冻结最小源码修复，并以 Dockerfile SHA-256 label 拒绝过期镜像。
- [x] 构建绑定 package repository snapshot 的不可变 Stage C image。
- [x] 执行零 Provider reference qualification，并生成 qualification receipt。

## C2：统一 runner 候选

- [x] 为 CXXCrafter-style baseline 实现受控环境与统一 candidate adapter。
- [x] 复用 Stage B Agent Workflow Node v2，不增加 fast path 或 evaluator feedback。
- [x] 统一 attempt ledger、request/token accounting、external evaluator 和 cleanup。
- [x] 实现 24 pairs / 48 arms 的 counterbalanced schedule 与 pair-boundary budget gate。
- [x] 实现由资格回执派生 authorized manifest、const Schema、protocol 和 runner。
- [x] 在资格阶段保持 Provider、credential、model creation、formal attempt 和 formal evidence write 为 false/0。

## C3：零 Provider 门禁

- [x] 用 scripted/fake model 覆盖 A success、modifier、no-submit/budget exhaustion；B 的 success、no-submit、budget 和 candidate rejection 复用 Runtime v2 既有门禁。
- [x] 验证第一 arm 普通失败后仍执行第二 arm。
- [x] 验证 identity/evidence/cleanup/orphan 缺陷 fail closed。
- [x] 用真实 Docker 覆盖 CMake、Make、Autotools、oracle、clean replay 和 cleanup。
- [x] 验证任务选择、资格 manifest/schema、schedule 和报告确定性。
- [x] 运行相邻回归、完整后端测试、lint 和资格 frozen identity 检查；authorized identity 等资格回执后生成。

## C4：执行候选与授权

- [x] 发布未授权 candidate PR，并保持 0 Provider / 0 formal evidence。
- [x] 只读审计历史成本，确认 300,000-token 单臂硬停止上限。
- [x] 派生 authorized identity，绑定 release policy、image ID、模型、网络介质、evidence 目录、资格回执和总 token ceiling。
- [x] 获得实验负责人对 Provider、14,405,000-token 最坏上限和 48-arm 的明确授权。

## C5：正式执行与分析

- [ ] 执行唯一 reachability；失败即停止且不创建 attempt。
- [ ] 按冻结顺序串行执行 24 pairs，每个 pair 后核验预算、证据和 0 managed resources。
- [ ] 生成 create-once deployment、paired、attrition、cost、bitwise 和 inventory 报告。
- [ ] 只读复算全部哈希、终态和分析结果。
- [ ] 根据最小有意义效应、区间宽度、成本和失败结构决定是否扩样。

Issue #310 只完成 C0。Issue #312 实现 C1-C4 的执行准备；C5 正式 reachability 与 batch 不属于本次代码实现。
