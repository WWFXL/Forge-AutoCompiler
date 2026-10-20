# 新增C++完整参考任务资格 v1

Issue #554，用户持续科研/零费用实验授权。阶段是人工参考资格/基础设施，非真实模型效果。固定yaml-cpp/simdutf/snappy各一次干净Session，全部CMake；不宣称跨系统或大型C++泛化。

来源为独立固定来源图cpp-build-cxx-reference-inputs-v1。主commit、完整组合归档、每个依赖gitlink与字节hash均冻结，不改原普通源码，不复用旧工作区。镜像sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a、2CPU。

在首次构建前冻结任务：

- yaml-cpp：静态库、BUILD_TESTING/YAML_CPP_BUILD_TESTS/CONTRIB/TOOLS开启，使用其自带GoogleTest；完整CTest（含集成单测、source-list与pkg-config检查），交付libyaml-cpp.a。
- simdutf：静态库、SIMDUTF_TESTS/BUILD_TESTING开启，SIMDUTF_FAST_TESTS=OFF；保持tools和其他默认功能，不缩减测试参数。完整CTest及原默认编译目标，交付libsimdutf.a。
- snappy：静态库、SNAPPY_BUILD_TESTS/SNAPPY_BUILD_BENCHMARKS开启，保留全部原GoogleTest及benchmark构建（benchmark自身测试按上游默认不启用）；安装zlib/lzo2/lz4开发依赖且固定测试前检查HAVE_LIBZ/HAVE_LIBLZO2/HAVE_LIBLZ4，避免自动缩小可选对照功能；完整CTest，交付libsnappy.a。

完整CTest不使用-R/-E或过滤，--no-tests=error，保存verbose完整输出；固定smoke核对任务选项，必须非空运行且全通过。精确交付至少一真实ar，原/replay路径、类型、大小、hash一致；clean replay从空环境执行同配方及完整测试，cleanup/finalize均过才qualified。

每项目max_commands32/max_handoffs0/wall1800秒/单命令900秒/replay1200秒，开启新项目需至少3300秒窗口，绝对截止UTC2026-10-20T18:19:33Z。失败、超时、未观察不替换、不续跑；cleanup或基础设施不可审计则停止整体。任何修复必须新身份，不修改已封存v1。0Provider/凭据读取/Token/新增模型费，不继承旧预算调用模型。

本阶段通过只表示任务与严格裁判可闭合。模型成功率、自然恢复率、模板覆盖或成本优势均未观察。保留#552为基线、不改旧组件，不加P2、不改RQ3分母，不降低验收。后续公平比较仍须前瞻角色/关联登记及独立协议/有效费用授权。
