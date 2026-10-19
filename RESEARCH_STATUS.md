# Forge Research Status

> 当前科研入口；只概括现阶段、证据、解释边界与下一决策。原始观察以冻结raw/inventory为准，身份与解释以版本化manifest/preregistration/report为准；详细工程交接见`.claude/memory/project.md`，长期综合见个人知识库。此前长时间线保留在Git版本`ce6e1af9:RESEARCH_STATUS.md`与各历史报告，不作为现阶段执行指令。

## 当前阶段

2026-10-20（北京时间）：#502固定六仓库/三系统/双重复/双臂的真实比较全部结束，24/24严格completed、12配对双方均成功，独立审计valid=true，0未知用量、源码不变、固定完整测试/精确交付/clean replay/cleanup闭合。143187普通文件/184链接/1193274172 bytes，inventory `2df552e2a26dac451b4d61690c4bc3eac59fee2fd0dcc0b3604f25c84905a91d`；raw `/home/yiwei/.codex/outputs/forge-plan-agent-paired-real-v1/`，报告`docs/research/2026-10-20-build-plan-agent-paired-comparison-results.md`。

plan/tool分别60/105请求、765692/1082737 Token、$1.26334296/$1.62595884估算、52/66命令。固定任务合计费用少22.3%，但libsodium/libsndfile的plan更贵，五维护者关联组的费用差重采样范围跨0，不能声称跨项目稳定成本优势。12个plan交接/修订均0；11/12个tool臂共19次配方ID拒绝后自行纠正，4条失败Shell均diagnostic。不能把差异全部归于初始规划，也不证明RQ2状态适应、总体非劣、成熟Agent排名或P2增量。

#504强接口真实探针已12/12完整封存，plan/tool各5/6 strict：37/50请求、486546/508130 Token、$0.79509408/$0.71376360估算、1095.568/840.297秒，0未知用量、cleanup全部成功。请求少不等于费用低，本批plan费用高11.4%；0submit拒绝，五成功tool各一次自动配方submit。libverto-r1-tool请求用尽前build/6测试过但未交付；libverto-r2-plan固定测试0/6后真实handoff一次，因状态材料超过50000字节在第10次总请求前停止；此前4次初始规划+5次真实恢复，0修订。失败不补跑，不能称纯模型恢复失败。raw `/home/yiwei/.codex/outputs/forge-auto-provenance-real-v1/`，inventory `d7bad477a8b355ffdbb21de127961c2f8f639798186d6c7d6ad0ecb27263e446`，独立审计valid=true；报告`docs/research/2026-10-20-build-auto-provenance-probe-results.md`。65组件、后验选样和严格终点均保持；不作跨批因果/总体非劣/成熟Agent排名。下一步独立#506三系统受控恢复资格。

父#493十项参考7/10合格、#498七控制7/7预期成立、#500两Make2/2严格completed及#502十二臂零Provider门禁均封存、独立审计通过。前三阶段均核验结果head三CI后合入依赖分支并关闭Issue；#503结果adc54403的三项实际CI均SUCCESS后已合并（df830217），#502关闭，未进入main。#502协议54d1d893、运行release557a44c4，manifest SHA-256 `5f2cc841c38b1ed8eaee5867d2491dfce060c539aa9c3c92170729bbc74f42f2`。

## 当前研究问题与已知边界

#508准备零费用两项参考配方修复资格：libpng只修正暂存文件名，libzip只关闭非任务目标的文档生成（原完整回归测试/交付/源码不变/重放均不变）；不回填#493或当前比较，libffi仍未解决不替补。4项测试、Ruff/format、完整父封存只读validate通过；候选manifest64组件，SHAe839a2b65c3149c438d1518d5655d5312279bfd3b60080c3485d1d45c6603e71，未提交/运行。新身份每项一次、900秒方案/600秒replay，UTC22:45阶段截止且准入留1800秒；待当前付费/构建实验结束后按剩余时间决定，不并行。

#507零Provider回顾分层验证覆盖审计完成全部43行并封存，inventory621a6d20ee695b0e4e7be3d818922c9b481f12ac4e65cf5a97da207baf7bf08f，消费文件/原分母终点/七关键案例独立核验valid=true；10项测试/Ruff/format通过。报告`docs/research/2026-10-20-build-validation-evidence-audit-results.md`，独立实现/协议/报告41c13664经最终三CI后由PR510合并ca01048a，#507关闭，不混入#505。初次默认workdir提取失败和独立核验字段误用均保留，不改旧证据。libzip的110个man HTML重生成属操作合同拒绝，不是已证实语义错误；受控空测试、交付漂移、遗漏bootstrap与过期状态分开解释。不混队列成功率，不估自然误接受/因果增量，不宣布第二创新点。#504的65组件未变。

#506受控恢复已完整封存：九槽零Provider门禁9/9预期成立，真实三系统3/3 strict、各一次handoff/revision2；6请求/61294 Token/$0.09434832估算。miniz保留configure前缀，pigz/libite从首变化失效重执行；旧失败和失效命令未进replay，源码/完整测试/精确交付/cleanup闭合，独立审计valid=true。raw `/home/yiwei/.codex/outputs/forge-plan-recovery-real-v1/`，inventory a47d84aa86bde07f5dda19f492bf3c7be3834f7b52c1e6c433d32ddda24a9f67；报告`docs/research/2026-10-20-build-plan-recovery-qualification-results.md`。初始人工方案不进入RQ1全策略成本，不当自然恢复率/P2增量。

