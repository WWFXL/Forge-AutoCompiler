# rtorrent完整原测试、精确交付与干净重放独立参考 v1

2026-10-21，Issue581，用户明确授权本次免费参考。身份cpp-build-rtorrent-reference-v1；0Provider/凭据/Token/模型费，准备/原运行/重放均占UTC05:26:27至07:26:27。独立来源准备通过且封存后才冻结本合同；其bootstrap输出不是策略效果。禁止重复旧身份、换版本、删测试、按结果放宽边界。

主源rtorrent d316b21cf02ae923d0cb1b6e75064a05016238bd，源依赖libtorrent c395f0af3924bb4c8514cfa3b0c46c78787ddc64，同0.16.25。根目录为主源，vendor-libtorrent为源依赖；联合原归档SHA f85e5968162b13452efff1dc86c3d8d616dee2952232b539810a4c500418f0b4；818原文件全部受保护。镜像sha256:8f3ef0a3b83948b454563ee89f5ff941d91e1034a5ba1c08696e2a11ced64e10及完整dpkg版本/包清单SHA bb3d977ee427e7427f82ef6bbad05d67aab26eb1c6bd1ccb29d9a4d312aa7b88固定，含gcc/g++13.3、Autoconf2.71、Automake1.16.5、Libtool2.4.7、CppUnit1.15.1、curl/OpenSSL/ncurses/zlib。系统递归依赖以不可变二进制镜像/全包清单闭合，不声称重建所有系统包源码。

2CPU、Docker network none，原执行与replay同镜像、同资源、全新空workspace/artifacts；无apt或来源网络。plan最多32命令/0handoff/2400秒、每命令1200秒，replay2400秒，新运行准入至少5100秒清理预留。任一步失败/超时分类保留，后续未观察不填失败/通过；无自动重试或补槽。原运行无外部Agent，可执行固定人工作为开发参考，不能进入RQ1策略效果或holdout。在协议deadline前保留完整清理/封存预算。

标准生成只允许两条确切autoreconf命令及其校准40新路径/新SHA，全部818作者源码、测试、configure.ac、Makefile.am及手写宏保持。autom4te.cache为显式新中间目录；两独立build目录仅容纳构建产物，config.h两个路径精确声明；不允许新增源码/测试，路径/事件/先改后恢复按现有B边界检查。所有生成来自本任务校准，不套用libconfig白名单。源码依赖完整configure/build/install是主任务dependency步骤，每步只有一个逻辑动作；主任务configure/build随后执行。

功能配置使用两项目默认功能：libtorrent共享库与原debug断言、rtorrent ncurses，未显式启用的Lua/XMLRPC/systemd保持作者默认；不为通过关闭原测试。CppUnit缺失即失败。采用前瞻-O0和固定路径映射以控制资源且保留默认-g/-DDEBUG，时钟/随机测试仍原样执行。

完整原程序来自Makefile.am的TESTS/check_PROGRAMS和SOURCES，冻结全部CppUnit叶声明（剔除源码注释，不是结果后过滤）。rtorrent_Test_Core/Rpc/Src分别1/36/65，共102；libtorrent九程序2/17/4/40/108/21/9/3/17，共221。构建原check_PROGRAMS，然后依作者程序在对应build/test目录直接逐个运行，unset TEST_NAME，不传过滤参数；与原TESTS列表同集合，不运行缩小替代程序。每程序120秒，保存完整stdout/stderr与退出码；退出0、CppUnit正总数及全部叶身份精确一致/无重复才能通过，不能缺依赖后空测试。该分母是原默认功能配置下声明的测试，不声称所有可选特性或每个函数体都有非空断言。

精确交付只有真实rtorrent ELF和libtorrent.so.53 ELF shared两文件，后者复制原libtorrent.so.53.0.0的真实字节而非别名链接，符合源CURRENT53/AGE0/REVISION0。交付后执行/artifacts/rtorrent -h，LD_LIBRARY_PATH仅/artifacts，必须打印作者0.16.25版本及Usage，验证消费交付的同版本库。受信参考把“全部323原叶测试+交付CLI”唯一成功命令绑定到executable policy，处理该程序只支持-h、现有默认长选项不兼容的问题；不修改通用smoke默认或减弱完整测试。

使用原Compile Session/严格Shell/显式recipe/原镜像clean replay/精确集合、类型、大小、SHA256及验证命令输出一致性/最终cleanup验收。原及重放测试日志全部保留；只将已核验的固定测试身份/通过数/CLI版本打印为确定性摘要，原测试输出中的临时路径/时间保存在文件，不通过删失败或伪摘要求一致。stdout摘要缺失/任一测试身份不符即失败。最终Session completed且replay passed和实际cleanup成功才qualify；源码与生成边界在两次运行相同。

组件/原引用/合同先测试提交后执行。封存后独立清单/包镜像/原及replay818源码、生成/323叶测试/真实交付/replay/容器不存在审计。结果仅回答该固定任务在该环境是否具备完整参考资格，不估策略优劣、自然失败/恢复率或总体成功率；保留其他候选、旧libconfig九槽/RQ3/P2/主线与用户HTML。
