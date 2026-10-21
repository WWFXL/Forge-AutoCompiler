# rtorrent 三版真实请求会话连续性审计结果

Issue #599；结果分析完成。后验固定v2/v3/v4全部114个实际请求、105个后继转换；没有抽取有利片段或修改旧raw。全程0新凭据/Provider/真实Token/费用/构建。来源inventory、独立真实审计、执行组件和既有实现SHA在正式普查前冻结；事前开发已见结果，因此明确不称结果盲预注册。

| 旧身份 | 实际请求 | 后继转换 | 原生前AI保留 | 完整前工具返回保留 | 原样追加后≤50k | 最大追加字节 |
|---|---:|---:|---:|---:|---:|---:|
|cpp-build-rtorrent-common-canary-v2|28|25|0|0|3|81575|
|cpp-build-rtorrent-common-canary-v3|31|28|0|0|4|76154|
|cpp-build-rtorrent-common-canary-v4|55|52|0|0|7|92271|

全部114请求只含单Human权威状态包，105个后继转换均未原样保留上一AI和配对ToolMessage。原始响应、工具反馈仍完整保存，源码工作集/最近三条反馈也可能带部分既有信息。因此结论是“原生会话没有传回”，不能推成“模型完全没有记忆或信息”。

在实际原请求后直接追加完整上一AI（包括reasoning_content与metadata）和全部唯一配对ToolMessage，14/105满足原50k，91/105超限，最大92271字节。此为未发送的机械测量：没有去重当前source_packet/最近反馈，没有改变轮数或定义新接口，不证明合理的原生保留不可行，也不提供Token、费用或效果预测。首请求没有前轮分母；仅保存而未开始的文件另列，本次为0。

现有依赖已提供可参考的成熟约定：LangChain SummarizationMiddleware保留近期AI/Tool配对，_find_safe_cutoff_point避免从工具返回中间截断；本身份只静态读取，不调用其模型摘要。项目PatchedChatDeepSeek在收到原生AI时能恢复reasoning_content，已有PlanThinkingDeepSeek经离线占位交互序列化回归确认。当前材料middleware在它之前重建单Human包，因而不能把适配器具有能力等同于当前实验实际保留。

这支持优先处理共同Harness的会话与证据保留，避免把循环读取直接归因于模型或规划方法。它不证明该问题导致了失败、不证明修复提高成功率，也不改变旧三版失败、strict分母或已见development单族边界。硕士主线保持，下一步是三策略共用原生会话接口的免费资格：完整AI/Tool配对、原任务/源码/测试与执行器边界、所有Token及费用仍可计量；材料和响应资源若调整须在新身份前共同冻结，不能按观察到的方法结果回调。新真实比较只在新版本内部解释，不能用前后工程版本差异当因果效果。

证据：
- release `f6e59a969069b1286effb9143b38294e86c304bd`；候选0501dc39544ffcdde6e554503748b2c22f455f5962974055bd04a6aba2d80265，8组件。
- raw `/home/yiwei/.codex/outputs/forge-rtorrent-context-continuity-audit-v1`；inventory `f3128a16f5d740e88571c2254d07d7ed72cce66eab2ed84d09ba2219178bac4a`，11文件/156948bytes/0链接。
- 独立stdlib重算全部来源/新全量清单、Git提交与组件字节、114实际请求/105完整工具配对/逐字段字节口径，valid=true。收据forge-rtorrent-real-session-2026-10-21/independent-context-audit.json。
- 10针对性回归、产品2531 passed/44 skipped/27 warnings，Ruff610后端文件及新脚本检查/格式/CLI通过；历史pytest临时目录权限告警保留。最终结果HEAD三CI成功后只合科研依赖分支，发布真源为GitHub/final-context-publication-audit.json。
- 原UTC2026-10-21T19:30:52截止不延长；三paid已闭合，累计名义$3.27044256，未新增模型费用。RQ3/P2/原验收/主线/用户HTML保持。
