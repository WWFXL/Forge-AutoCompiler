# 三策略真实比较：原部分批次与独立续段（#538）

原36个逻辑槽位取得完整观察：严格成功26/36，未观察0；共293次真实请求、3650987 Token，保守费用估算$5.50500324，未知用量0。**这些数据来自两个分别冻结的身份，只做披露工程修复后的描述性比较，不能称原v1完整闭合或单一冻结版本的因果比较。**

本轮的实证取舍是：无规则方案与强工具Agent都为9/12严格成功，方案少10次请求（9.2%），但费用高24.9%、总臂耗时更长，**当前版本不支持整体成本优势**。check与libtommath有局部费用优势，libsodium的两个方案策略均2/2而工具1/2；这些条件性结果支持继续改进当前主线，不要求全指标胜出。规则臂0次规则激活，其较少请求和较低成功数不能解释为规则增量。

## 研究问题与冻结边界

主线为“面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究”。比较强工具Agent、完整初始规划＋Workflow＋失败Agent、完整初始规划＋Workflow＋一次有界规则＋失败Agent。正常执行阶段由Workflow推进；异常后依据权威记录修订，使首变化后的执行记录失效，再做完整测试与交付验证。规则未覆盖或规则后仍失败时转同预算Agent。

原6项目check/libpng/libsodium/libtomcrypt/libtommath/libzip×2重复×3方法的任务、顺序、精确源码commit/归档、镜像、模型、资源与裁判保持。来源及人工参考均已见，不称holdout；libtom两项合为5个保守关联组之一，不证明项目族独立。全部初始规划、读取、输出、失败与恢复费用计入，不只统计成功臂。不增加P2、不改变RQ3原候选分母，不降低原源码/固定完整测试/精确交付/clean replay/cleanup验收。

归档扩展名事后盘点显示六项目均包含.c、未发现.cc/.cpp/.cxx/.c++文件（archive-language-description.json）。这轮主要是C库任务，不能直接推广到大型C++、复杂子模块或更多系统；C++后续应单独登记样本资格，不能把CMake等同于C++覆盖。

## 为何分为两个身份

原cpp-build-full-strategy-comparison-v1在16观察后按协议停止：12strict、3请求预算停止、1源码合同拒绝，原20未观察永久保留。libzip规则Workflow重生成110个原man HTML，原源码不变裁判拒绝有效；不能当作通过，也不等同于已证实功能错误。权威container.cleanup.removed exit0、finalize及Docker实际不存在证明清理成功；旧run_arm在finally后续源码检查抛错时，把已成功物理cleanup覆盖为false，触发整批停止。

新cpp-build-full-strategy-cleanup-continuation-v1只执行原第16..35槽，original_slot保留映射；前16没有重跑。新增适配器仅在原源码实际改变、正确Session/container的权威removed exit0/finalize、原与replay容器全部实际不存在时，分别记录源码拒绝和物理cleanup。原逐臂result.json保持，另写physical-cleanup-classification.json，根聚合保存legacy_cleanup，strict仍为false。真正cleanup失败/未知用量仍停止。原85组件不改，新增3组件，共88组件。

零Provider开发buffer负例故意追加原Makefile注释，1次脚本请求、0Token，旧wrapper源码拒绝/cleanup=false保留，新分类strict=false/物理cleanup=true。独立stdlib核验valid=true，库存b4e99be9c79cca602552a7c2b37dfc3f7276d5dffd5876781c840a226f434d63；父完整13槽正门禁库存08286b1789beabeef814fda35d735da3575984a82d6489d189eb9ca9c13a841f复核通过。

修复发生在首16槽结果已见后，即使执行策略与成功裁判保持，也不能把跨身份汇总写成单一版本的预注册因果证据。两队列独立审计并保留，汇总只描述原固定逻辑任务集合。原逐臂kind继承real_model_development_canary标签，不回写；根身份、预注册和kind定义本轮前瞻角色，不与旧canary混合分母。

## 固定逻辑槽位的描述性比较