已识别混杂：原工具接口要求模型手工选择supporting/recipe ID，真实轨迹经常在构建与固定测试成功后因ID/顺序被拒。这不是项目不可编译。#504只自动选择权威记录中的最后成功build与有序成功配方，再委托原submit；固定测试freshness、源码、精确交付和重放不放宽。允许同轮批量构建/测试/暂存/提交，不人为限制强基线。后续比较是实际完整路径间的描述，不以跨批差值宣称自动ID因果效应。设计`docs/research/2026-10-20-build-auto-provenance-baseline-design.md`。

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
| #502前瞻性比较 | 24/24 strict、12完整配对，inventory `2df552e2a26dac451b4d61690c4bc3eac59fee2fd0dcc0b3604f25c84905a91d`，独立审计通过、估算$2.88930180 | 请求/Token更少但费用项目异质且范围跨0；19次手工ID拒绝；0plan交接，下一步#504强接口探针 |

所有新任务均为独立身份，旧失败、部分观察与冻结原始证据只读。#484四项目人工参考资格已全部通过，#486读取接口失败与#478 libusb响应合同停止等前序结果见各版本化报告；不能当新主线总体负结果，也不续跑旧身份。

## 本轮授权、费用与停止

用户已授权Issue→实现/实验/测试→commit/push→PR→最新head检查后合并→关闭Issue，并持续同步知识库。跟踪#470，协议`docs/research/2026-10-19-continuous-research-authorization.md`。

- 各阶段共享新增Provider上限$20；已知保守估算累计$5.80615200，另旧live未知费用预留$1，预算占用$6.80615200；#504与#506预留已分别按$1.50885768/$0.09434832结算，无活动付费阶段。
- 估算不是账单，预留不是实际支出。共享账本`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/{authorization.json,budget-events.jsonl}`。
- 绝对截止北京时间2026-10-20 07:00，即UTC2026-10-19 23:00；最后15分钟仅清理/交接，不能跨午夜顺延。各阶段可更早停止新槽位准入。
- 预算耗尽后可做有效零支出工作。重大主线变更、超预算或需放宽科学主张边界时保存状态等待用户；普通阶段切换不需重新询问。

## 发布与工作区

#491/#494/#497均核验对应最新head的三项实际CI成功后合入依赖分支，#489/#492/#496关闭。#495已核验98236292三CI并合入依赖分支，#493关闭；#499控制结果6a69e738三CI通过后合并（f95f72d7），#498关闭；#501两Make结果bd9cb38e三CI通过后合并（72bdb55c），#500关闭。#503已核验adc54403三项实际CI全SUCCESS后合并（df830217），#502关闭；#505为#504独立探针PR，协议a598925a三项实际CI通过，最终a5624a3e三CI后已合并26b58e3a，#504关闭。合入依赖开发分支不等于进入main；不把约176个历史未进main提交一并发布。用户未跟踪的`docs/research/2026-10-13-forge-research-progress-defense.html`不修改/提交。

相关阶段本地回归与Ruff通过，检查以各自报告、PR和head为准；默认产品回归必须`CI=true FORGE_RUN_CLIENT_LIVE=0`，不得意外触发付费live测试。知识库固定入口为`01-研究/自动化编译/Forge-当前创新机制与实验路线.md`，只通过knowledge_base MCP维护，写前读取最新SHA、CAS写入后回读；不复制Vault或注入正式实验Agent。

## 历史停止决定仍有效

| 历史身份 | 决定与边界 | 权威入口 |
| --- | --- | --- |
| #440 H0/H1 v3 | strict19/27→22/27、成本下降50%，但非劣下界-0.111未过-0.10且Make/Autotools退化；H1不再单独作为主创新 | `benchmarks/reports/cpp-progress-aware-harness-comparison-v3-authorized.md` |
| #455 H0/H1/H2 v2 | 各6/6，无closure rejection/repair激活；不能证明H2可靠性增量，不追加相同全成功样本 | `benchmarks/reports/cpp-progress-aware-h0-h1-h2-runtime-v6-formal-comparison-v2.md` |
| #463/#465 Jev | 校准覆盖不足，逐动作分解/ActionCard未转为有效覆盖；停止进入controller，不补跑或降阈值 | `benchmarks/reports/cpp-jev-progress-budget-calibration-v1.md`、`cpp-jev-action-safety-decomposition-v1.md` |
| #467依赖/配置A0–A4 | 未得到至少3个强Agent后仍未解且有合法修复依据的残余难题；停止A5，不等于否定自动化编译硕士主线 | `benchmarks/reports/cpp-dependency-configuration-agent-investigation-v2.md` |

历史#408受控失败正向结果、#457状态/BudgetFit benchmark与其他历史观察继续保留各自原主张范围；新路线不重写旧结论。
