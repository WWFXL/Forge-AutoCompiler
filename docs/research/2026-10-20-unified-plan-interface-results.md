# 工具/模型规划共享装配与恢复接口（#542）

## 状态和研究问题

当前是基础设施资格阶段：消除两种规划方式在固定测试、交付装配及失败恢复接口上的混杂，为新公平比较提供入口。工程门禁不能回答真实模型成本或成功率优势。硕士主线继续，接受小幅/条件性收益和代价，不要求所有指标同时胜出。

**共享契约门禁v2已9/9严格完成，独立审计valid=true；强工具新入口补验1/1严格完成并独立审计通过。正式36槽效果比较尚未运行，等待新的有效费用/时窗授权。**

## 实现后的共同契约

| 层 | 工具初始规划 | 模型初始规划 |
| --- | --- | --- |
| 任务 | 同一源码归档/commit/image、原完整测试、精确交付 | 完全相同 |
| 可生成内容 | 单根入口模板给出dependency/configure/build | 只读Agent返回同一BuildActions schema |
| 测试与交付装配 | 系统逐字段装入作者固定测试及共同delivery_command | 完全相同，模型不再抄写测试和暂存脚本 |
| 正常执行 | 同一CanaryWorkflow执行Shell，保留权威命令记录 | 完全相同 |
| 运行中失败 | 权威handoff→同一propose_actions→完整动作修订 | 完全相同，首次变化后失效重执行 |
| 初始无法生成 | 单独登记initial_abstention→同预算只读Agent | 本身即从只读Agent开始 |
| 严格终点 | 原源码、固定完整测试、精确交付、结构/哈希、同镜像clean replay、实际cleanup | 完全相同 |

`backend/packages/harness/deerflow/compile/unified_plan.py`定义共享装配及同一个恢复入口；`plan_delivery.py`定义共同可重放暂存。`BuildAction.role`仅允许三种构建角色，模型不能在该schema提交测试或交付步骤；同一`PlanTask.materialize`仍逐字段校验作者测试。过期handoff或不符合系统装配的当前方案在调用Agent前被拒绝；Workflow仍校验活动handoff、命令frontier和方案revision，Agent不能改权威状态或自行宣告成功。

恢复只保留实际成功且未变化的逻辑前缀；依赖/配置变更需要Agent显式清理缓存和旧产物，逻辑失效不自动等于物理重建。最终clean replay始终从空环境执行完整配方。暂存从仓库内寻找与交付basename相符的唯一ELF/ar候选；允许内部版本化链接指向真实普通文件，拒绝缺失/歧义/越界/悬空/循环，复制后交付仍为普通文件，不降低产物裁判。

底层复用历史run_arm并保留其逐臂旧标签；外层新身份/协议区分本轮工程门禁与未来前瞻比较，不修改旧证据或将历史canary变为效果。

强工具Agent保留原固定测试工具、批量Shell与无参数权威配方提交，属于整策略参照。它的工具与控制方式仍不同，不能说三个方法只差一个变量。

## v1主动停止和交付修复

v1 release `3dd1d2ef`运行期间，为公平比较核对libzip任务时发现交付接口缺口：libzip原冻结任务交付`libzip.so`，#508合格原工作区与replay均实际记录`libzip.so → libzip.so.5`，指向真实ELF。旧共同暂存器忽略所有符号链接，将正常版本化库视为缺少候选。

- 只读核对#508 inventory `9eb4c2d336766e6c66aff742f771dcd93686aece0eac70d5e40b619cd2ba0e3c`中的两个链接和解析后文件hash，收据`libzip-link-frozen-audit.json`。
- 独立宿主共享库小夹具真实执行`cc -fPIC -shared`并创建版本链接，旧暂存器exit1、候选为空；新暂存器exit0、普通文件及SHA一致。收据`shared-library-link-reproduction.json`；这是工程修复复现，不是项目效果。
- v1主动SIGINT后保留3完整strict（Make双来源、CMake工具）、1部分中断（CMake模型）、5未启动。根结果其余6未完整观察，不填方法效果失败。四个实际Session原源码未变、容器全部实际不存在；独立stdlib审计valid=true。
- v1 raw `/home/yiwei/.codex/outputs/forge-unified-plan-gate-v1/`，37524文件/0链接/154676154bytes，inventory `d0e7ce5f81a85399ab9fae1dbc5cdcaba28294835ce3c5955ec93bdcdb556405`，全部manifest/raw/source-snapshot保留，不续跑或回填。

v2 release `02014597a9a5b384b8b3385dcbc56597389fa2bc`只修本轮新增共享模块/入口，新增暂存器及6项真实Shell链接回归；原93历史组件逐项hash不变。v2独立九槽从头执行，沿用原绝对工程截止，不把v1完成结果拼入v2。

## v2零Provider门禁

协议`benchmarks/manifests/cpp-build-unified-plan-gate-v2.json`及同名preregistration，101冻结组件。三开发任务buffer/Make、uncrustify/CMake、libverto/Autotools双来源正常六槽；buffer双来源真实build=false→handoff→revision2→固定完整测试/交付/replay两槽；受控初始拒绝→Agent升级一槽。