| 方法 | 严格成功/观察 | 请求 | 输入/输出Token | 全臂费用USD | Shell | 总臂耗时秒 | 交接/修订/规则 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 强工具Agent | 9/12 | 109 | 1170349/33775 | 1.67860968 | 92 | 2259.393 | 0/0/0 |
| 方案Workflow＋失败Agent | 9/12 | 99 | 1208493/126631 | 2.09666952 | 46 | 3187.684 | 4/4/0 |
| 方案Workflow＋规则＋失败Agent | 8/12 | 85 | 1012410/99329 | 1.72972404 | 44 | 3226.877 | 4/4/0 |

按输入$1.32/M、输出$3.96/M复算的保守估算，不是账单。请求或总Token少不必然更便宜。总臂耗时含执行/验证/replay/cleanup，不用最后请求前tracker elapsed替代。工具臂自行修复没有Workflow交接事件，交接0不表示没有错误；diagnostic失败单列，不称构建失败。

| 候选 / 基线 | 双方成功 | 仅候选成功 | 仅基线成功 | 双方失败 | 全费用差USD | 合计费用变化 | 请求差 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 方案Workflow＋失败Agent / 强工具Agent | 8 | 1 | 1 | 2 | 0.41805984 | +24.9% | -10 |
| 方案Workflow＋规则＋失败Agent / 强工具Agent | 7 | 1 | 2 | 2 | 0.05111436 | +3.0% | -24 |
| 方案Workflow＋规则＋失败Agent / 方案Workflow＋失败Agent | 7 | 1 | 2 | 2 | -0.36694548 | -17.5% | -14 |

每格12个项目/重复配对；重复不是独立项目。这里不做总体排名、非劣/显著性或自然恢复率推断。小幅收益、条件性优势和有利有弊均可支持硕士研究继续，不设事后最低收益门槛。

## 费用差与阶段归属

以下是原Token按冻结单价的算术分解，不是机制因果归因。

| 候选 / 基线 | 输入费用差USD | 输出费用差USD | 合计差USD |
| --- | --- | --- | --- |
| plan_workflow_failure_agent / strong_tool_agent | 0.05035008 | 0.36770976 | 0.41805984 |
| plan_workflow_rules_failure_agent / strong_tool_agent | -0.20847948 | 0.25959384 | 0.05111436 |
| plan_workflow_rules_failure_agent / plan_workflow_failure_agent | -0.25882956 | -0.10811592 | -0.36694548 |

无规则方案相对工具的额外费用中，输出部分贡献$0.36770976，输入部分贡献$0.05035008；不能把少请求等同于低成本。

| 方法 | 初始请求/费用USD | 恢复请求/费用USD | 初始规划占方法费用 |
| --- | --- | --- | --- |
| plan_workflow_failure_agent | 89/1.84749840 | 10/0.24917112 | 88.1% |
| plan_workflow_rules_failure_agent | 76/1.51956948 | 9/0.21015456 | 87.9% |

两方案方法约88%的费用在初始规划阶段；这支持将下一项改进优先放在初始规划接口与证据获取开销，尚不证明哪种改动必然改善效果。10个未严格成功槽中，6个预算停止（4个初始未交付方案、2个工具已构建/测试/暂存但未submit），3个原文件改写拒绝、1个固定测试命令逐字合同拒绝。未执行的后续层仍保留未观察。

| 项目 | 构建系统 | 强工具 成功/2；费用USD | 方案Workflow 成功/2；费用USD | 方案规则Workflow 成功/2；费用USD |
| --- | --- | --- | --- | --- |
| check | autotools | 2/2；0.35578884 | 2/2；0.26337300 | 2/2；0.25505964 |
| libpng | cmake | 2/2；0.22685916 | 2/2；0.41852184 | 0/2；0.47257056 |
| libsodium | autotools | 1/2；0.33883872 | 2/2；0.35237004 | 2/2；0.31216020 |
| libtomcrypt | make | 2/2；0.21698424 | 1/2；0.42639696 | 2/2；0.21194712 |
| libtommath | make | 2/2；0.22587180 | 2/2；0.16986816 | 2/2；0.16226760 |
| libzip | cmake | 0/2；0.31426692 | 0/2；0.46613952 | 0/2；0.31571892 |

