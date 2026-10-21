# rtorrent原注册名解析修复独立参考 v2

2026-10-21，Issue581。v1完整编译/精确暂存通过，原依赖前2程序退出0且2+17叶通过；第二程序因作者CPPUNIT_TEST_SUITE_NAMED_REGISTRATION的torrent/net注册前缀未被解析器接纳而误拒，后10程序/CLI/replay未观察。v1 inventory37fba75a47d6ff13e194a5fbd6a7025e57ce0cfbf30bad32392261383329b4a5永久保留，不续跑、不回填。其budget_exhausted是0handoff上限触发的Workflow终态，实际剩余1948秒，不是Token或墙钟耗尽。

v2只修复作者注册名处理：从同一原Makefile.am的各SOURCES实际.cc读取具名注册宏，将registry前缀纳入精确叶身份；允许作者torrent/net等斜杠，不剥除任意前缀。原323叶声明/12程序/CppUnit总数/无重复/退出码及全部源码、生成、配置、交付、镜像、2CPU/无网络、plan/replay时限全部继承v1，原免费07:26:27截止不延长。旧冻结组件不修改；新代码/回归/manifest先冻结提交后全新空原执行及全新空replay一次，无自动重试或旧工作区继承。新期望名来自作者源码，不由通过结果决定。0Provider/模型费/凭据，不当方法效果；失败/未观察保留。
