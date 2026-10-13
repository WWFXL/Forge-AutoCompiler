# 未见项目族 H0/H1/H2 三臂比较资格实施计划

> Tracking Issue：[#445](https://github.com/WWFXL/Forge-AutoCompiler/issues/445)  
> 设计：`docs/superpowers/specs/2026-10-13-h0-h1-h2-unseen-qualification-design.md`

## A. 设计冻结

- [x] 审计 v3 H0 Token、请求和墙钟长尾。
- [x] 冻结三臂共同 `T=600,000`、`R=100,000` 预算。
- [x] 排除 v3 九个项目族及既有 Jev/typed-action 项目族。
- [x] 记录 `libConfuse` 来源筛查失败，不将其静默替换为同一候选。
- [x] 固定 `tinyxml2`、`mjson`、`libcsv` exact commit 与 reference recipe。
- [x] 冻结 H0/H1/H2 dispatch 和后续 9-arm canary / 18-arm 正式比较边界。

## B. 零 Provider 资格

- [x] 生成并验证 const manifest/schema。
- [x] Q0 重新获取 exact commit，并核对确定性 source archive SHA-256。
- [x] Q1 在真实 Docker 中完成三项目 recipe、smoke、artifact stage 和 H2 clean replay closure。
- [x] 验证 Session 状态、正式 replay attempt、容器 cleanup 和 0 credential/Provider/model token。
- [x] 生成 create-once marker、inventory、审计和报告。

## C. 验证与交接

- [x] 运行聚焦测试、Runtime v5 相邻回归、Ruff 和 format check。
- [x] 更新 `RESEARCH_STATUS.md` 与 `.claude/memory/project.md`。
- [ ] 将结果回写 Issue #445，提交并推送分支，创建堆叠 PR。

## D. 后续阶段

- [ ] 资格通过后创建独立 Provider canary identity。
- [ ] 在读取 credential 前冻结 9 arms、总 Token/request/费用上限和停止规则。
- [ ] canary 只检查运行闭合；正式 18-arm 比较使用新的 identity。

本计划 B/C 阶段不产生 treatment effect。旧 evidence 全部只读。
