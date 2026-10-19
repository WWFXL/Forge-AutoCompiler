# 三系统受控错误的零模型强规则恢复资格

Issue #516，身份`cpp-build-rule-recovery-qualification-v1`。观察#506模型修订后设计的开发资格，不是holdout或公平效果比较。固定同miniz/pigz/libite三项目、人工初始方案、受控错误、source/image及完整固定测试/源码不变/精确交付/replay/cleanup合同，各一次串行、不替换或补跑。

规则函数只接收当前坏方案、权威handoff实际失败记录及源码文件名，不接收正确人工参考或旧模型修订：CMake明确未知--target且日志与参数同名则去掉该单一target；Make明确CC=覆盖的编译器缺失则去掉覆盖使用冻结镜像默认工具链；Autotools ./configure确实不存在、存在configure.ac/Makefile.am/autogen.sh且仅有一个先前configure noop时，将该noop改为./autogen.sh。无覆盖则停止，不调用模型；当前计划hash不符、超时或错误证据不吻合均拒绝直接规则。以上只是限定开发任务的候选规则，不作一般安全性/覆盖率保证。

人工正确参考只用于初始方案及与父相同的注入；传入既有run_arm的scripted_model不会被调用，NoProviderMeter在任何请求前直接拒绝。规则函数接口与独立测试保证不消费该参考，也不读取父模型修订。stage 0凭据/0Provider/0模型请求/0Token；九项测试覆盖固定测试保持、误匹配/陈旧/超时/源码证据缺失及禁止模型请求。

时限收窄：meter节点300秒、单命令120秒、evaluator/replay各180秒、cleanup120秒，2CPU/最多32命令，原Workflow wall1200不作为准入依据；meter逐动作时间门禁将节点执行收窄到300秒，加在途命令/evaluator/replay/cleanup仍由1200秒保留覆盖。阶段UTC22:45截止，新项目保留1200秒，即UTC22:25后不准入。资源预算与#506不同，不做成功率/成本因果或非劣比较。保留失败/未观察，不用部分成功声称三系统资格通过。

create-once独立封存父/源身份、65组件及全轨迹；独立审计预定初始失败/交接/前缀保留/后缀失效、固定测试与源码、配方不含失败/失效命令、replay/cleanup、0模型调用。正向只说明这三已见简单受控错误不需要模型也可闭合，不证明规则优于模型或自然失败可无模型处理；以后不能把它们当语义机制优势样本。
