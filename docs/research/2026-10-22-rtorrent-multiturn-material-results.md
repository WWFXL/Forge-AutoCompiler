# rtorrent 多轮材料可逆共享资格

#591 是基础设施/工程修复。旧真实 canary 的两个策略在后续消息超过 50000 字节时停止；本阶段只修复完整材料的表示，保留原任务、源码、测试、状态、费用和验收。新表示共享完全相同且至少256字节的 JSON 对象或列表，表内保留完整值和 SHA；不删除字段。先展开原文本因子和共享文本，再展开 JSON 值；拒绝保留字段冲突、悬空/含糊引用、表篡改及整体 SHA 错误，无收益时保留旧表示。

固定 `cpp-build-rtorrent-multiturn-material-gate-v1` 的分母为旧v2全部28实际请求及两个最后停止材料，62来源文件SHA、270代码组件前瞻冻结。30/30资格，0未观察，0 Provider/真实模型Token/费用/未知用量。经过真实 SharedValueMeter→ContextCanaryMeter→CanaryMeter，handler只返回一次 usage0 脚本响应；每例完整task/current_plan/state/source_packet/read_index/recent反馈/预算逐值还原，系统提示及工具schema相同，原50k/8k保持。最大消息48877字节，两个停止案例48475/48877字节。

停止材料用最后projected、最后三个tool.completed及终态usage重建；elapsed是末snapshot数值，不是原未落盘请求的精确时间或字节。历史预算作为显式fixture注入，不重跑旧工具，不伪称真实历史回放。30个脚本响应不当真实模型响应；本阶段未执行完整新构建，不能证明模型理解新表示或三策略成功率，也不能把不同工程版本前后差当因果方法增益。

运行release `0cddecf7d32e75845901b7c958df426b28628300`；raw `/home/yiwei/.codex/outputs/forge-rtorrent-multiturn-material-gate-v1`；typed inventory `2174ec7e96f6949c74013f6a9aa5d08a8275e38be3f47104722cc2af0158f36f`，463文件/0链接/14554111bytes。派生分析 `benchmarks/analyses/cpp-build-rtorrent-multiturn-material-gate-v1-results.json`；同名manifest/preregistration为资格合同。

会话 `/home/yiwei/.codex/outputs/forge-rtorrent-real-session-2026-10-21` 的 `independent-material-gate-audit.json` 用独立stdlib核验全量清单、父证据、62来源SHA、Git组件及source-snapshot、逐值/预算/反馈还原、消息/schema大小、原系统提示及每例一次零Token脚本生命周期，valid。14新回归、产品2469 passed/44 skipped/27 warnings、Ruff/614文件格式检查通过，历史pytest权限告警保留。最终HEAD三CI成功后只合科研依赖分支；发布状态以GitHub及会话final-material-publication-audit.json为准。

下一步准备独立新版本真实canary，保持已资格共同任务/模型/执行与验证/资源，全部读取、初始规划、失败、恢复和编码墙钟计入。原用户10美元/UTC2026-10-21 15:30:52–19:30:52（准备计入）/请求不限/无自动重试，旧v2已花0.82323780美元必须扣除；新授权绑定旧阶段闭合账本与原截止。不补旧失败或混版本分母；RQ3/P2/主线及用户HTML保持。
