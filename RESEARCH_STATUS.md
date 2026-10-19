# Forge Research Status

> 当前科研入口；只概括现阶段、证据、解释边界与下一决策。原始观察以冻结raw/inventory为准，身份与解释以版本化manifest/preregistration/report为准；详细工程交接见`.claude/memory/project.md`，长期综合见个人知识库。此前长时间线保留在Git版本`ce6e1af9:RESEARCH_STATUS.md`与各历史报告，不作为现阶段执行指令。

## 当前阶段

2026-10-20（北京时间）：#500两项Make参考资格全部严格完成并封存，libhydrogen完整12自测、buffer完整18断言与clean replay通过，源码不变、cleanup闭合、对应容器0残留。独立审计valid=true；267普通文件/0链接/3,188,966 bytes，inventory `7a7ca99cbc89cb2754b66f418f73eeab75a67fc9bf6162b1ac70903113336a6a`；报告`docs/research/2026-10-20-build-make-reference-results.md`。0Provider。

#498七槽状态/验证控制已封存，三正常strict completed、四已知负控制均按预定原因拒绝，7/7预期成立，两独立审计通过。#493十项参考7/10合格、8个Forge completed，三项未合格保留；PR #495已核验三CI并合入依赖分支，#493关闭。

下一阶段#502前瞻性配对比较：六仓库、三系统、双臂各两重复（24真实槽）；先同协议12臂零Provider门禁。新结果观察前共同冻结command300s/replay600s（uncrustify参考完整测试203.7s），完整测试/严格验收不变。#500已封存，可以修改后续共享组件；不得修改旧证据/manifest。当前尚无新模型效果观察。

## 当前研究问题与已知边界

主线为“面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究”，目标是完整、可答辩、可复现的硕士论文。方法为初始方案生成、确定性Workflow、权威状态观察、合理失败接管、修订失效和严格验证；不将先规划、DAG或重规划称为通用首创。方法定位见`docs/research/2026-10-20-build-plan-method-positioning.md`。

- RQ1：相同任务/材料/模型/资源/严格终点下，完整方案Workflow与允许批量操作的工具Agent，严格完成及全部成本如何变化？
- RQ2：状态变化后的适应有何实际增量？先识别动作分歧，保留合理规则强基线；没有分歧或修订激活时不为复杂选择器制造理由。
- RQ3：完整测试、精确交付与clean replay各能发现哪些表面成功？受控控制不能估计自然误接受率。

#489真实v2开发canary为8/8 strict completed，双方均18命令；plan/tool为7/34请求、68950/291092 tokens、$0.13283688/$0.43705728估算。四个plan臂交接/修订均0，不能证明状态适应增量。只描述已见开发项目，不作总体效果、非劣、总体成本收益或成熟Agent排名；不以修复前v1到v2差值作因果比较。

## 当前证据与后续执行入口

| 阶段 | 状态与证据 | 边界/下一步 |
| --- | --- | --- |
| #489真实双臂v2 | 封存`/home/yiwei/.codex/outputs/forge-plan-agent-canary-real-v2/`；3436普通文件/96链接，inventory `31652865251842eebb49f8582fb22c96610da21d6a4f5339b31daa08a5613663`，独立审计valid=true；报告`docs/research/2026-10-20-build-plan-agent-canary-v2-results.md` | 严格接线闭合；不当正式效果分母 |
| #492扩展12来源 | 12精确来源成功；78文件，inventory `49214164eab150f68fe950975cc81e8b36f143534545068ce2751c4137f39c62`；报告`docs/research/2026-10-20-build-source-expansion.md` | FastLZ语料子模块、HDiffPatch相邻依赖/oracle未闭合，暂缓不替换 |
| #493十项参考任务 | 7/10合格，8个Forge completed；inventory `34614ceaf61f45f383ea46bfacf4490e0e888417ea40c150b5bdee04b99ae011`；报告`docs/research/2026-10-20-build-reference-expansion-results.md` | 全部封存、0Provider，不替换三项未合格；已选定比较中的四项目均合格 |
| #496第二批Make来源 | 六槽位5来源成功/1 metadata失败；41文件，inventory `1cd3b892a03273cf289fc36b823163b0c794f1c1bf988ab460840a19050288ee`；报告`docs/research/2026-10-20-build-make-source-catalog.md` | libhydrogen/buffer有完整自测；pico需固定子模块；commander仅演示暂缓；tinyAES已有开发暴露 |
| #498状态/验证控制 | 七槽7/7预期成立，三正常strict、四已知负控制正确拒绝；inventory `f013a79451c2630f0ffd8e532eacda46a371716d1397eb500eaca5cc1f51cc85`；报告`docs/research/2026-10-20-build-state-validation-controls-results.md` | 已封存、两独立审计通过、0Provider；不新增P2，不估计自然误接受率 |
| #500两项Make参考 | 2/2严格completed；inventory `7a7ca99cbc89cb2754b66f418f73eeab75a67fc9bf6162b1ac70903113336a6a`；报告`docs/research/2026-10-20-build-make-reference-results.md` | 已封存、独立审计通过、0Provider；人工参考资格，不是模型结果 |
| #502前瞻性比较 | 六仓库、三系统、双臂各两重复，24真实槽；libhydrogen/libsodium同维护者关联组，总五组；已提交执行器与预注册，manifest父证据尚未绑定 | 参考与七控制闭合后，先12臂零Provider门禁；再共享预算内最多$12真实采集，不把缺槽或失败成本藏掉 |

