# 修复基座后18项目Harness重新测量准备

用户要求“重现测量”。本轮为数据采集前的必要准备，尚未产生新模型效果。

- Issue #817；身份`cpp-build-harness-update-repaired-comparison-flash-v1`。
- [协议](../../benchmarks/preregistrations/cpp-build-harness-update-repaired-comparison-flash-v1.md)、[材料](../../benchmarks/fixtures/harness-update-repaired-comparison-v1/tasks.json)、[manifest](../../benchmarks/manifests/cpp-build-harness-update-repaired-comparison-flash-v1.json)。
- 原18项目×两组，共36槽；两组Harness/模型/源码/任务/顺序不变，无成功方案复用、无动态经验库，模型均从零规划。新结果是原项目集重新评价，不增加独立样本。
- 统一使用#816执行基座；smenu/quickjs/zstd参考采用上一阶段真实构建验证后的正确检查。其余参考不变，不向libtasn1注入特定补救命令。原E58和论文v0.12不修改。
- 入口隔离加载原已验证调度/计费/分析模块，独立身份和manifest，不改旧模块全局配置。8项必要检查确认材料差异、两组策略一致、36槽分母、默认检查不触Provider；Ruff通过。真实源码归档SHA全部核对，Docker运行时就绪。不重复已有四项目工程构建。
- manifest SHA-256：`04c8d26e8838a96f38b9be1f6c2cac11e30975dae022c4968df4f4ce3d7d89aa`。
- 新增模型费用0，未读凭据，正式0/36。拟10美元硬上限、确认起8小时，旧批授权已用完；本批须先绑定费用和时窗。
- 授权后直接运行，统计全18项目完成情况、请求/Token/费用/耗时及阶段开销；失败保留、无自动重试、不补槽，未知用量/模型标识异常/清理失败即停。结果先交用户审核，不自动入论文。
