# libffi容器查询工具自主观察

身份`cpp-build-libffi-environment-tools-flash-v1`，1个已暴露项目×1次从零路径，非新holdout或原E57补槽。结果尚待用户审核，未写论文。

[报告](../../../docs/research/2026-11-16-libffi-environment-tools-autonomous.md)、[摘要](summary.json)、[方案/查询轨迹](trajectory.json)、[封存](seal.json)。

统计从原始`agent/events.jsonl`按`agent.started`划分初始/三次恢复；逐个`model.request_completed`和`model.cost_estimated`汇总Token和Decimal费用。请求/响应编号1—54闭合，响应模型均deepseek-flash。工具调用来自`tool.started`，实际容器查询来自`recovery.environment_query`；无效/超限只记工具尝试，不算真实容器查询。重复读取为相同read_source参数，重复查询为相同操作/名称/范围/类型；不直接认定跨状态重复都无用。

原文件检查同时比较SHA与mode：config.guess内容不变、权限0644→0755；config.sub内容变化。初次原件`analysis-derivation.py`只列内容变化，最终`verification.json`及本摘要补齐权限比较，不覆盖原运行summary。阶段标签沿用原件，主构建/交付/重建为未观察；总任务未完成。

54次、0.2957706美元、497.67秒，实际查询36次，仍未定位真实开发包。与旧成功观察的较低投入不当效果提升；不重跑、不自动修改论文。原件目录及inventory SHA见报告。
