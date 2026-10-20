# 三策略统一入口与端到端零Provider门禁（#536）

本轮完成三策略统一入口和完整13槽工程门禁，13/13严格完成并经独立核验。新增Provider请求、Token和费用均为0；真实36槽因剩余窗口不足3900秒未准入，全部保留为未观察。这是**基础设施阶段**，解除三策略比较的执行与接管资格阻塞；不据此声称某策略更省钱、成功率更高或真实模型恢复能力更强。

## 问题与实际实现

研究问题沿用#532：完整项目构建中，强工具Agent、先规划Workflow+失败Agent、先规划Workflow+一次合理规则+失败Agent如何取舍严格交付、完整费用、请求和耗时。以硕士论文尺度接受小幅/条件性收益和明确取舍，不要求全指标占优，不放松裁判。

| 方法 | 入口与异常处理 |
| --- | --- |
| strong_tool_agent | run_tool_agent_automatic，允许批量工具，自动从权威成功命令选择配方ID，同预算Agent自行调查 |
| plan_workflow_failure_agent | propose_with_context生成完整方案，Workflow执行；真实handoff后完整修订，首变化后步骤记录失效 |
| plan_workflow_rules_failure_agent | 相同模型初始规划，费用计入；#516三条规则最多一次，未覆盖或规则后再失败转同预算Agent |

代码 `scripts/forge_build_full_strategy_runtime.py`、`scripts/forge_build_full_strategy_runtime_v2.py`；v2运行release `f349ffd0615c239b0e4d8d9daf8c9bbbda17aa93`，manifest/preregistration同名 `cpp-build-full-strategy-runtime-v2`，82组件SHA固定。v1和旧libverto实验组件/manifest/raw不改；每方法、项目、重复和规则闭包独立。真实Agent不接收正确参考或知识库；只有工程门禁使用人工脚本模型和参考方案。

三方法共同HandoffContextMeter，2CPU，节点1200秒、命令600秒、evaluator/replay各900秒、cleanup120秒，32命令、12模型请求、消息50k/schema8k。400000已记录Token为准入界限，单响应上限100000，最后响应可能使累计达到500000，不误称400000绝对总量。两Workflow臂最多两次交接、一次规则修订。

## 完整门禁结果

3开发项目buffer/uncrustify/libverto分别覆盖Make/CMake/Autotools；各三正常路径共9槽，另4条预定失败恢复。全部在实际容器中执行，固定完整测试、原源码不变、精确交付、同镜像clean replay、实际cleanup全部通过。

| 项目 | 方法 | 场景 | 规则 | 规则臂Agent恢复 | 真实交接 | 严格终点 |
| --- | --- | --- | --- | --- | --- | --- |
| buffer | strong_tool_agent | normal | 0 | 0 | 0 | 通过 |
| buffer | plan_workflow_failure_agent | normal | 0 | 0 | 0 | 通过 |
| buffer | plan_workflow_rules_failure_agent | normal | 0 | 0 | 0 | 通过 |
| uncrustify | strong_tool_agent | normal | 0 | 0 | 0 | 通过 |
| uncrustify | plan_workflow_failure_agent | normal | 0 | 0 | 0 | 通过 |
| uncrustify | plan_workflow_rules_failure_agent | normal | 0 | 0 | 0 | 通过 |
| libverto | strong_tool_agent | normal | 0 | 0 | 0 | 通过 |
| libverto | plan_workflow_failure_agent | normal | 0 | 0 | 0 | 通过 |
| libverto | plan_workflow_rules_failure_agent | normal | 0 | 0 | 0 | 通过 |
| buffer | plan_workflow_failure_agent | agent_recovery | 0 | 0 | 1 | 通过 |
| uncrustify | plan_workflow_rules_failure_agent | rule_recovery | 1 | 0 | 1 | 通过 |
| buffer | plan_workflow_rules_failure_agent | uncovered_to_agent | 0 | 1 | 1 | 通过 |
| uncrustify | plan_workflow_rules_failure_agent | rule_then_agent | 1 | 1 | 2 | 通过 |

无规则臂的Agent恢复不使用规则组件的事件计数，agent_recovery槽另由真实handoff/修订及两次脚本规划响应核验。完整矩阵共16次零Token脚本请求、58条Shell，0Provider。脚本请求经过真实planner、工具、计量与状态接线，不能称真实模型能力或自然恢复率。

关键链路为：错误target实际失败→规则删除target并保留configure→build和固定测试成功→stage=false实际失败→脚本Agent交付revision3，保留configure/build/check，仅重做stage→最后clean replay仍从空环境完整重建/测试/比对。另一个未覆盖错误由规则臂转Agent；正常路径不激活恢复。

## 时间检查修复与旧证据保留

