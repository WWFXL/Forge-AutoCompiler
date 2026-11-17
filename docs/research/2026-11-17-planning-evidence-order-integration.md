# P5规划Harness接入与三系统观察准备

跟踪Issue #830。用户已审核[P5完整提案](2026-11-17-planning-evidence-order-proposal.md)，候选指纹568429c41480d2208cc9bbfb14b0a1a173331d0e9874629fc550793a017f98b4保持。本轮是工程接入与实验准备，0Provider、新增模型费用0，不修改论文。

## 接入方式

现有`forge_harness_update_comparison.executor`增加显式可选的planning_harness参数；默认仍是P0，已有入口行为保持。新入口`scripts/forge_planning_evidence_order_observation.py`使用该参数传入P5，其余采用当前LH_v1政策和恢复Harness。没有改SIMPLE_PROMPT、工具权限、执行器状态判断、输出schema、纠正次数或验收。

P5只在初始propose_simple应用；恢复时既有PlanningHarness接口不追加该指导，原LH_v1恢复指导和诊断能力保持。测试实际经过LangChain Agent图，确认P5文本送达请求系统消息；这只是脚本响应的接线验证，不证明Flash会遵循路径。

## 已准备的下一观察

[协议](../../benchmarks/preregistrations/cpp-build-planning-evidence-order-observation-flash-v1.md)、[manifest](../../benchmarks/manifests/cpp-build-planning-evidence-order-observation-flash-v1.json)。身份`cpp-build-planning-evidence-order-observation-flash-v1`，libuv/quickjs/libunwind各一次，覆盖CMake/Make/Autotools，共3槽。现有任务、源码归档和独立参考逐项核对；无成功方案复用、无动态经验检索、不提供已知修复指令。

这是三个已知项目的读取与收敛观察，不是新的对照效果。拟使用deepseek-flash、费用硬上限2美元、确认起2小时，无自动重试、不补槽；未知用量、模型标识异常或清理失败停止。正式比较仍需另选与开发历史隔离的新项目集，两组同基座，仅切换P0/P5。

当前没有本身份付费授权、尚未读取模型凭据或启动真实模型构建。旧36槽费用授权不能扩用于本批。结果先交用户审核，不自动入文。

## 本轮验证

- 12项针对性与相邻测试通过，包含真实Agent图提示送达、P0/P5除规划指导外执行参数一致、恢复保持、候选变化拒绝、新授权缺失拒绝、未启动槽保留未观察。
- Ruff及git diff --check通过。CLI --prepare与--check-prepared通过，实际核对三个源码归档哈希；不调用Provider。
- pytest退出时发现其清理既有历史临时目录的权限警告，路径在旧test_real_local_recovery_build0目录；本轮测试通过，未删除或更改历史目录。
- 尚未运行真实模型或新的Docker构建，不声称提高完成率、减少请求或解决dsvpn/zstd输出根因。

下一项：绑定本身份新预算与时窗后，仅执行固定三槽并分析真实轨迹，再决定正式新项目比较。
