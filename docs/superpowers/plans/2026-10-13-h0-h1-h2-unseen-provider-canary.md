# 未见项目族 H0/H1/H2 九臂 Provider Canary 实施计划

> Tracking Issue：[#447](https://github.com/WWFXL/Forge-AutoCompiler/issues/447)
> 设计：`docs/superpowers/specs/2026-10-13-h0-h1-h2-unseen-provider-canary-design.md`

## A. 协议冻结

- [x] 固定三个项目、三臂与九臂拉丁方顺序。
- [x] 固定 DeepSeek 模型、单臂预算和整批 `$7.56` 费用上界。
- [x] 固定 canary 硬门禁、停止规则和解释边界。
- [x] 实现 const manifest/schema、runner 和聚焦测试。
- [ ] 提交并推送冻结 release；在 Provider 前记录 exact revision。

## B. Q0 零 Provider 资格

- [ ] 核对 #445 parent identity、inventory 和三个 source archive。
- [ ] 核对 Docker image、runtime dispatch、工作树与零受管资源。
- [ ] 创建 create-once identity/Q0 evidence，确认 0 credential read 和 0 Provider request。

## C. Q1 九臂 Canary

- [ ] Q0 通过后读取冻结 credential 环境变量并执行 9 arms。
- [ ] 每臂保留 request、usage、budget、S0-S5、instrumentation、Session 和 cleanup evidence。
- [ ] 对 identity、硬门禁、总预算和 inventory 做独立 audit 并生成报告。

## D. 交接

- [ ] 更新 `RESEARCH_STATUS.md` 与 `.claude/memory/project.md`。
- [ ] 更新知识库固定研究路线文档。
- [ ] 回写 Issue #447，提交、推送并创建堆叠 PR。

旧 evidence 全部只读；禁止 replacement、backfill、删除失败 observation 或在同 identity 重跑。