v1错误地将真实Provider所需3900秒余量同时用于零Token脚本请求。三项测试稳定复现旧拒绝，并确认v2仅对严格scripted-gate/0用量采用120秒工程时间检查，真实Provider仍走原3900秒路径，全部执行与验证上限不变。实际外层启动器 `launch_gate_v2.py` 保存在本轮工程证据目录：UTC03:46:10发SIGINT、90秒后强止，为用户03:48:10绝对截止保留清理时间。v2已正常完成，未触发硬停止。

旧v1在UTC02:26:27因工程修复主动SIGINT，7strict/1中断部分/5未启动，包含部分8脚本请求、0Token/Provider/费用；root保留6未观察或未闭合。继承标签initialization_not_completed不表示真实初始化失败，实际原因以外部v1-interruption-request.json和KeyboardInterrupt日志为准。中断部分源码不变、实际cleanup通过；不计为方法效果失败，不续跑或回填。

独立开发资格 `cpp-build-full-strategy-fallback-gate-v1` 已1/1 strict、独立核验valid=true，2脚本请求/6Shell/2失败与交接/revision2和3、0Token/Provider/费用；不能替代完整13槽或取得付费准入。两矩阵和独立资格曾以独立进程/Session并行，每容器2CPU，主机64逻辑CPU；工程并行耗时不用于方法性能比较。

libverto正常门禁使用干净环境的既有合格参考；#530原失败状态到最小configure修订的失败证据仍有效，条件不同，不回填。

## 冻结证据与核验

| 身份 | raw目录 | inventory SHA-256 | 文件/链接/bytes |
| --- | --- | --- | --- |
| 完整v2 | /home/yiwei/.codex/outputs/forge-full-strategy-gate-v2/ | 08286b1789beabeef814fda35d735da3575984a82d6489d189eb9ca9c13a841f | 140562/72/476924134 |
| 中断v1 | /home/yiwei/.codex/outputs/forge-full-strategy-gate-v1/ | 0553b00b2c2fa21e94741ec36c2f651fba63f080337b155320462a3727d62482 | 84125/24/277419007 |
| 独立fallback | /home/yiwei/.codex/outputs/forge-full-strategy-fallback-gate-v1/ | bfb6a3b78981b805d43567f33d5524783e0cb9f4bb0566ec93ebab23a25f9cf6 | 27933/0/89378825 |

独立stdlib核验 `audit_three_strategy.py` 不导入执行器及其门禁判定，重新计算完整inventory、组件/归档/原源码hash、命令日志、模型原始响应/费用、权威handoff/revision/规则事件、固定测试、原/replay产物集合/大小/SHA-256、实际容器缺失状态。实现SHA `6e7e3890c8af684221f2a76ff8206b7f4f6d5de532d0ee3c593bae675d58161f`，完整v2 gate_coverage_complete=true；中断v1为false，独立fallback无全比较准入，未混淆三者。中断槽另由audit_v1_interruption.py核验。

独立代码、结果、授权、工程日志、完整产品测试日志及发布收据统一在 `/home/yiwei/.codex/outputs/forge-three-strategy-session-2026-10-20/`。本地15项相关测试、产品2015 passed/44 skipped、Ruff及536文件格式检查通过。测试数是工程验证，不是科研效果。PR537合入依赖开发分支yiwei/534-rq3-natural-failures；最终head、三项CI、merge和Issue关闭状态以GitHub及final-publication-audit.json为准，未进入main。用户未跟踪HTML未改/未提交。

## 授权、未观察分母与下一步

本轮新增共享上限20美元，UTC01:48:10至03:48:10（北京时间09:48:10至11:48:10），准备计入，不继承旧费用/未知预留。门禁结束后的准入核验时间2026-10-20T03:15:51.140584+00:00，剩余1938.9秒，少于3900秒，不读Provider凭据或创建真实attempt。36槽逐项保留在live-admission-v2.json，均为not_observed，不填失败/通过，也不比较便利子集。

final-budget-audit.json独立复算本轮含v1中断部分、独立资格及完整v2共26次脚本请求，全部0Token/Provider；费用/未知预留/预算占用为0，未使用上限20美元，付费账本无stage事件。旧已知$5.80615200和未知预留$1保持原窗口，不挪入本轮。

下一阶段是在新的有效授权窗口中执行原6评估项目×2重复×3方法的完整36槽，保持初始规划/读取/输出/失败/恢复全成本、固定测试/源码/精确交付/replay/cleanup。11来源及人工参考均已见，评估角色不称holdout；libtom两项合为5保守组之一，不证明独立项目族。小幅或条件性收益仍值得继续；没有合理动作分歧不加P2，RQ3固定原候选分母不变，不放松科学主张。
