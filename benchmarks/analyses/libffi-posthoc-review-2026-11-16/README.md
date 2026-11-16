# libffi 后验审查自主观察

身份`cpp-build-libffi-posthoc-review-flash-v1`，一个已暴露项目的一次从零路径，结果待用户审核，未入论文、不增E57分母。

[报告](../../../docs/research/2026-11-16-libffi-posthoc-review-autonomous.md)、[摘要](summary.json)、[轨迹](trajectory.json)、[语义审查](source-review.json)、[封存](seal.json)。

统计按events.jsonl的agent.started区分初始与三次恢复，逐响应汇总Token/Decimal费用；31请求/响应序列闭合，31模型标识均deepseek-flash，费用0.1493766美元。真实查询按recovery.environment_query计19次，工具尝试23次；不把拒绝查询算实际执行。全部454原输入核验SHA、mode、link；78份源码/材料快照核对运行revision；主/重建4个容器引用确认不存在。

主库/交付/干净重建完成、246.06秒、原输入未变，但新增兼容宏固定检测值，source_review仍待定，不批准为已验证经验；运行候选配方文件不等于语义批准。本轮未重现上一轮原文件变化拦截，也不能由独立单例成本差证明改进因果。完整原件与inventory指针见报告。
