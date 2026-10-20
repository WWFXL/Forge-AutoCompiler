# libverto 同源最小修订资格 v2

Issue #530；身份 `cpp-build-libverto-natural-recovery-v2`。依据用户2026-10-20四项继续指令，新时窗单槽一次、零凭据/Provider/Token/费用；不续跑 #524/v1、不调用模型、不估自然恢复率。机器协议为同名 analyses JSON，固定其全部组件hash和输出目录。

沿用 #504 原源码归档、完整commit/镜像、真实初始plan-1及完整六测试/精确静态库交付任务。初始方案逐字相同；显式使用 #526 planner v2。只有实际观察到 make check exit2、六项上下文创建断言且无builtin时，允许一次 configure 从 disable-shared 改 enable-shared，同时保留 enable-static。其余命令、测试、源码、交付要求不改；修订后再次失败即停，不重试、不替换。

2CPU；节点1200秒、命令600秒、evaluator/replay各900秒、cleanup120秒，准入保留3900秒（覆盖节点、在途命令、验收/重放、清理），UTC2026-10-20 03:30截止。与 v1 的资源不同，仅验证同源修订，不比较两身份成功率或成本因果。充足依赖资源不是放宽六测试/交付验收。

执行前新增入口接线/资源测试及相邻恢复回归通过、协议代码提交冻结。结果包括所有未观察/失败；raw create-once并封存组件和typed inventory。核验实际原失败、一次修订、保留dep/autoreconf前缀、失效旧configure/build、完整六测试、原源码不变、精确交付、clean replay、cleanup及0模型事件。未到原失败不得声称修订无效；通过也不回填父实验或宣称学习型选择器增量。
