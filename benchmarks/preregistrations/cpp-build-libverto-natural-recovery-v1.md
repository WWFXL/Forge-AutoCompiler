# 已见libverto自然失败的最小配置恢复资格

Issue #524；身份`cpp-build-libverto-natural-recovery-v1`，单槽一次，0Provider/凭据/Token。观察#504与#522后设计，不是holdout/自然失败率/算法比较。固定#504 libverto源/镜像/完整六测试/精确静态交付任务，初始方案逐字为libverto-r2-plan/plan-1，不重新规划。

真实执行至固定make check失败后才接管。必须是当前revision1/hash、check/make check exit2非超时、完整test-suite.log TOTAL6/PASS0/FAIL6与六个上下文创建断言、config.log无builtin。否则保留停止。唯一修订是configure命令disable-shared换enable-shared，保留enable-static、全部依赖/后端/固定测试/交付及其他步骤；更新修订来源说明，不接收正确人工参考。修订后若再失败停止，不重试。

2CPU；meter节点180s、命令60s、evaluator/replay120s、cleanup60s，总600s准入保留覆盖180+在途60+验收120+重放120+清理60（540s），UTC22:45截止，22:35后不准入。父资源不同，只作后验单例机制资格，不作成功率/成本因果。父初始规划与恢复成本不扣除。

验证初始0/6真实复现、一次handoff/revision2、保留dep/autoreconf前缀、configure及旧成功build失效、固定完整六测试/原源码/精确交付/clean replay/cleanup；最终配方不含旧失败/失效命令。create-once raw+全部组件快照/typed封存，7项针对性测试通过后才执行。独立只读审计后报告；不能把新成功回填#504，也不能称自动学会规则、自然恢复率或P2增量。