| 比较 | 保守关联组 | 项目 | 配对 | 费用差USD | 请求差 |
| --- | --- | --- | --- | --- | --- |
| 方案Workflow＋失败Agent / 强工具Agent | check | check | 2 | -0.09241584 | -11 |
| 方案Workflow＋失败Agent / 强工具Agent | libpng | libpng | 2 | 0.19166268 | +7 |
| 方案Workflow＋失败Agent / 强工具Agent | libsodium | libsodium | 2 | 0.01353132 | -6 |
| 方案Workflow＋失败Agent / 强工具Agent | libtom-associated | libtomcrypt,libtommath | 4 | 0.15340908 | -3 |
| 方案Workflow＋失败Agent / 强工具Agent | libzip | libzip | 2 | 0.15187260 | +3 |
| 方案Workflow＋规则＋失败Agent / 强工具Agent | check | check | 2 | -0.10072920 | -11 |
| 方案Workflow＋规则＋失败Agent / 强工具Agent | libpng | libpng | 2 | 0.24571140 | +10 |
| 方案Workflow＋规则＋失败Agent / 强工具Agent | libsodium | libsodium | 2 | -0.02667852 | -8 |
| 方案Workflow＋规则＋失败Agent / 强工具Agent | libtom-associated | libtomcrypt,libtommath | 4 | -0.06864132 | -11 |
| 方案Workflow＋规则＋失败Agent / 强工具Agent | libzip | libzip | 2 | 0.00145200 | -4 |
| 方案Workflow＋规则＋失败Agent / 方案Workflow＋失败Agent | check | check | 2 | -0.00831336 | +0 |
| 方案Workflow＋规则＋失败Agent / 方案Workflow＋失败Agent | libpng | libpng | 2 | 0.05404872 | +3 |
| 方案Workflow＋规则＋失败Agent / 方案Workflow＋失败Agent | libsodium | libsodium | 2 | -0.04020984 | -2 |
| 方案Workflow＋规则＋失败Agent / 方案Workflow＋失败Agent | libtom-associated | libtomcrypt,libtommath | 4 | -0.22205040 | -8 |
| 方案Workflow＋规则＋失败Agent / 方案Workflow＋失败Agent | libzip | libzip | 2 | -0.15042060 | -7 |

## 实际恢复与失败

| 原槽 | 项目/重复/策略 | 严格终点 | 交接/修订/规则 | 初始/恢复请求 | 已记录构建/完整测试/暂存；replay次数 | 最终异常 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | check/r1/方案Workflow＋失败Agent | 通过 | 1/1/0 | 3/3 | 1/1/1；1 | 无最终异常 |
| 2 | check/r1/方案Workflow＋规则＋失败Agent | 通过 | 1/1/0 | 3/3 | 1/1/1；1 | 无最终异常 |
| 4 | libpng/r1/方案Workflow＋规则＋失败Agent | 拒绝或停止 | 0/0/0 | 12/0 | 0/0/0；0 | AgentWorkflowBudgetExceeded |
| 6 | libsodium/r1/方案Workflow＋规则＋失败Agent | 通过 | 1/1/0 | 7/2 | 1/1/1；1 | 无最终异常 |
| 7 | libsodium/r1/强工具Agent | 拒绝或停止 | 0/0/0 | 0/0 | 1/1/1；0 | AgentWorkflowBudgetExceeded |
| 8 | libsodium/r1/方案Workflow＋失败Agent | 通过 | 1/1/0 | 6/3 | 1/1/1；1 | 无最终异常 |
| 10 | libtomcrypt/r1/方案Workflow＋失败Agent | 拒绝或停止 | 0/0/0 | 12/0 | 0/0/0；0 | AgentWorkflowBudgetExceeded |
| 15 | libzip/r1/方案Workflow＋规则＋失败Agent | 拒绝或停止 | 0/0/0 | 10/0 | 1/0/0；0 | PlanContractError：原始源码或测试被修改 |
| 16 | libzip/r1/强工具Agent | 拒绝或停止 | 0/0/0 | 0/0 | 1/0/0；0 | PlanContractError：原始源码或测试被修改 |
| 17 | libzip/r1/方案Workflow＋失败Agent | 拒绝或停止 | 0/0/0 | 10/0 | 0/0/0；0 | PlanContractError：Agent 不得改变任务作者固定的验证步骤 |
| 19 | check/r2/方案Workflow＋规则＋失败Agent | 通过 | 1/1/0 | 3/3 | 1/1/1；1 | 无最终异常 |
| 20 | check/r2/方案Workflow＋失败Agent | 通过 | 1/1/0 | 3/3 | 1/1/1；1 | 无最终异常 |
| 23 | libpng/r2/方案Workflow＋规则＋失败Agent | 拒绝或停止 | 0/0/0 | 12/0 | 0/0/0；0 | AgentWorkflowBudgetExceeded |
| 25 | libsodium/r2/方案Workflow＋失败Agent | 通过 | 1/1/0 | 7/1 | 1/1/1；1 | 无最终异常 |
| 33 | libzip/r2/方案Workflow＋规则＋失败Agent | 拒绝或停止 | 1/1/0 | 4/1 | 1/0/0；0 | PlanContractError：原始源码或测试被修改 |
| 34 | libzip/r2/方案Workflow＋失败Agent | 拒绝或停止 | 0/0/0 | 12/0 | 0/0/0；0 | AgentWorkflowBudgetExceeded |
| 35 | libzip/r2/强工具Agent | 拒绝或停止 | 0/0/0 | 0/0 | 1/1/1；0 | AgentWorkflowBudgetExceeded |

