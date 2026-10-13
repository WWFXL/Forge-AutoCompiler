# Submit 拒绝后的有界恢复门禁实施计划

## 1. 冻结身份与边界

- 绑定 Issue #449、identity `cpp-progress-aware-submit-rejection-recovery-gate-v1`、父 evidence inventory 和零 Provider 权限。
- 冻结 spec、预注册、const manifest/schema、案例、门槛和停止规则。
- Runtime v4/v5、#447 report 和 raw evidence 全程只读。

## 2. 实现 Runtime v6

- 继承 Runtime v5，不修改 v4/v5 文件。
- submit 返回后重载 Session，并记录当前权威 frontier 和结构化 submit 结果。
- 对非终态拒绝打开每 frontier 一次的 repair window，并释放该 Node 的 post-build phase。
- 只允许一个非 staging 修复命令和一个后续 artifact-stage；执行前消费许可。
- 暴露 repair window 状态到权威 progress snapshot 和 evidence ledger。

## 3. 脚本化回归

- 确定性复现 v5 submit 前/后 frontier 漂移。
- 验证无 submit 的 ready candidate 仍阻止 Shell。
- 验证拒绝后第一条 repair build 放行、第二条 repair build 拒绝、stage 只放行一次。
- 验证 frontier 更新后必须重新 submit，accepted/terminal/malformed response 不开放窗口。
- 验证同步与异步 middleware 路径一致。

## 4. 真实 Docker qualification

- 使用本地 Make 夹具构造 mjson 同构脏工作区陷阱。
- 用 scripted model 驱动完整 Runtime v6，真实执行 CandidateVerifier、functional oracle 和 ReplayClosureVerifier。
- 首次 closure 必须为 `recipe_execution_failed`，随后 repair build、stage 和第二次 submit 必须成功。
- 加入 ready-before-submit、repair-limit、invalid-contract、budget termination 和 cleanup 案例。

## 5. 封存与审计

- 在干净 exact revision 上 create-once 写入 identity、case result、summary、marker 和 inventory。
- 重算 inventory，核对 #447 inventory canonical SHA-256 与零受管容器。
- 生成 JSON/Markdown 报告并更新 `RESEARCH_STATUS.md`、`.claude/memory/project.md` 和知识库固定文档。

## 6. 决策

- 全部门槛通过：`proceed_to_unseen_three_arm_formal_comparison_design`；下一阶段只设计新的 18-arm formal identity。
- 任一恢复、安全、严格验证、预算、cleanup 或父 evidence 门槛失败：`stop_before_formal_comparison`，封口本 identity，不 replacement、不 backfill。
