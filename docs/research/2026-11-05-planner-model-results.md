# 规划方案接收修复后的模型路由比较

2026-11-05，Issue #685、PR #686。比较的是同一经验Forge中初始规划路由的选择；恢复统一Flash，不改变Workflow、经验库、任务目标或独立验收。RichLab请求`gpt-6-astra`，两批实际均响应`gpt-5.6`，按用户接受的披露条件执行，不证明后端为官方Astra。

## 首批完整16次：输出交付正常，保留一次上下文容量失败

身份`cpp-build-planner-model-comparison-v1`，四个已开发暴露项目jsoncpp/libsrtp/libite/highwayhash×两重复×两种规划，各8次、全部16终态。运行release `61a1128bd5e44c10efa27f1d9dd0e56683647bf2`；[协议](../../benchmarks/preregistrations/cpp-build-planner-model-comparison-v1.md)、[manifest](../../benchmarks/manifests/cpp-build-planner-model-comparison-v1.json)固定共同Harness、来源族隔离的旧24条库、每任务一次检索、两条/4096字节、2CPU、作者推荐/default主要构建与独立作者测试/交付/clean replay。

|指标（各8次）|Flash规划|RichLab规划|
|---|---:|---:|
|方案交付 / 主要构建 / 完整完成|8 / 8 / 8|7 / 7 / 7|
|全部请求（均为初始规划）|27|15|
|在线保守估费，美元|0.0954420|0.1898260|
|累计全流程秒|425.60|428.29|
|初始规划累计秒|51.48|103.61|
|源码读取|20|8|
|格式纠正 / 恢复请求|0 / 0|0 / 0|

15份接收方案均通过工具提交，并完成主要构建、作者测试、交付、重放和原源码保持；正文接收与一次纠正没有在本批自然触发，相关实现只由原响应回放验证，不冒称真实纠正效果。全部cleanup通过、未知用量0。Flash较少费用且多一次完整，RichLab请求/读取更少但费用更高，不能把请求下降等同效率收益。

唯一失败为RichLab/libsrtp/第一次重复：第一次模型请求返回三个合法读取调用（README指定区间、根目录、Makefile.in），但下一请求前初始消息32624字节、最新响应4677、工具结果13105，超过49KB容量；初始源码包单独占23764。系统拒绝唯一完整工具组，尚未进入构建，无模型格式错误或功能测试失败。RichLab第二次libsrtp重复完整通过，不推断为模型不会构建。

原件`/home/yiwei/.codex/outputs/forge-planner-model-comparison-v1`，inventory `8a83618da032dd3b91eafe89704f9b4804de707a6f2949ad92f29ea877def596`，28091普通文件/176链接/241853792字节。42真实响应、487686记录Token、新增估费0.2852680美元；逐响应与阶段计费复算一致。[分析](../../benchmarks/analyses/cpp-build-planner-model-comparison-v1/analysis.json)、[16行表](../../benchmarks/analyses/cpp-build-planner-model-comparison-v1/slots.csv)、[费用复算](../../benchmarks/analyses/cpp-build-planner-model-comparison-v1/response-verification.json)、[项目内配对](../../benchmarks/analyses/cpp-build-planner-model-comparison-v1/pairs.json)保留完整分母。

## 容量修复与独立确认

首批完成封存后，共同上下文改为容量不足时优先移出可重新读取的初始源码片段，保留路径/哈希/截断说明、公开任务和最新完整工具交互；不扩大49KB限制、不截断最新工具结果、不修改经验或验收。原工具仍可按需补读，压缩不调用额外摘要模型。该修复适用于两规划路由。

53项相关检查通过；首批失败的原三工具响应已通过零Provider实际构建回放，发生一次初始材料压缩，主构建/作者测试/交付/replay/源码/cleanup全部通过。工程原件`forge-plan-capacity-engineering-v1`、inventory `f26e0d91f3fe8216f62339673c579f39e4b29a9301f9a09f628f283dfa10f817`，0新增Token。随后固定独立`cpp-build-planner-model-confirmation-v2`同样16槽，见[协议](../../benchmarks/preregistrations/cpp-build-planner-model-confirmation-v2.md)。两批共享原2美元总上限与原截止，不回填首批失败、不合并分母、不从跨批差值估计压缩的因果效果。

## 第二批独立16次：两路由全部完整，Flash费用和时间更低

