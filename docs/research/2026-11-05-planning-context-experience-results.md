# 改进规划上下文后的16次经验增量比较

2026-11-05，Issue [#683](https://github.com/WWFXL/Forge-AutoCompiler/issues/683)。真实数据采集和结果分析已完成；固定16/16槽终结，0未启动或未闭合槽，无自动重试、补槽或扩批。**基础Forge完整6/8，经验Forge完整3/8；当前组合不支持经验的整体收益。7次未完成均在规划交付前后停止，未执行构建；其中6份正文JSON通过原方案schema的只读校验。** 原结果保持，不把事后可解析改写为构建成功。

## 问题、方法与版本

身份`cpp-build-planning-context-experience-flash-v1`，见[固定协议](../../benchmarks/preregistrations/cpp-build-planning-context-experience-flash-v1.md)及[manifest](../../benchmarks/manifests/cpp-build-planning-context-experience-flash-v1.json)，候选SHA `7a59cc565c2bcfc0ca751b634424e0d926e5d6580a72a66f7c32574f4781bd2b`。jsoncpp/libsrtp/libite/highwayhash×两重复×基础/经验Forge，各8次；第二重复反转各项目方法顺序。四项目因已见问题选入，全部开发暴露，两个重复不是八个独立项目。

两组共同使用精简方案schema、对话保留/容量压缩、重复读取收敛及一次原生结构纠正，均为deepseek-flash thinking low、相同公开简洁目标/源码/镜像/2CPU、只读工具、Workflow与方案式恢复。经验组每任务开始检索一次，从同一旧12轨迹/8族/24条库取最多两条、4096字节条件建议，无更新或新提炼、无同项目方案复用。个人知识库不注入正式Agent。只比较共同Harness下的经验增量，不隔离每项修复的因果。

准备PR682的三项直接check-run均SUCCESS，merge `cea792980cb9b72d117bfb79bf80a252a8b52321`，Issue681已关闭。运行HEAD `d7902250249149aa43ee1d3858564b0717f0cd5e`与merge完整Git tree相同；代码和依赖按manifest保持到封存。CI汇总接口曾滞后，依据同head的逐项check-run完成合并；相关记录在会话`prepared-ci-direct.json`和`prepared-publication.json`，没有绕过检查。后续结果分支提交不冒充运行revision。

## 全分母结果

|指标（各计划/观察8次）|基础Forge|经验Forge|
|---|---:|---:|
|初始方案交付|6/8|3/8|
|主要构建完成|6/8|3/8|
|完整任务完成|6/8|3/8|
|规划交付停止；后层未观察|2|5|
|模型请求，全部为初始规划|21|22|
|输入 / 输出Token|191719 / 5743|226816 / 5346|
|在线保守估费，美元|0.0644073|0.0744600|
|累计全流程分钟，包含失败|5.85|3.27|
|源码读取 / 同path与start_line重复|16 / 0|15 / 1|
|实际方案格式纠正 / 恢复请求|0 / 0|0 / 0|

经验组在线费高15.6%、少完整3次，不支持整体优势。它的累计时间较低，但五次早停远短于完整构建，不能当作加速收益。作者测试、交付、完整clean replay各9通过/7未观察，源码终态9通过/7未观察；cleanup16通过。9次接收有效方案后全部完整，零实际失败恢复，不证明状态选择或恢复的独立增量。

|项目（各方法2次）|基础完整|经验完整|
|---|---:|---:|
|jsoncpp|2/2|1/2|
|libsrtp|1/2|0/2|
|libite|2/2|1/2|
|highwayhash|1/2|1/2|

共同完整的jsoncpp第二重复、libite第一重复、highwayhash第二重复仅3对：基础/经验费0.0182097/0.0169758美元，经验低6.8%；累计150.06/146.81秒，低2.2%，请求7/6。这是保留的条件性局部观察，不能覆盖全16槽负向结果。libite第一重复经验读取2次对基础4次，请求3对4、费低27.6%；第二重复经验却因正文提交被拒，不能称稳定收益。

## 为什么未完成：共同出口遗漏

|槽|项目/方法/重复|原响应事实|原终态|
|---|---|---|---|
|2|jsoncpp/经验/1|方案放在正文；原JSON通过SimpleBuildActions校验|规划停止，构建未观察|
|3|libsrtp/经验/1|调用SimpleBuildActions，但参数末尾多一个右大括号，成为invalid_tool_calls|规划停止，构建未观察|
|7、8|highwayhash/经验、基础/1|两份正文JSON均通过原schema校验|规划停止，构建未观察|
|11、12|libsrtp/基础、经验/2|两份正文JSON均通过原schema校验|规划停止，构建未观察|
|13|libite/经验/2|正文JSON通过原schema校验|规划停止，构建未观察|

直接原因是继承的`CanaryMeter.capture_response`在`plan_agent_canary.py:101`附近要求每个规划响应存在有效`message.tool_calls`，否则立刻抛出“规划未返回工具调用，停止而不自动续问”。这发生在LangChain ToolStrategy的结构纠正之前：六个正文方案没有工具调用，另一个JSON语法错误被SDK放进`invalid_tool_calls`，七次都未到本轮新增的schema反馈。因此所有`simple.proposal_rejected`及显式纠正次数为0，不能宣称本轮已真实验证格式纠正效果，也不能把七次都称空方案或模型不会构建。

这属于本轮实现覆盖不全。原jsoncpp槽2已经写出`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release`及`cmake --build build --parallel 2`，只是正文提交未被接收。事后分析严格对原正文执行`json.loads`和同一`SimpleBuildActions.model_validate`，没有删括号、补字段、运行命令或修改原响应；六份结构有效不代表它们实际编译、测试或交付通过。该诊断与16槽完全重叠，不新增实验分母。

## 探索与经验的实际观察

经验组8次均检索一次、无弃权，合计22682字节，单次2321–3820字节；覆盖只表示词项匹配，不等于语义适用或实际采纳。两组总源码读取16/15，重复0/1；未出现旧版50请求循环，但早停缩短了探索，不能把减少请求全归收敛机制。容量压缩在6次请求前发生，最多累计淘汰3组；一次到两轮无进展提醒，强制只输出工具实际0次。经验是否改变了输出渠道选择仍需独立检验，不能从5比2的接口失败直接推断语义负迁移。

[历史E42重叠子集](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/historical-development-subset.json)取相同四项目两Forge的16槽，基础/经验完整6/8、4/8，请求32/177；只是问题驱动选择的历史对照，不是新分母或单变量比较。本批基础仍6/8、经验3/8，不声称新版稳定性提高。测试入口适配与其他共同改动也不能通过新旧完整率相减估效果。旧E01/E30/E33/E35–E42及论文v0.6保持。

## 费用、时窗与证据

用户回复“授权此次执行”，承接10美元硬上限/确认起4小时。北京时间2026-11-05 00:11:36–04:11:36，准备和CI等待计入；唯一PID2757267于00:29:33启动，采集约551.95秒，00:38:49已封存并退出。43完成响应、输入418535/输出11089、429624记录Token，估费0.1388673美元、未知用量0，响应模型均deepseek-flash。按输入0.30/输出1.20美元每百万Token、全输入未命中保守估费，非实际账单。原库历史制备费0.095129美元另列、不在本轮再支付；若一次计入经验侧则0.1695890美元。没有Astra请求、自动重试、追加提炼或余额扩批。

冻结raw：`/home/yiwei/.codex/outputs/forge-planning-context-experience-flash-v1`，inventory `749f9afc565dc56a115f55775826e0e3c7464cfaeb4cae097b1965e067d0d648`，20719普通文件/135链接/174881421字节。保存全部输入/原响应/用量/工具反馈/源码读取/方案、构建/测试/交付/replay日志及分层结果、冻结源码快照；封存工具已实际核对文件清单。失败原件不改。

会话`/home/yiwei/.codex/outputs/forge-planning-context-experience-session-v1`保存授权、CI滞后/重开记录、逐项CI、merge/tree映射、launch/run.log、最终费用与资源检查。50项容器名称/ID（16编译+9重放各名称与ID，非50个独立容器）实查均不存在；未新增托管镜像。全部逐响应Token/请求/费用与结果相符，账本完整、无活动Provider。

论文材料：[全表CSV](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/slots.csv)、[分析](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/analysis.json)、[配对](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/paired.json)、[原响应/费用核对](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/response-verification.json)、[失败诊断](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/failure-analysis.json)、[探索/经验](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/process-analysis.json)、[共同完整](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/common-complete.json)、[PDF图](../../benchmarks/analyses/cpp-build-planning-context-experience-flash-v1/planning-comparison.pdf)。用于第5章经验方法的边界、第6章完整比较及接口失败案例，不冒称论文全文/Word/PDF已更新。

## 下一步

优先修两Forge共同的规划出口：原正文只有在严格通过同一schema后才作为候选接收；JSON工具参数解析失败应进入既定的一次显式计费格式反馈，服务错误仍不重试。用这七个原响应做离线回放，保留原终态，不增加分类器、Agent角色或新经验库。修复后再定义独立比较，不能在本批途中换实现、回填原失败或使用剩余预算续跑。本次未准备新付费身份或新增授权请求。
