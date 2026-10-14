# Runtime v6 的 H0/H1/H2 held-out 正式比较资格实施计划

> Tracking Issue：[#451](https://github.com/WWFXL/Forge-AutoCompiler/issues/451)
> 设计：`docs/superpowers/specs/2026-10-14-h0-h1-h2-runtime-v6-qualification-design.md`

## A. 设计冻结

- [x] 排除 Runtime v6 已观察的 `mjson` 及全部既有 H0/H1/H2 项目族。
- [x] 固定 CMake `cmark`、Make `mpc`、Autotools `expat` exact commit 和真实静态库终点。
- [x] 冻结 H0/Runtime v3、H1/Runtime v4、H2/Runtime v6 的唯一分派。
- [x] 冻结三臂共同预算、18-arm 规模、主要 estimand、非劣界和解释边界。
- [x] 明确 Provider 正式比较使用独立 identity，当前 identity 不产生效果 observation。

## B. 零 Provider 资格

- [x] 生成并验证 const manifest/schema。
- [x] 提交 candidate，使资格运行绑定干净 release revision。
- [x] Q0 重新获取三个 exact commit 并核对确定性 source archive。
- [x] Q1 完成三个禁网 Docker reference recipe、smoke、artifact stage 和 clean replay closure。
- [x] 验证 Session、正式 replay attempt、Runtime 绑定、cleanup 与零 credential/Provider/model token 边界。
- [x] create-once 封存 marker、inventory，完成独立 audit 和版本化报告。

## C. 验证与交接

- [x] 运行聚焦测试、Runtime v3/v4/v6 与 replay closure 相邻回归。
- [x] 运行 Ruff、format、manifest/schema check 和 `git diff --check`。
- [x] 更新 `RESEARCH_STATUS.md` 与 `.claude/memory/project.md`。
- [x] 将结果回写 Issue #451，提交、推送并创建堆叠 PR。

## D. 后续阶段

- [ ] 资格通过后，另建 18-arm Provider 正式比较 identity。
- [ ] Provider 前冻结模型、执行顺序、总 request/token/费用上限和停止规则。
- [ ] 将 H2 对 H1 作为主要比较，H1 对 H0 作为 Harness 消融。

本计划 B/C 不产生 treatment effect。历史 evidence 永久只读。