身份`cpp-build-planner-model-confirmation-v2`，运行release `3138d020d9b9909483ec0ce0682a59e861b3a168`；[manifest](../../benchmarks/manifests/cpp-build-planner-model-confirmation-v2.json) SHA `5793ab1267a3919a082f181dc490d6e3828f261e7e215167e66b39196c7dce76`。仍为四项目×两重复×两规划路由，16/16终态、0未观察槽，没有替换或重跑首批槽。

|指标（各8次）|Flash规划|RichLab规划|
|---|---:|---:|
|方案交付 / 主要构建 / 完整完成|8 / 8 / 8|8 / 8 / 8|
|全部请求（均为初始规划）|23|19|
|在线保守估费，美元|0.0810804|0.2525810|
|累计全流程秒|422.20|503.45|
|初始规划累计秒|48.00|127.64|
|源码读取|19|9|
|格式纠正 / 恢复请求|0 / 0|0 / 0|

16份方案均通过工具提交，主要构建、完整作者测试、交付、clean replay、原源码保持和cleanup全部通过。三槽实际触发初始材料压缩：Flash/libsrtp两重复分别2、5个片段，RichLab/libsrtp第二重复2个；这里取每槽累计字段的最大值，不能重复累加各次请求记录。没有再次出现容量停止。RichLab/libsrtp首重复这次未触发压缩，故不能将其相对首批通过直接归因压缩；两批仍分开报告。

RichLab比Flash少4次请求、少10次源码读取，但费为3.12倍、累计全流程时间高19.2%，初始规划时间为2.66倍。不同费率、输入/输出规模、API与服务时延共同影响成本和时间；请求/读取数减少不能代替实际效率。当前结果支持在这些开发项目上继续使用Flash默认规划，没有证据要求全面切换RichLab。由于两组没有恢复、格式纠正或正文接收，本批不估计这些机制的自然增量，也不证明经验相对无经验有收益。

原件`/home/yiwei/.codex/outputs/forge-planner-model-confirmation-v2`，inventory `2ffaab2d1b7a9ed689c4ca089c7233f47c26797c8b28f2236c5ed53627326970`，30581普通文件/176链接/255628597字节。42真实响应，输入492507/输出10764、共503271记录Token，估费0.3336614美元、未知0；[分析](../../benchmarks/analyses/cpp-build-planner-model-confirmation-v2/analysis.json)、[16行表](../../benchmarks/analyses/cpp-build-planner-model-confirmation-v2/slots.csv)、[项目内配对](../../benchmarks/analyses/cpp-build-planner-model-confirmation-v2/pairs.json)及[逐响应费用复算](../../benchmarks/analyses/cpp-build-planner-model-confirmation-v2/response-verification.json)保存原分母、实际响应标识与上下文压缩字段。逐响应、槽总费用与初始/恢复分项一致。

两批新增费合计0.6189294美元（只合计支出，不合并效果分母），未触达自行设定2美元上限或原UTC19:24:06截止。正式进程已正常退出，无活动Provider，无自动重试/补槽或扩批。会话`forge-plan-output-session-v1/resource-check.json`在四个已封存原件目录收集73条compile/replay记录、146个名称/ID，与实际Docker列表比对全部不存在；没有删除无关资源。历史失败与论文v0.6全文保留。

## 解释边界与论文用途

第4/5章可说明规划交付、有限纠正与上下文管理的实现；第6章可作为规划路由敏感性、请求/费用差异与工程失败案例，分别登记E44/E45。四个项目已开发暴露、两重复不当八个独立项目；两条路由还包含API/服务差异，不作官方模型排名、未见泛化或经验/状态独立增量。旧E43等终态与论文v0.6保持，工程回放不计入真实比较分母。下一步回到固定Flash下的系统/经验增量比较，避免以新增组件或继续换模型代替论文主问题；本轮余额不扩新付费身份。

用户本轮明确要求按顺序修复并允许RichLab；开发助手自行限定新增2美元、正式启动起2小时。首批授权从UTC2026-11-04 17:24:06至19:24:06，全部初始/失败/纠正/恢复计费；Flash输入/输出0.30/1.20美元每百万Token（全输入未命中保守估费），RichLab沿用用户提供输入输出各1美元/百万Token。历史经验制备费0.095129美元单列、不再次支付。无服务重试、补槽或用余额扩无关实验。授权/启动/工程与发布收据保留在`forge-plan-output-session-v1`；首次系统Python3.10生成授权文件失败发生在凭据/正式目录前，后改用项目Python3.12，原日志保留。
