# 统一基座18项目Harness比较准备

Issue #826；身份`cpp-build-unified-base-harness-comparison-flash-v1`。

用户接受在统一修复后执行器上重新比较原18项目，两组各一次、共36槽。沿用E59项目、源码、镜像、参考及交替顺序；LH_v0_common/LH_v1的规划与恢复差异完全保留。PR822为两组共同基座，不新增Harness提案或组件。

独立入口复用既有调度、预算、模型、验收和封存；新manifest SHA-256为`31ee49a2a7a8de2f6c37ef8883c50cfafcfc3e2ced2fefaa5c46e245c2ee8157`。三个针对性测试验证项目/排期/Harness保持、无授权先停止及两组18项目分母；全部通过。源码归档SHA核对、Docker就绪、Ruff及diff检查通过。pytest清理历史临时目录时有旧root文件权限告警，本次三项测试通过，未修改这些旧目录。

准备阶段无Provider、无凭据读取、无新增构建，不重复已有参考资格。拟10美元/确认起8小时；本批费用及时窗尚待确认。无自动重试、不补槽，未知用量/模型身份异常/cleanup失败停止。结果先审核、不自动入论文；旧完整比较及三项目观察保留，新结果不与旧槽拼接、不增加独立样本。入口及详细限制见[协议](../../benchmarks/preregistrations/cpp-build-unified-base-harness-comparison-flash-v1.md)。