上表阶段数字仅表示是否有成功记录；0包括未执行/未观察，不能当作失败。它们不替代当前严格验收，未发生的验证不填通过/失败。8个方案槽发生实际handoff并修订，7个最终strict（check四次、libsodium三次），libzip一次修复pip依赖后仍因源码改写拒绝；它们不是8个独立错误族或一般恢复率。成功恢复只证明这些具体路径能执行，不推自然错误覆盖率。规则未触发时，规则臂的差异不能归因于规则收益；独立初始输出有随机性，不为获得规则增量额外注入故障。

## libsodium bootstrap网络等待的事后解释

第二重复规则方案选择./autogen.sh -s，原bootstrap执行252.326秒；只读进程观察显示其中等待curl更新GNU config脚本，之后原工作区测试与clean replay都通过。无规则方案初始使用./autogen.sh -b但未生成configure，Agent恢复时增加-s且保留-b，最终为./autogen.sh -s -b，跳过该可选更新。两者参数选择与网络等待均是完整路径的一部分，费用/耗时不剔除；不能把单次网络等待差异全部解释为Workflow或规则本身的通用速度收益。原命令与duration_seconds在analysis-cross-identity.json的command_timeline及权威Session保存。

## libzip验证命令拒绝的事后核对

原逻辑槽17的无规则方案在初始规划后，被任务验证步骤逐字合同拒绝。逐响应核对表明仅单双引号写法不同：shlex分解后python3 -c参数的Python AST一致，其余Shell词元一致，其他步骤字段一致；没有观察到删减固定测试。libzip-quote-rejection.json保存原protocol/response SHA与核验，原strict失败不改。该单例支持接口转写脆弱性解释，不是通用Shell语义判等，也不证明执行后一定成功。未来可让系统直接装入作者固定验证步骤，消除模型转写负担而保持同一测试；需要独立新身份验证，不能回填本轮。

## 版本、授权与独立核验

用户授权本轮共享$20/4小时，UTC2026-10-20T03:47:40Z至07:47:40Z（北京时间11:47:40至15:47:40），准备计入、不重置、不挪旧费用。原阶段实际$2.54462076000000006后关闭，新阶段预留$10是最坏占用而非实际费用。每臂$1.50/每请求$0.40/3900秒准入，未知usage立即停止。外层UTC07:30:40 INT/90秒强止，原截止不延长。

