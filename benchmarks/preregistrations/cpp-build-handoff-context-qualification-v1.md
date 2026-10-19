# 接管材料投影零Provider资格

Issue #511，身份`cpp-build-handoff-context-qualification-v1`。这是观察#504失败后的独立工程资格，不是效果实验。固定只读#504 libverto-r2-plan源码、任务、方案与needs_handoff快照；不运行Shell、不修改源码或旧证据、不读取凭据、不调用Provider。

按原执行器规则重建材料，冻结观察的remaining_seconds不能还原实际毫秒级快照，因此明确称重建而非原请求字节复本。原ContextCanaryMeter和新增HandoffContextMeter接受相同脚本响应：复述原方案，仅检验实际LangGraph/middleware准入，不执行修订方案。原路径预期在50k消息门禁停止且0请求；投影路径预期1次零Token脚本请求、返回revision2且消息<=50k，工具schema<=8k、费用和请求限制沿用原实现。

投影仅移除state.handoff.recent_commands内重复output_tail，以其UTF-8字节数与SHA保存省略收据；顶层handoff近期三条预览仍保留，全部命令身份/状态、退出码、日志路径/原日志SHA、完成步骤、预算、完整任务/测试/方案不变。两份handoff身份错配则拒绝。核心材料仍超限则不调用模型，不增加限额。

9项针对性测试含身份错配、非破坏性投影与核心超限fail closed；另运行上下文相邻测试。父inventory和运行组件hash需前后不变；create-once独立目录封存原/投影包、请求响应、计量及代码快照。失败保留，不续跑旧身份。

截止沿用本轮UTC2026-10-19T23:00:00Z，原meter新请求预留1800秒；本资格在UTC22:30前执行。0Docker、0Provider，允许与真实构建同时进行只读材料验证，不能污染任何构建耗时比较。结果只能说明这份失败材料的准入阻塞是否消除，不证明真实模型会修复测试失败、提高成功率或节省费用；后续真实恢复须新身份/协议与授权时窗。
