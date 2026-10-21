# rtorrent独立参考准备 v1

Issue581，用户明确要求冻结完整任务并执行参考。免费窗UTC2026-10-21T05:26:27至07:26:27，准备计入。0Provider/凭据/模型费，不继承旧截止。此身份只准备依赖镜像、两精确源码装配及标准bootstrap生成关系，不configure/编译/测试，不计任务成功。

精确源：rtorrent d316b21cf02ae923d0cb1b6e75064a05016238bd及libtorrent c395f0af3924bb4c8514cfa3b0c46c78787ddc64，均0.16.25。父证据清单、树/归档全部核验后，仅去codeload前缀，后者置vendor-libtorrent，保留原字节/模式。拒绝符号链接/重复冲突/gitlink，两个原文件集合全保护。

基于固定gcc13镜像d27a6ab733c7构建准备镜像，仅安装autoconf-archive/libcppunit-dev/libtool-bin及apt解析依赖，网络重试0、build600秒；最终image_id、完整dpkg包版本与工具链输出冻结后才能正式参考。系统依赖以完整二进制镜像/包清单闭合，不声称可重建所有系统包源码。Dockerfile和运行组件先测试提交，build无自动重试，网络/源失败封存不补跑。

隔离容器2CPU/8GiB/无网络，只分别执行cd vendor-libtorrent && autoreconf -ivf及autoreconf -ivf，每次180秒。全部作者文件原字节保持，否则准备失败。标准新生成输出逐路径SHA256登记，autom4te.cache为中间目录另记；不将作者源码/测试/语义输入声明成输出。原日志/完整前后清单/source快照与失败封存，容器清理且实际不存在后结束。正式构建、完整libtorrent九测试及rtorrent三测试、交付/replay须另身份、先冻结合同，不在准备身份执行。
