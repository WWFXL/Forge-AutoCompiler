# Jev 三臂端到端 canary v4 零 Provider 资格失败

- 决定：`supersede_with_fresh_v5_identity`
- Provider / credential / formal attempt / model token：`0 / 0 / 0 / 0`
- Compile Session：`3`，全部 cleanup，受管资源残留 `0`

v4 的 args/CMake 与 hoextdown/Make 均完成代码绑定动作、Candidate 提交、S0-S5、functional oracle、provenance 和 clean replay，严格成功为 `2/2`。

c-ares/Autotools 已正确选择冻结的 Autotools 能力，缺失源码故障、`dependency` 恢复和后续构建也均按预期完成。其 `artifact_stage_commands` 继承了 `make install`；Forge 在成功构建后将该命令识别为新的 build 动作，并以退出码 `126` 拒绝进入 post-build 阶段。因而第三个 case 在 Candidate 提交前停止。

该结果证明 v3 暴露的宿主文件权限与构建系统身份问题已修复，同时说明 v4 资格门禁正确捕获了 staging 动作角色冲突。v4 不续跑、不替换、不补齐；v5 只能将 c-ares staging 改为明确的 `mkdir/cp` 代码绑定动作，并使用新的 manifest、预注册、报告和 evidence root。

本次资格失败不能解释 Jev、RuleGate 或完整 Agent 的能力，也不支持 treatment effect 或成本节省结论。
