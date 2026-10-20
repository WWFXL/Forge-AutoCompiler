# libconfig供应header模板：独立configure环境资格

Issue #565。原cross-system-reference-v1为tinyxml2合格、libconfig不合格（1/2）；后者虽完整8PASS+1原XFAIL、16 tinytest和精确交付/重放工程通过，make自动调用autoheader改写原ac_config.h.in，仍违反原文件SHA合同。原失败永久封存，不能重启或回填为2/2。

独立cpp-build-cxx-cross-system-reference-header-v1只运行原libconfig。唯一修订：将configure前缀设为AUTOHEADER=true，延续bootstrap阶段已有选择。冻结证据中的configure使用AUTOHEADER=${AUTOHEADER-...autoheader}，原Makefile为missing autoheader；因此仅在autoreconf进程设变量不能防止后续make重生成。新命令使configure产生AUTOHEADER=true的Makefile，继续使用源码已供应且含必要宏的ac_config.h.in；不删除/还原/修改模板，不修改源码或测试，不忽略编译与测试退出码。

原任务来源、完整测试命令、8PASS+1XFAIL、C++及两静态库交付、Git索引/no HEAD/所有原文件SHA、同镜像2CPU重放和cleanup逐字段保持；预算和UTC22:07:35绝对截止/3300秒新项目预留不变。0Provider/凭据/模型费，无重试/补槽；若仍改写原文件，保留失败，不豁免合同。通过也只建立已见参考资格，不作为方法效果。后续有效池可分别引用tinyxml2原身份与libconfig新身份，不称原身份2/2。