所有新任务均为独立身份，旧失败、部分观察与冻结原始证据只读。#484四项目人工参考资格已全部通过，#486读取接口失败与#478 libusb响应合同停止等前序结果见各版本化报告；不能当新主线总体负结果，也不续跑旧身份。

## 本轮授权、费用与停止

用户已授权Issue→实现/实验/测试→commit/push→PR→最新head检查后合并→关闭Issue，并持续同步知识库。跟踪#470，协议`docs/research/2026-10-19-continuous-research-authorization.md`。

- 各阶段共享新增Provider上限$20；已知公开价保守估算累计$1.31364420，另旧live测试未知费用预留$1，预算占用$2.31364420。当前无未结束付费阶段，无运行中Provider。
- 估算不是账单，预留不是实际支出。共享账本`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/{authorization.json,budget-events.jsonl}`。
- 绝对截止北京时间2026-10-20 07:00，即UTC2026-10-19 23:00；最后15分钟仅清理/交接，不能跨午夜顺延。各阶段可更早停止新槽位准入。
- 预算耗尽后可做有效零支出工作。重大主线变更、超预算或需放宽科学主张边界时保存状态等待用户；普通阶段切换不需重新询问。

## 发布与工作区

#491/#494/#497均核验对应最新head的三项实际CI成功后合入依赖分支，#489/#492/#496关闭。#495已核验98236292三CI并合入依赖分支，#493关闭；#499控制结果已封存待结果head检查，#501两Make资格仍打开；#503配对比较为draft，尚未开始模型采集。合入依赖开发分支不等于进入main；不把约176个历史未进main提交一并发布。用户未跟踪的`docs/research/2026-10-13-forge-research-progress-defense.html`不修改/提交。

相关阶段本地回归与Ruff通过，检查以各自报告、PR和head为准；默认产品回归必须`CI=true FORGE_RUN_CLIENT_LIVE=0`，不得意外触发付费live测试。知识库固定入口为`01-研究/自动化编译/Forge-当前创新机制与实验路线.md`，只通过knowledge_base MCP维护，写前读取最新SHA、CAS写入后回读；不复制Vault或注入正式实验Agent。

## 历史停止决定仍有效

| 历史身份 | 决定与边界 | 权威入口 |
| --- | --- | --- |
| #440 H0/H1 v3 | strict19/27→22/27、成本下降50%，但非劣下界-0.111未过-0.10且Make/Autotools退化；H1不再单独作为主创新 | `benchmarks/reports/cpp-progress-aware-harness-comparison-v3-authorized.md` |
| #455 H0/H1/H2 v2 | 各6/6，无closure rejection/repair激活；不能证明H2可靠性增量，不追加相同全成功样本 | `benchmarks/reports/cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v2.md` |
| #463/#465 Jev | 校准覆盖不足，逐动作分解/ActionCard未转为有效覆盖；停止进入controller，不补跑或降阈值 | `benchmarks/reports/cpp-jev-progress-budget-calibration-v1.md`、`cpp-jev-action-safety-decomposition-v1.md` |
| #467依赖/配置A0–A4 | 未得到至少3个强Agent后仍未解且有合法修复依据的残余难题；停止A5，不等于否定自动化编译硕士主线 | `benchmarks/reports/cpp-dependency-configuration-agent-investigation-v2.md` |

历史#408受控失败正向结果、#457状态/BudgetFit benchmark与其他历史观察继续保留各自原主张范围；新路线不重写旧结论。
