# 两项Make完整自测与干净交付参考资格

跟踪#500，独立身份 `cpp-build-make-reference-v1`；#470跨阶段授权下0Provider/0模型费用。父来源#496，固定libhydrogen、buffer，不将仅演示或缺子模块的项目替换进来。此阶段是人工参考任务资格，不评价模型、状态选择器或总体成功率，不宣称最终holdout。

固定完整commit/codeload原始归档，剥除外层目录形成tar，普通文件字节和链接文本不变；保存普通文件哈希。libhydrogen使用原Makefile的make lib，make check实际执行tests/tests的全部12个测试函数，使用命令输出`tests/tests && touch tests/tests.done`证明执行到测试，不加入NDEBUG、不选择性删测试。交付libhydrogen.a。

buffer依原Makefile编译buffer.c和test.c，原make test再次编译并运行全部18项断言测试；固定成功输出绿色勾号后的ok文本，交付真实test ELF并在干净环境重建重跑同一完整测试。测试程序是明确的本任务交付，不把它说成独立生产命令行产品。默认smoke实际运行同一main，不使用--help演示代替功能测试。

每项2CPU、方案32命令/0交接/900秒、单命令180秒、replay600秒。一次运行不重试、不自动修订、不替换失败项目；单项失败保留继续，cleanup失败整批停止。真实执行排在#493和#498之后，不并行重型构建。UTC22:45前至少保留3000秒才启动新项目，总截止UTC23:00/北京时间07:00和最后15分钟交接不变。

通过须原始源码普通文件未变、完整功能自测成功、精确交付且为有效ELF/ar、空源码clean replay、交付路径/类型/大小/SHA-256与smoke一致、重放完整测试、cleanup后completed。失败退出码、源码漂移或原始协议错误均保持原分类，不作方法负结果；修正需新身份。冻结全部原始日志、Session、源码索引、产物及代码快照，封存后独立审计。后续模型角色和评估边界须在新模型outcome前另行冻结。
