# 规划方案接收修复后的模型路由比较

2026-11-05，Issue #685、PR #686。比较的是同一经验Forge中初始规划路由的选择；恢复统一Flash，不改变Workflow、经验库、任务目标或独立验收。RichLab请求`gpt-6-astra`，首批实际均响应`gpt-5.6`，按用户接受的披露条件执行，不证明后端为官方Astra。

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

## 解释边界与论文用途

第4/5章可说明规划交付、有限纠正与上下文管理的实现；第6章可作为规划路由敏感性、请求/费用差异与工程失败案例。四个项目已开发暴露、两重复不当八个独立项目；两条路由还包含API/服务差异，不作官方模型排名、未见泛化或经验/状态独立增量。旧E43等终态与论文v0.6保持，工程回放不计入真实比较分母。

用户本轮明确要求按顺序修复并允许RichLab；开发助手自行限定新增2美元、正式启动起2小时。首批授权从UTC2026-11-04 17:24:06至19:24:06，全部初始/失败/纠正/恢复计费；Flash输入/输出0.30/1.20美元每百万Token（全输入未命中保守估费），RichLab沿用用户提供输入输出各1美元/百万Token。历史经验制备费0.095129美元单列、不再次支付。无服务重试、补槽或用余额扩无关实验。授权/启动/工程与发布收据保留在`forge-plan-output-session-v1`；首次系统Python3.10生成授权文件失败发生在凭据/正式目录前，后改用项目Python3.12，原日志保留。
