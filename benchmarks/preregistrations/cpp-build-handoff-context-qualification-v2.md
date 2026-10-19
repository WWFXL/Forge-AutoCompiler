# 接管材料投影零Provider资格v2

Issue #511。v1的原/投影材料均准入（46410/32467字节），未复现#504超限，已封存且不修改。v1错误地仅重建首次handoff材料，没有此前读取索引和最终工具反馈，不能用来宣称修复成功。

v2固定同一#504 libverto-r2-plan，按request-9.json的任务/方案/权威状态/接管材料和读取索引，再应用最后三个tool.completed原文恢复工作集；真实LangGraph输入使用第九次AI工具调用和三个相应ToolMessage。系统提示词使用原第九次请求原文。只读原冻结证据，不调用源码工具重新取值，不读取凭据、Provider或Docker。

预期原ContextCanaryMeter在下一次总请求准入前超过50k而0脚本请求，HandoffContextMeter投影后1次零Token脚本请求，返回revision2但不应用、不执行构建。原50k消息/8k工具schema/预算门禁不变。失败保留，旧v1不替换。其余身份错配/核心超限规则沿用v1，9针对性及5上下文相邻测试已通过。

这是实际第十次请求前材料的重建；使用原第九次state.remaining_seconds与新计量器预算时间，不能称逐字节原请求。保留全部固定任务/方案/状态核心，原/投影仅在重复output_tail省略收据上不同。准入通过也不证明真实模型会交付有效修订、自然恢复效果或费用收益。UTC22:30前执行脚本请求，UTC23:00总截止；0Provider、0Docker、0凭据。父/源组件前后hash不变并create-once独立封存。
