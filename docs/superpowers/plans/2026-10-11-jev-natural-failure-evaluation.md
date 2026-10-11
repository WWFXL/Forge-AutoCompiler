# Jev 混合链路自然构建失败评测实施计划

日期：2026-10-11。设计：`../specs/2026-10-11-jev-natural-failure-evaluation-design.md`。
追踪：Issue #411。

## A. 结果盲设计冻结

- [x] 核对 Issue #408 正式比较、Issue #409 混合链路 canary 和当前研究边界。
- [x] 创建并回读独立 tracking Issue #411。
- [x] 从父结果提交建立 `yiwei/411-jev-natural-failures` 分支。
- [x] 核对 CXXCrafter source revision、Top100 CSV、构建系统元数据和 Forge 历史 project family。
- [x] 冻结 22 个 exact-commit 候选、系统内角色、标准初始路径、资源预算和不可替换规则。
- [x] 提交并推送 spec/plan，使设计提交先于任何构建 observation。

## B. 零 Provider qualification identity

- [x] 创建版本化 source-pool fixture，记录选择输入、排除摘要、排序键、仓库元数据和 exact commit。
- [x] 创建 manifest、JSON Schema 和预注册，绑定设计提交、镜像 ID、父证据哈希和独立 evidence 根。
- [x] 固定失败类别规范化、命令/墙钟预算、停止条件、create-once marker 和 inventory 合同。
- [x] 添加 protocol 校验和只读 audit；默认入口不得读取 credential 或调用 Provider。

## C. 初始自然失败 replay

- [x] 运行 Docker preflight，确认镜像、daemon、磁盘和 0 managed resources。
- [ ] 对 22 个候选执行 source/exact-commit 门禁；唯一 attempt 完成 7 项后在第 8 项因 runner 超时处理缺陷失败封口。
- [ ] 对 source-eligible 项目执行两个独立、无网络的标准初始路径；已完成项保留，未观察项不填零。
- [x] 保存已发生的完整日志、命令退出和 cleanup；只读审计纠正两项网络失败误标签。
- [x] CMake calibration 固定配额已不可能达到，冻结负结果并停止 v1。

## D. Reference recipe 与动作矩阵

v1 source qualification 未通过，本节不执行。

- [ ] 对稳定自然失败逐项审计仓库文档、构建文件和失败日志，冻结可追溯 reference recipe。
- [ ] 为每项绑定 target、functional oracle、provenance 和 clean replay，禁止源码补丁和 verifier 放宽。
- [ ] 在两个全新 session 中验证 reference closure。
- [ ] 从同一自然失败状态分别执行 `dependency`、`configure`、`build`，形成第一个 outcome matrix。
- [ ] 在第二个全新 checkpoint 完整 replay matrix，核对 categorical consistency。
- [ ] 检查 cleanup 和 0 managed resources。

## E. 资格分析与关键结论

- [x] 审计已观察角色配额；动作分布和 RuleGate 指标因未进入动作矩阵而不计算。
- [x] 给出 `stop_natural_failure_evaluation_v1`，不进入 Provider evaluation。
- [x] 生成 create-once 失败 JSON/Markdown、canonical inventory 和只读失败审计。
- [x] 更新 `RESEARCH_STATUS.md` 和 `.claude/memory/project.md`，区分 observation、派生指标和解释边界。
- [x] 运行聚焦测试、lint、Schema/protocol 校验、`git diff --check` 和最终 0-orphan 审计。

## F. 仅在资格通过后执行 Provider 阶段

v1 未通过，本节不执行。

- [ ] 派生独立 Provider identity，冻结 design prompt、calibration 方法、evaluation schedule 和三臂顺序。
- [ ] 固定 Jev/Agent 模型、request/token/费用/墙钟预算、无隐式 retry、停止规则和 evidence 路径。
- [ ] 先在 design 项目运行最小 canary；只检查接线、预算、严格终点和 cleanup。
- [ ] 在 calibration 项目冻结门槛；evaluation 项目只运行一次分析，不调整 prompt/阈值。
- [ ] 执行 `AlwaysAgent`、`RuleGate+Agent`、`JevGate+Agent`，保存全部失败、超时和 Provider 错误。
- [ ] 按项目族聚类 bootstrap 分析严格成功非劣、总成本下降和 Jev 直接动作错误率。

## G. 发布与长期状态

- [x] 提交、推送并创建中文 PR，以 `Closes #411` 关联 tracking Issue。
- [x] 回读 PR，等待 CI；只有获得完整关键结论后才更新个人知识库固定文档。

## 固定边界

- Issue #408/#409 及更早 manifest、raw evidence、marker、ledger 和报告永久只读。
- 构建 observation 后不得换项目、前移角色、修改 exact commit、动作语义、阈值门槛或 verifier。
- qualification 失败即停止 Provider；不得用 replacement、backfill 或事后缩小分母挽救。
- 资格/canary 不解释为 treatment effect；固定安全预算不解释为动态预算控制。
- Provider 阶段若需要修改通用机制或数据合同，关闭当前 identity，另建 Issue 和版本。