- 九槽全部strict，0未观察；7次脚本模型请求、38条Shell，0真实Provider/Token/费用/未知。
- Make原完整自测；CMake双来源原工作区与replay均14/14 CTest；Autotools双来源原与replay均六测试6/6、0skip/0fail。完整日志标志逐项复核。
- 两个受控build失败各真实handoff一次、修订至revision2；两者均保留成功的gate-configure前缀，实际只执行一次该前缀，失败build及后续重跑；最终replay从空环境执行全配方。
- 初始受控拒绝槽为initial_abstention、0运行中handoff，走同预算Agent，不伪造成恢复成功率。
- 原文件内容hash、任务装配/交付、产物结构及哈希、同镜像replay和实际cleanup均通过；独立stdlib实现不导入生成器/Workflow/执行器，直接核对56701个inventory条目、原始请求响应/所有源码/固定测试与replay日志/实际容器不存在。
- raw `/home/yiwei/.codex/outputs/forge-unified-plan-gate-v2/`，56671文件/30链接/229021615bytes，inventory `6617b2f862686ca5c8086d3ca1431182d8bc8576c365a8166bbbd9dbafdf24a5`。独立审计`independent-v2-audit.json`，实现SHA `744690b3de57a0cb2b47cab7773e62b280b991613fe23e38c045dbfec5bda9f5`，完整测试摘要`full-test-summaries.json`。

补充`cpp-build-unified-strong-dispatch-gate-v1`固定buffer一槽，经新slot_runner→原强工具Agent自动配方接口，1/1 strict、1脚本模型响应/3Shell，0真实Provider/Token/费用；一次无参数submit，原完整测试/源码/交付/replay/cleanup及独立审计通过。raw `/home/yiwei/.codex/outputs/forge-unified-strong-dispatch-gate-v1/`，146文件/2105347bytes，inventory `bcdbdda48cd3f01464c33ee2ab7a6e1beb3cce86f8f3c21f70ea769a060d0a89`；收据`strong-dispatch-independent-audit.json`，独立实现SHA `11a1bd38ac10b03e7b94566c4f2d3cdc84ffe902e5e501f90fdc2ff9f8000f31`。这只是新入口连接资格，不是新的模型效果样本。

门禁模型是显式构造的本地FakeMessagesListChatModel，经真实create_agent/ToolStrategy/预算/响应计量，不读取Provider凭据。请求数是脚本响应数，不是真实模型能力观察。受控生成器拒绝与build=false明确标注，不计自然覆盖或自然恢复率。

## 公平比较候选

新候选manifest `benchmarks/manifests/cpp-build-unified-plan-comparison-v1.json`，SHA `7ac195707008dd127719b808577a1e099dcd4675652664041de2928b0d03023e`，107冻结组件，授权与截止为null（候选不等于付费授权）；新身份`cpp-build-unified-plan-comparison-v1`，执行入口`scripts/forge_build_unified_plan_comparison.py`，逐请求阶段费用分析`scripts/forge_analyze_unified_plan.py`。六评估项目×两重复×三方法36槽：工具初始Workflow、模型初始Workflow、强工具Agent。第一重复六项目覆盖全部六种方法排列，第二重复各块反序；固定项目/任务/资源/模型/裁判，全失败与未观察保留。

所有项目来源/人工参考已见，开发助手已看过#538结果；主要C库，不称holdout/训练未见或大型C++效果。libtom两项按一个保守关联组，共五组。预运行静态覆盖固定2/4分层：libsodium/libzip可生成候选，其余四项保守拒绝、将升级Agent。这是当前模板范围，不是构建成败，也不能证明这些项目必须用模型规划；不删除项目或按新结果调模板。

前两种方法共享装配、恢复只读工具/提示/状态投影、同一模型和预算。全部初始读取/输出、静态扫描及装配耗时、初始拒绝升级、失败Shell、运行中恢复、最终验证计入。费用从原请求账本重算并分初始/升级/恢复；解析失败的已知响应也计费，未知用量保留预留并停止，不凭请求数推节省。报告全臂费用、全部成本/strict交付数、Token/请求、总臂墙钟、Shell、成功与失败；不只比较成功子集。

新付费运行前须候选SHA、明确新预算和绝对时窗、完整门禁及独立审计闭合。旧#538付费stage均已关闭，额度剩余不构成新实验授权。本轮没有新的Provider效果数据。候选最多20美元，每请求0.40/3900秒预留，每臂1.50，费用/未知/物理cleanup及模型身份停止规则保持，未观察不填通过/失败。

## 检查、发布与证据

本轮新增36项回归；最终产品2088 passed/44 skipped/27 warnings，Ruff及548文件格式检查通过，候选真实CLI零Provider preflight通过。历史pytest垃圾目录root权限清理告警保留，不能当本轮用例失败。工程检查数量不作科研效果。

门禁v1/v2 raw各自只读；本轮会话收据统一在`/home/yiwei/.codex/outputs/forge-unified-plan-session-2026-10-20/`，包括中断独立审计、共享库链接复现、预运行静态覆盖、完整测试摘要、v2独立审计、CI和发布回读。最终完整HEAD三项实际CI通过才合入依赖分支`yiwei/534-rq3-natural-failures`，不进main；Issue542和长期#470状态以GitHub为准。知识库经MCP CAS同步并完整回读/检索验证，不复制Vault或注入Forge实验Agent。用户HTML未修改/提交。

不加P2、不改RQ3原固定候选分母、不放宽科学主张或裁判。下一项是新有效授权下执行完整比较，不能把本轮接口资格当成收益结论。
