# 新库完整依赖输入图

Issue625，cpp-build-library-inputs-v1，原8小时/20美元共享窗口不变。本阶段0模型/凭据/源码执行/Docker。

父完整来源rank8/16/18精确commit保持。rang补doctest v2.4.11；ELFIO补其CMake3.28分支声明GoogleTest v1.16.0；bit7z按作者默认26.01补rikyoz/7-Zip、原精确commit filesystem/Catch2、原v1.18.2测试数据、原SHA256固定CPM0.42.3。标签首次解析成精确commit保留原响应，再一次codeload，无自动重试。失败/部分文件保留；三项固定队列不替换。副作用仅在全新输入归档，不覆盖父文件。仅移除codeload外层目录，原普通文件字节/链接文本保持；新增依赖位于.forge-deps。

全部输入由三策略共同获得，是固定依赖资源任务，不称无辅助开放网络仓库全流程。原依赖的构建/使用仍须实际执行；不提前授资格。后续参考配方不注入实验Agent，原源码/测试不改。rang和ELFIO为header-only，后续须明确原有编译端点和作者测试，不能伪造静态库或把空CTest记成功。
