# 自然失败正式 build/reference 资格 v1 实施计划

日期：2026-10-12。追踪：Issue #419。设计：
`docs/superpowers/specs/2026-10-12-natural-failure-formal-build-reference-v1-design.md`。

## A. 结果盲协议冻结

- [x] 核对 v4 正式 report、构造效度审计、v5 canary、当前 Git 和 Docker runtime；
- [x] 创建并回读独立 tracking Issue #419；
- [x] 从 PR #418 的 HEAD 创建 `yiwei/419-formal-build-reference-v1`；
- [ ] 冻结默认路径 identity 的预注册、manifest、Schema、runner 输入、预算和停止规则；
- [ ] 在任何正式 build observation 前提交并推送协议提交。

## B. 默认路径 runner

- [ ] 新增独立 formal runner，不修改 v1-v5 历史 runner；
- [ ] 从父 report 哈希校验并读取固定 36 项，校验系统、rank、family 和 exact commit；
- [ ] 实现 create-once evidence、marker、partial result、项目级故障隔离和 final audit；
- [ ] 保持 v5 的 artifact、machine、probe、producer 和动态 target 分类合同；
- [ ] 添加角色配额、已知反例、source-only 误伤、cleanup 和零 Provider 门禁。

## C. 零 Provider 正式运行

- [ ] 运行 Docker、镜像、磁盘和 0 managed-resource preflight；
- [ ] 对 36 个项目各执行两个 clean 默认路径 observation；
- [ ] 保存所有成功、失败、网络、timeout、不一致和 infrastructure 结果；
- [ ] 执行 formal audit，冻结 JSON/Markdown 报告和 evidence inventory；
- [ ] 根据预注册门槛给出 proceed/stop 决定。

## D. Reference closure（仅在 C 通过后）

- [ ] 建立独立 reference identity、Schema、manifest 和 create-once evidence；
- [ ] 按 system/role/rank 顺序审核全部 stable candidate 的日志、文档和默认 target；
- [ ] 在第一次运行前冻结全部 recipe、包版本、产物和 functional oracle；
- [ ] 每份 recipe 执行两个 clean reference closure；
- [ ] 审计 ELF/`ar`、machine、producer、source identity、oracle、provenance、clean replay 和 cleanup；
- [ ] 检查每系统 `1/1/2` 配额并给出是否进入 action matrix 的关键决定。

## E. 状态与发布

- [ ] 更新 `RESEARCH_STATUS.md` 和 `.claude/memory/project.md`；
- [ ] 运行聚焦测试、相邻冻结回归、Ruff、Schema/manifest/audit 和 `git diff --check`；
- [ ] 提交、推送并创建中文 PR，以 `Closes #419` 关联 Issue；
- [ ] 回读 PR 并等待 CI。

## 固定边界

- 本阶段 0 credential、0 Jev request、0 Agent Provider request、0 model token；
- 不续跑、重跑、replacement、backfill 或修改任何历史 evidence；
- 默认路径 identity 失败时不创建 reference identity；
- reference identity 失败时不创建动作矩阵或 Provider identity；
- 固定安全预算不是动态预算控制证据。

