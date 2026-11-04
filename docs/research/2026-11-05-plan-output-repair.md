# 规划方案接收修复与规划模型对照准备

2026-11-05，Issue #685。当前阶段为工程修复，新增模型支出0；真实模型效果以独立的`cpp-build-planner-model-comparison-v1`结果为准。

## 修复内容

原E43的7次失败均在规划出口：6份正文方案结构有效，1份工具参数语法错误。`propose_simple`不再启用旧meter的“每响应必须有有效工具调用”判据，原始响应、模型身份、截断和用量检查保持。工具方案继续用LangChain ToolStrategy校验；单一完整正文JSON通过同一SimpleBuildActions校验才可接收，不补字段、猜括号或从散文中抽取命令。原正文允许完整的JSON代码围栏。

正文、工具schema和invalid_tool_calls共享一次显式反馈机会，第二次错误停止；服务异常不进入纠正，不重试。无效工具调用仅在后续上下文中表示为错误数据，避免悬空调用ID，原响应仍单独保存。规划提示词明确区分“工具参数示例”和“通过工具提交”，不增加任务目标或独立验收要求。

共同执行器新增可选的固定恢复模型与按实际响应标识分项计价，以便只改变初始规划路由；每响应只计费一次，身份异常按最高单价保守记录后停止。下一响应按Token上界和最高单价预留，不把已有历史经验的制备费重复支付。

## 验证与证据

52项相关检查通过，覆盖原7份失败响应、合法正文、语法错误、正文与工具错误共享纠正额度、服务异常不续问、真实Responses API工具/身份/计量适配，以及既有上下文、经验和Workflow行为。Responses使用本机MockTransport，0真实请求；不把模拟结果当RichLab效果。改动代码Ruff检查、后端格式和diff检查通过，未重跑旧资格链或全量产品测试；合并仍须相关CI。

四份代表性响应驱动真实Docker构建：jsoncpp/原槽2、highwayhash/原槽7、libite/原槽13的正文直接接收；libsrtp/原槽3先反馈语法错误，再由脚本提供同项目另一原正文方案。四条均通过主要构建、完整作者测试、交付、干净重放、原源码保持和cleanup。共5次零Token脚本响应，不能补判E43成功或估计模型收益。

原件：`/home/yiwei/.codex/outputs/forge-plan-output-engineering-v1`，封存inventory `0bea80ebf939aa082dae7efef4de3e6a584058e9346750d0bd6c11c9df17cf67`；7588普通文件、44链接、63068550字节。会话及driver在`/home/yiwei/.codex/outputs/forge-plan-output-session-v1`。旧E43原件与终态保持不变。

## 真实对照

[协议](../../benchmarks/preregistrations/cpp-build-planner-model-comparison-v1.md)固定四项目×两重复×Flash/RichLab规划，共16槽，两组均为相同经验Forge，恢复固定Flash。用户本轮明确允许RichLab，新增费用自行限定2美元、正式启动起2小时，0自动重试，未知用量/身份异常/清理失败停批。RichLab请求gpt-6-astra，沿用已接受的gpt-5.6/gpt-6-astra响应标签并披露，输入输出各1美元/百万Token，不称官方模型排名。正式结果尚未观察。
