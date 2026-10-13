# H2 重放闭包状态资格设计

## 研究问题

Runtime v4 的 `candidate_ready` 只证明当前工作区已有成功 build、staged artifact 和 target mapping。H0/H1 v3 的两个 H0-only arm 表明，该状态不能证明提交的 recipe 能从冻结源码重建同一产物。

本阶段验证一个更窄的工程机制：在候选冻结前，对提交请求中的有序 recipe 做一次隔离 clean replay，并把“当前工作区可提交”和“recipe 对冻结源码闭合”建模为两个不同状态。只有两者都成立时才允许冻结候选。

正式 identity 为 `cpp-progress-aware-replay-closure-qualification-v1`。

## H2 状态与接口

H2 保留 Runtime v4 的权威进展快照，并新增：

- `workspace_ready`：当前工作区满足成功 build、artifact stage 和 target mapping；
- `replay_closure_ready`：最近一次通过的 preflight 与当前完整 frontier 一致；
- `replay_closure_fingerprint`：绑定 commit、image、source archive、recipe command 内容、supporting build、delivery 路径/类型/大小/SHA-256 和 target mapping；
- `replay_closure_failure`：最近一次失败的有界结构化分类。

preflight 接收已经通过现有 CandidateVerifier 的 `SubmitCandidateRequest`，复用正式 `build_replay_recipe()` 与相同的 `build.sh` 生成逻辑，在隔离 replay container 中执行，并比较完整 delivery。它不能写正式 replay attempt、改变 Compile Session 终态或代替 external evaluator。

## 失败分类

- `missing_bootstrap_step`：冻结源码存在 Autotools bootstrap 输入，但 recipe 直接调用不存在的 `configure`；
- `missing_generated_input`：构建工具明确报告 recipe 缺少生成目标或输入；
- `recipe_execution_failed`：recipe 失败，但证据不足以归入更具体类别；
- `artifact_set_mismatch`：recipe 成功结束，但产物路径集合不同；
- `artifact_content_mismatch`：路径相同但类型、大小或 SHA-256 不同；
- `timeout`、`cleanup_failed`、`internal_error`：基础设施或执行未闭合，全部 fail closed。

分类只提供下一步反馈，不改变严格裁判。Agent 仍需通过受限 Shell 增加通用 dependency/configure/build/artifact-stage 命令，再以新 frontier 重试。

## 生命周期

1. Agent 在当前工作区完成 build、smoke 与 artifact stage。
2. H2 快照报告 `workspace_ready=true`，但 `replay_closure_ready=false`。
3. Agent 调用 `submit_candidate_v1`。
4. 原有 contract、delivery、target mapping 和 functional oracle 先执行。
5. preflight 用候选 recipe 在隔离容器中执行 clean replay。
6. 失败时提交被拒绝，返回结构化 finding；Session 保持活动，Agent 可继续修复。
7. 成功时结果绑定当前 frontier，候选才按既有 create-once 路径冻结。
8. external evaluator 仍独立执行 S0-S5、functional oracle、provenance 和正式 clean replay。

任何命令、recipe、delivery、target mapping、source 或 image identity 变化都会改变 frontier，使旧的 closure 结论失效。

## 安全边界

- 不读取 credential，不调用 Provider；
- 不修改 v1-v3 evidence；
- 不使用项目名、仓库 URL 或项目族特例；
- preflight 失败不能把 Session 标为 `verification_failed`；
- preflight 成功不能跳过 CandidateVerifier 或 external evaluator；
- timeout、异常、证据缺失和 cleanup 失败均不得形成 ready 状态；
- 临时容器必须带受管标签，并在返回前完成删除对账。

## 资格范围

两个已知 v3 缺陷 recipe 用于机制回归；另以 CMake、Make、Autotools 正确 recipe 检查误拦。它们是 post-observation 工程资格证据，不能估计 H2 对成功率、成本或 token 的 treatment effect。

