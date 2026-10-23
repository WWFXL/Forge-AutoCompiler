# 新库独立参考资格

Issue625；cpp-build-library-reference-v1；原8小时/20美元共享窗口不变，本阶段0模型/凭据，固定rang、ELFIO、bit7z三项依序，每项一次，不自动重试或补位。输入沿完整来源/依赖固定commit归档，完整文件SHA原始/依赖均保持，允许新增构建/测试输出。

rang：原CMake三个测试程序，doctest v2.4.11、6测试/15子分支、原CTest入口及colorTest/envTermMissing输出检查，精确交付all_rang_tests/colorTest/envTermMissing。ELFIO：作者默认全部示例与测试ON，GoogleTest v1.16.0、原82测试叶/83CTest注册（整包+叶注册），全部CTest，无过滤；精确交付ELFIOTest。两者是header-only的作者原有编译端点任务，不冒称静态库或公共头文件安装包。

bit7z：原默认26.01/功能，7-Zip真实共享模块及原精确filesystem/Catch2/测试数据，文件系统测试保持ON；三个作者程序bit7z-tests/bit7z-tests-public/bit7z-tests-public-cpp20均完整默认执行、无过滤、非空统计，交付真实libbit7z64.a。作者原生隐藏/平台条件和root权限跳过分支保留并单列，不能将未执行分支当通过。一次配置/功能不是整个作者CI矩阵。

同一不可变镜像/2CPU，参考主执行1800秒、命令1200秒、replay1800秒，无handoff；新项目预留3900秒，原总截止不延期。失败/未观察保留。完整测试、原源码、精确交付、同镜像clean replay与实际cleanup全部通过才授资格。参考配方仅开发助手读取，不进入方法Agent；比较任务只取task及共同源码依赖材料。

工具规划器边界预先声明：任务给定CMake，原task-selected通用模板只生成BUILD_TESTING配置和build，项目特定配置/依赖需真实失败后升级；不称自主多系统选择或按新项目定制配方。三项目仍属CMake，不称新增跨系统覆盖。
