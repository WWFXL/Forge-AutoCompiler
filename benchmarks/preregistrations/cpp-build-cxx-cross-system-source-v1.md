# C++ Make与Autotools固定来源资格

身份cpp-build-cxx-cross-system-source-v1，Issue561。基础设施阶段：补本轮新增C++样本全为CMake的覆盖缺口，不产生构建成功率或策略效果。固定tinyxml2@321ea883b7190d4e85cae5512a12e5eaa8f8731f（10.0.0，拟Make）和libconfig@a42cb47c1526a4f2ed025fcbb2289863375bc898（v1.8.2，拟Autotools，C/C++接口），不按构建结果替换项目或commit。

只读公开metadata/tag/commit/recursive Git tree与固定commit codeload。先核对tag直接commit对象与固定SHA一致，tree未truncated、无gitlink，再检查归一化tar每个普通文件内容、链接文本与执行位对应该tree的Git blob；额外/缺失/重复/内容/模式/不安全路径/链接或不完整来源均拒绝。复用既有安全检查，只移除外层目录，保留原文件/链接/模式；不修改归档、测试或冻结证据。来源每次获取不自动重试，首失败即停，后续未观察保留，不续跑该身份。

每归档压缩≤32MiB、展开≤256MiB、单文件≤32MiB、成员≤20000，摘录≤16000bytes，最终值以manifest为准；无源码执行、无Docker、无凭据读取/真实Provider/模型请求/Token/模型费用。gh仅使用已有认证读取公开元数据，不调整认证或网络。截止继承本轮UTC22:07:35，不延长4小时，也不挪用旧授权。

开发助手已读两项目固定commit的根Makefile/README/Autotools配置/作者CI与测试入口，准确暴露在登记中；不能当训练未见或holdout。tinyxml2 Make默认构建静态库+xmltest，自测由check执行；libconfig原make check递归包含C/C++示例，C++example4原XFAIL保留；这些仅为作者文件内容判断，实际测试数/产物/原源码不变/完整replay尚未观察。本身份不定义或估计方法效果，不改变RQ3原分母。

封存源归档、逐文件sha256和Git元数据/树/对象对应收据，独立stdlib实现重新从tar与Git tree复算并核对归一化前后内容、模式与链接，不导入来源采集器。只有来源通过后，另冻结原作者参考任务/构建与固定完整测试、精确交付、同镜像2CPU clean replay/原源码/索引与cleanup资格，不把来源成功冒充构建成功。文献/人工参考不注入未来真实Agent。
