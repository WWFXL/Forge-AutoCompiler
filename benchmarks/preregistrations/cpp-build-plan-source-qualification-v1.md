# 新来源参考方案零Provider资格 v1

跟踪 #482。只验证参考任务可执行性，不比较模型/选择器；0Provider、0凭据读取、无付费预算。来源目录 `forge-build-source-catalog-v1` 已封存，inventory `4f97f8b1f0963eec12d1e5df41464d46a0090458ea6bc80fa89e8ae5044c4705`。新根tar与完整参考方案、固定测试在首次构建前绑定manifest。

固定顺序miniz、md4c、pigz、libite。四者源码读取后成为开发项目，不当未经暴露的最终holdout。每项目一次干净Session，无自动修复/重试/替换；失败后继续下个固定项目，cleanup失败则停止。zlog Make oracle未固定与错误owner404来源不进入本阶段，不能填作失败构建。

使用既有方案原型：600秒Workflow、最多32命令/2交接、120秒单命令、180秒replay、2CPU；不调用恢复模型。父进程1500秒保底超时不把超时当科学失败，出现此异常须核验并清理确切资源。截止UTC2026-10-19T23:00:00，启动每项目至少保留1800秒。

miniz：默认库构建加显式BUILD_TESTS=ON，CTest须包含catch_tests且100%通过；不关闭测试。md4c：静态库链接md2html，执行原`python3 ../scripts/run-tests.py`（工作目录build），包含全部原suite及病理测试，保留上游允许失败，不以空CTest替代。pigz：原`make test`（不是更广的`tests`目标），保留上游条件compress分支和原Shell语义；要求完整命令成功及真实测试输出。libite：原autogen/configure/make和全部21项make check，不改权限敏感断言或去掉测试。

每个项目固定精确交付：libminiz.a、md2html、pigz、libite.a。原任务测试先成功，再产物结构/默认可执行smoke、显式recipe、同不可变镜像与空目录clean replay、重放测试、产物路径/类型/大小/SHA256相同及cleanup，才算qualified。新增生成文件允许，原始普通源码/测试逐文件哈希不得变化；原始符号链接身份绑定tar。失败日志、Session终态和原源码变化均完整保留。

阶段结果封存inventory并独立只读审计。只有四项均合格才讨论该固定集合的三系统端到端比较；否则先解释失败与修复可行性，新的修订以新身份保存，不在本阶段选择通过子集当预定样本。任何成功不构成方法效果、泛化或成本节省。
