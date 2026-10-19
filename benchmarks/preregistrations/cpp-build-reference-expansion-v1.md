# 扩展来源完整参考任务资格 v1

跟踪#493，身份 `cpp-build-reference-expansion-v1`，沿用#470跨阶段授权，0Provider/0模型费用。本轮是人工参考任务的数据资格与基础设施，不评价模型或方法效果，不构造自然失败总体。

父来源为#492冻结的12候选目录，inventory `49214164eab150f68fe950975cc81e8b36f143534545068ce2751c4137f39c62`。按既定顺序运行其中10项：uncrustify、libpng、libzip、libsndfile、libtommath、libtomcrypt、libsodium、libverto、check、libffi。FastLZ因未固定语料子模块、HDiffPatch因相邻依赖/完整oracle未闭合，明确暂缓并保留，不替换。

每项固定同一完整commit、原始codeload归档和普通源码文件哈希。只剥除归档外层目录，保存规范tar哈希，普通文件字节和符号链接文本不变；归档规范化不添加人工修改。每项一次独立干净Session，人工参考方案写入manifest；真实canary全部结束后才运行，不并行重型实验。

功能合同：CMake全量CTest并使用no-tests=error；固定smoke同时核对CMakeCache中的测试/功能选项。libpng启用PNG_TESTS/PNG_SHARED/PNG_STATIC；libsndfile固定静态库、BUILD_TESTING、外部codecs和MPEG，安装对应开发依赖，不以缺依赖自动关闭特性。libzip启用全部regression，nihtest固定1.11.1，安装bzip2/lzma/zstd/OpenSSL等依赖；不因缺测试工具关闭测试。libtommath和libtomcrypt显式运行./test，后者固定GMP数学后端，不关闭算法自测。Autotools完整make check；libverto安装glib/libev/libevent三个后端；check保留timeout tests，仅文档不在交付任务范围；libffi使用DejaGNU，要求expected passes>0且无FAIL/XPASS/ERROR，disable-builddir只固定输出布局、不删测试，文档不在任务范围。

人工方案不自动修订，不重试失败项目，不根据结果换命令或放宽marker。单项目构建、测试、交付、源码或replay失败保留并继续其他预定项目；只有cleanup失败或基础设施不可审计才停止整体。未开始槽位保留为not_started，不作失败重填。失败后若需修正只能另建版本/身份，旧原始目录永久只读。

每项2CPU、max_commands32、max_handoffs0、方案墙钟1800秒、单命令600秒、严格验收/replay900秒，使用现有独立短cleanup时限。镜像固定sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a。开始新项目须距离UTC22:45至少3000秒；最后15分钟只清理交接，总任务UTC23:00/北京时间07:00截止不变。

通过要求：固定完整功能测试实际执行且成功、精确交付路径集合、至少真实ELF/ar、来源/命令配方可审计、从空源码环境重建、交付集合/类型/大小/SHA-256一致、重放完整测试成功、原始源码普通文件未变、cleanup后Session completed。无模型回调或凭据。保存原始/重放完整日志、命令、产物和失败，类型化封存后独立审计。

历史暴露按#492报告保留：libtommath/libtomcrypt/check已有实际开发，libsodium/libffi有metadata命中，有限URL搜索不证明其余项目全历史未见。此阶段不预先宣布最终holdout，之后在未看新模型outcome前另行冻结评估身份与角色。