模型deepseek-v4-pro thinking low、max output32768、max_retries=0；2CPU、节点1200秒、命令600秒、evaluator/replay900秒、cleanup120秒、32命令、12请求、400000累计Token准入/单响应100000（绝对最多500000）、50k消息/8k schema、最多两交接/一次规则修订。真实模型不接收人工正确方案或知识库。

| 身份 | 运行release / 协议SHA | 观察 / 原未观察 | raw / inventory |
| --- | --- | --- | --- |
| cpp-build-full-strategy-comparison-v1 | 6f9869733234ffefc5f4489651995b0434910865 / c40e2279eac72b02d80c9c744d8233fe6d0359b6c4bd7f624e4626d91fe818b7 | 16 / 20 | `/home/yiwei/.codex/outputs/forge-full-strategy-real-v1/` / `f216c3930624768d6def984681af377d0ccb1e2427dd52a30b21c5d595692b72` |
| cpp-build-full-strategy-cleanup-continuation-v1 | 3965e5c2e3ac7a616431594a7cbe536f180a56d1 / 5cf3c4181bee93ecded68bbef15c7431a2eaf0b5decf7c85e7c87efb48ec5d36 | 20 / 0 | `/home/yiwei/.codex/outputs/forge-full-strategy-real-continuation-v1/` / `012476793e5a0a40ceaa532a0c6b953fcea682fba748a4e33554d277935bba92` |

独立stdlib审计不导入执行器，分别重新计算inventory/冻结组件/原源码/原响应用量/固定测试/精确交付/replay与实际Docker不存在，valid=true。新续段两次cleanup分类另经independent-cleanup-classifications.json独立核验，原错误/strict/用量不变、两项均改写110个原HTML且实际清理成功。cleanup-classifier-projection.json核验负例与正式分类函数AST一致，负例后仅新增main准入收据哈希检查。原audit_three_strategy.py实现SHA6e7e3890c8af684221f2a76ff8206b7f4f6d5de532d0ee3c593bae675d58161f；两个身份均完整复算，无回写。派生analysis-cross-identity.json另复算全部原始started/completed/response一一对应、Token/费用/初始与恢复归属、原36逻辑顺序、每方法12槽、配对/关联组与两阶段共享账本。

逐响应分析实现SHA`1c91fe67308a4f0b2add35afb75e5facbcf8a1bd1eb54bda5f850f7a98d49a01`。授权/启动/原账本/独立核验/派生分析/最终发布收据统一在`/home/yiwei/.codex/outputs/forge-full-comparison-session-2026-10-20/`。工程测试28项相关通过、产品2033 passed/44 skipped，Ruff/format通过；CI与merge以final-publication-audit.json及GitHub为真源，仅合入依赖分支、不进main，用户HTML未改/未提交。前置路径错误/pytest历史临时目录root权限告警保留，不作为实验效果。

## 后续决定

按固定集合的完整费用、成功率与具体恢复路径定位方法适用范围，不因混合结果放弃硕士主线。区分初始规划开销、确定性执行节省与恢复局限；若无真实规则激活，不声称规则或复杂选择器有独立增量。本轮不包含libverto，不能回填#530最小配置修订不足以恢复的负证据。下一步优先围绕新增证据暴露的可检验问题设计廉价离线或零Provider资格，不扩大主张或直接转写论文正文；下一付费阶段须重新核验有效授权与窗口。

## 事后读取行为描述

首批部分结果已见后准备，不是预注册机制因果检验。仅计read_source API；工具Agent的Shell cat/grep等读取不在此表，不能将表中调用数当作完整信息获取量。精确重复返回可能有上下文恢复作用，不等同无用读取，也不能据此归因预算停止。

| 方法 | 初始/恢复/工具读取调用 | 精确重复成功返回 |
| --- | --- | --- |
| 强工具Agent | 0/0/19 | 0 |
| 方案Workflow＋失败Agent | 138/6/0 | 51 |
| 方案Workflow＋规则＋失败Agent | 114/5/0 | 37 |

详见read-patterns-cross-identity.json，实现SHA`b6b4b3e089fa5b94dbfcd0ed97b593ce701604a40aa01275b0db414d6f133841`，不改变原实验分母。
