# 进展感知结构化 Agent Harness 资格实施计划

1. 创建 Issue #433 和堆叠分支 `yiwei/433-progress-aware-harness-qualification`，确认 Issue #430 与旧 evidence 只读。
2. 冻结本 spec、零 Provider 预注册和 `cpp-progress-aware-harness-qualification-v1` identity；只绑定新文件和父 checkpoint inventory，不把工程 canary 写入旧 evidence。
3. 在 Agent Workflow Runner 中增加行为保持的 middleware 扩展点；Runtime v1-v3 默认 middleware 顺序和行为不变。
4. 新增 Runtime v4：权威 `ProgressSnapshot`、确定性上下文裁剪、ready frontier 门禁、连续诊断无进展门禁和 recipe 建议。
5. 增加单元测试和脚本模型集成测试，覆盖快照稳定性、宿主路径排除、消息配对、门禁解锁、预算计数、H0 不变和 verifier 仍为最终裁判。
6. 实现 create-once 零 Provider runner，支持 `validate`、`plan`、`run`、`audit`、`report`；首个物理 attempt 前校验 revision、component hash、Docker runtime、父 checkpoint inventory 和 0 credential/0 Provider 边界。
7. 在真实 Docker checkpoint 上运行唯一工程门禁，保存独立 ledger、Session、candidate、evaluator、clean replay、cleanup 和 inventory。
8. 若门禁通过，形成 H0/H1 Provider 配对实验决策包；若失败，封口该 identity 并停止 Provider 实验。
9. 更新 `RESEARCH_STATUS.md` 与 `.claude/memory/project.md`，运行相关 pytest、Ruff、manifest/audit 和 `git diff --check`。
10. 提交并推送堆叠分支，创建中文 PR，关联 `Closes #433`。不自动合并，不修改或补跑 Issue #430。

