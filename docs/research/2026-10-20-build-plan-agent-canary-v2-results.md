# 双臂真实开发canary v2：八臂严格完成，状态修订尚未激活

跟踪 #489；独立身份 `cpp-build-plan-agent-canary-v2`，运行代码为 `5512ff60d78dd6227169ca7186c930040a926377` 及原始目录保存的组件快照。8/8固定单元均strict completed，固定完整测试、精确交付、clean replay、源码未变、cleanup与独立完整性/用量审计通过。决定为 **`proceed_to_state_transition_and_reference_task_qualification`**。

| 项目 | plan/tool严格终点 | 请求数plan/tool | recorded tokens plan/tool | 估算美元plan/tool |
| --- | --- | --- | --- | --- |
| miniz | completed / completed | 2 / 7 | 19,855 / 71,861 | 0.03079692 / 0.10121100 |
| md4c | completed / completed | 2 / 9 | 21,681 / 76,716 | 0.03899412 / 0.12170664 |
| pigz | completed / completed | 2 / 8 | 16,769 / 51,992 | 0.03943764 / 0.08437176 |
| libite | completed / completed | 1 / 10 | 10,645 / 90,523 | 0.02360820 / 0.12976788 |

plan合计7请求/68,950 tokens/$0.13283688，tool合计34请求/291,092 tokens/$0.43705728；双方均18条命令。该表只描述已见四开发任务、每格一次、指定本地Harness与模型预算下的观察，不报告总体节省比例、显著性、非劣或模型能力排名。工具Agent允许批量调用，真实进入构建并完成交付；不将它等同成熟Codex/Claude Code等Harness。

## 研究含义与尚未回答的问题

读取绝对路径别名、可恢复错误反馈及有界证据工作集通过真实接线；八臂没有因v1同类读取错误提前终结。但v1/v2材料和Harness不同，不能把两次结果差值当修复因果效果或方法增益。

四个plan臂都直接从ready_for_verification到verified，**交接与修订次数为0**。当前只证明正常构建任务的规划/执行/验证链路闭合，没有检验状态变化时的动作选择，也不能证明自适应规则或学习选择器有效。所有项目已用于人工参考和开发接线，不能当最终holdout。

严格验收未降低：原固定miniz CTest、md4c完整上游脚本、pigz make test、libite 21项make check均执行；每臂干净重放固定测试，交付路径集合、类型、大小和SHA-256相符，Session cleanup后completed。不同方法的中间构建路径/配方可以不同，不要求两臂二进制互相相同；每臂须与自己的干净重建精确匹配。

## 用量、封存和预算

41请求，324,194 input +35,848 output =360,042 recorded tokens，已知保守公开价估算 **$0.56989416**，未知usage为0，费用不是实际账单。全臂成本均纳入，不按成功子集过滤。节点含验收墙钟合计plan319.864s、tool323.534s；单次、串行固定顺序且规模小，不据此宣称速度优势。

原始 `/home/yiwei/.codex/outputs/forge-plan-agent-canary-real-v2/`，3436普通文件/96链接/86,365,971 bytes；类型化inventory canonical SHA-256：
`31652865251842eebb49f8582fb22c96610da21d6a4f5339b31daa08a5613663`。
独立审计 `/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/plan-agent-canary-real-v2-audit.json`，valid=true，核验文件/链接全量、原始响应usage与费用、原始源码、固定oracle、Session/replay、精确交付和无残留容器。manifest SHA-256 `549dbbd1f9b28f5cfe2d012dce67406124428da912dc55230b9675d9b50a64b5`。

阶段$12预留已在封存成功后结算，不是实际支出。共享新增已知费用累计$0.74375004+$0.56989416=**$1.31364420**；另旧live测试未知费用预留$1，预算占用$2.31364420，无未结付费阶段。持续上限$20，截止北京时间2026-10-20 07:00不变。

本次工程验证：修复新增5项、零Provider真实Docker门禁8/8，默认产品1880 passed/44 skipped、Ruff与format通过。真实结束后未改运行组件；报告和当前状态更新不覆盖原始证据。#489发布仍需最新结果提交的三项实际CI成功后合入依赖开发分支，不等于进入main。

## 下一阶段

#492固定12候选来源目录已零Provider完成并独立审计；#493设计10项完整参考任务资格，两项外部来源不完整的候选保留暂缓。同时按#488设计零Provider状态变化/分层验证正负控制，先观察实际动作分歧，再决定是否增加状态规则或进入独立Provider比较。不会重复这四个正常全成功任务来制造恢复机制结论，也不重开任何已停止的旧identity。
