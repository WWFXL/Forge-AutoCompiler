# C++ Make/Autotools完整参考资格 v1

Issue #565；固定#561来源tinyxml2@321ea883b7190d4e85cae5512a12e5eaa8f8731f（Make）和libconfig@a42cb47c1526a4f2ed025fcbb2289863375bc898（Autotools）。这是已见开发样本的参考任务资格，不是方法效果或holdout。

沿用本轮20美元/4小时授权，绝对截止UTC2026-10-20 22:07:35，准备计入；0 Provider、0凭据读取、0模型Token和费用。每新项目预留3300秒；32命令、0handoff、执行1800秒、单命令900秒、replay1200秒。单进程串行Docker，不重试/替换/补槽；清理失败立即停止后续，截止拒绝项目保持未观察。

tinyxml2执行原Make默认all（xmltest及staticlib）与完整make check，要求真实自测Pass为正、Fail为0，交付libtinyxml2.a。libconfig保持C++、全部tests/examples、静态库启用，仅排除非任务文档。其原ac_config.h.in已供应，因此AUTOHEADER=true autoreconf -i仅生成所需构建入口，不强制重新生成已供应模板；仍逐原文件核验，不允许改写后恢复或跳过核验。原测试依赖源码目录固定相对fixtures，采用in-source构建；若生成器覆盖原文件，资格失败，不放宽合同。完整make check要求9个Automake入口准确为8PASS+1原XFAIL（C++ example4），0FAIL/XPASS/SKIP/ERROR；另保留libconfig_tests完整tinytest输出。交付libconfig.a及libconfig++.a。

全部项目原执行和同不可变镜像clean replay均需完整测试、原源码SHA不变、共同Git索引原文件集合一致且无伪HEAD、精确交付集合/字节相等、实际容器cleanup。原源码、测试入口和XFAIL不修改；新增生成文件允许，改写原文件不允许。失败与未观察分开记载，不能由build退出0替代完整成功。

方案、镜像和组件SHA在同名manifest冻结；父source inventory 89e09bc2267593695a0dae54f9eda9d764d0afcc3af7ad780850d92c4f6aff5f。独立审计需读取原/replay日志及全部原文件、交付manifest与实际容器状态。通过后只允许设计共同输入/策略资格，不直接当方法优越性证据，不修改RQ3历史分母，不增加P2。
