# rtorrent完整任务冻结与独立参考构建结果

2026-10-21，跟踪Issue #581。本阶段为任务资格数据采集、验证脚本工程修复和独立审计；没有模型策略效果比较。

**结论：固定rtorrent与同版本libtorrent的完整任务资格通过。原执行和空目录clean replay均执行12个原测试程序、323个叶测试，并通过CLI、818原文件保护、40生成文件SHA、精确两ELF字节一致性与实际cleanup。模型费用为0。**

## 冻结的完整任务

| 项目 | 固定要求 |
| --- | --- |
| rtorrent源码 | `d316b21cf02ae923d0cb1b6e75064a05016238bd`，0.16.25 |
| libtorrent源码依赖 | `c395f0af3924bb4c8514cfa3b0c46c78787ddc64`，0.16.25 |
| 组合源码归档 | `f85e5968162b13452efff1dc86c3d8d616dee2952232b539810a4c500418f0b4`；仅去codeload目录前缀，依赖置vendor-libtorrent |
| 二进制依赖环境 | `sha256:8f3ef0a3b83948b454563ee89f5ff941d91e1034a5ba1c08696e2a11ced64e10`；完整254包版本清单SHA `bb3d977ee427e7427f82ef6bbad05d67aab26eb1c6bd1ccb29d9a4d312aa7b88` |
| 资源与功能 | 2CPU、无网络；原及replay同一镜像；默认功能、原debug断言；-O0与固定路径映射 |
| 原文件保护 | 818原作者文件，包括源码、测试、configure.ac/Makefile.am/手写宏等构建语义输入；不允许改写 |
| 正常生成 | 两次autoreconf -ivf；依赖19+主项目21个精确生成输出；独立SHA固定。缓存及两个out-of-source构建目录按任务声明 |
| 测试边界 | 主3程序102叶+依赖9程序221叶；移除TEST_NAME环境变量，逐程序退出0、全部精确叶身份、无重复及唯一CppUnit总数 |
| 精确交付 | 普通ELF文件/artifacts/rtorrent及/artifacts/libtorrent.so.53；复制真实.so.53.0.0字节，不交付别名链接 |
| CLI与重放 | 对交付rtorrent以LD_LIBRARY_PATH=/artifacts执行-h，要求0.16.25及Usage；完整测试留在verify配方，既有显式functional policy只绑定独立交付CLI，不改产品默认smoke |

系统依赖冻结的是不可变二进制镜像与完整已安装包版本，不主张所有系统包都从源码重新构建。核心环境为gcc/g++13.3、Autoconf2.71、Automake1.16.5、Libtool2.4.7、CppUnit1.15.1及curl/OpenSSL/ncurses/zlib。完整清单位于准备raw的packages.tsv；生成路径、命令、输出哈希与全部原文件哈希以版本化manifest和准备证据为准。

## 原测试程序分母

| 来源 | 原程序 | 全部叶数 |
| --- | --- | ---: |
| libtorrent | `LibTorrent_Test_Protocol` | 2 |
| libtorrent | `LibTorrent_Test_Torrent_Net` | 17 |
| libtorrent | `LibTorrent_Test_Torrent_Runtime` | 4 |
| libtorrent | `LibTorrent_Test_Torrent_Utils` | 40 |
| libtorrent | `LibTorrent_Test_Torrent` | 108 |
| libtorrent | `LibTorrent_Test_Data` | 21 |
| libtorrent | `LibTorrent_Test_Net` | 9 |
| libtorrent | `LibTorrent_Test_Tracker` | 3 |
| libtorrent | `LibTorrent_Test` | 17 |
| rtorrent | `rtorrent_Test_Core` | 1 |
| rtorrent | `rtorrent_Test_Rpc` | 36 |
| rtorrent | `rtorrent_Test_Src` | 65 |

这些程序和叶身份来自作者test/Makefile.am及其SOURCES中的CppUnit声明/具名注册。三个注释掉的声明不计入。直接构建并运行作者TESTS/check_PROGRAMS对应的全部原二进制；不改测试，不过滤或用空测试替代。运行中原测试可输出DNS诊断，但成功必须仍满足作者退出状态、全部身份和总数；不由诊断文字自行宣称通过。

## 各独立身份的实际观察

| 身份 | 原程序/叶观察 | CLI | clean replay | 资格 |
| --- | --- | --- | --- | --- |
| preparation-v1 | 仅bootstrap校准，未运行编译或测试 | 未观察 | 未观察 | 仅准备通过 |
| reference-v1 | 前2程序19叶退出0；其余10程序未观察 | 未观察 | 未观察 | 失败：原registry与多行诊断解析缺口 |
| reference-v2 | 前2程序19叶退出0；其余10程序未观察 | 未观察 | 未观察 | 失败：具名registry已修，多行格式仍误拒 |
| reference-v3 | 12程序323叶实际通过 | 通过 | 未观察 | 失败：生成脚本汇总时缺局部import json |
| reference-v4 | 12程序323叶通过 | 通过 | build/verify退出0、323叶通过；最终产物smoke超时 | 失败：全套测试误绑20秒产物smoke |
| reference-v5 | 12程序323叶通过 | 通过 | 全部严格检查通过 | 通过 |

前四个参考身份全部完整构建并暂存产物，但未达到严格资格终点。v1/v2的budget_exhausted是解析器拒绝后0handoff规则触发的终态，分别仍剩1948/1949秒；v3剩680秒，v4的约570秒timed_out来自产物smoke的20秒短时限，并非1200秒replay总上限，不能解释为模型预算或整轮墙钟预算耗尽。v3的原始tests字段为not_observed，代表外层完整验证步骤未成功；独立审计记录的323叶和CLI是细化观察，不回写或改变原终态。

修复均先以新文件/测试/manifest冻结提交，再使用独立空工作区执行；不续跑旧身份、不复用脏工作区、不修改原证据。v2从作者注册宏确定精确registry；v3按原listener的开始—诊断—结束事件识别成功，仍拒绝未知/重复/未闭合/失败叶与错误总数；v4仅将json导入置于生成脚本自包含函数内部；v5保持完整测试在verify配方中，另以独立交付CLI记录绑定产物短smoke，未延长任何smoke/总时限。回归实际执行生成python -c内容，在空globals下复现旧NameError并验证新汇总。

原免费窗口UTC05:26:27至07:26:27、准备计入、不延长。v1/v2的原执行/replay各2400秒、准入5100秒；依据两次约450秒的原编译观测，新v3/v4/v5收紧为原执行/replay各1200秒、准入2700秒，含300秒清理封存余量。验收不变；每个身份各一次、32命令/0handoff、单命令上限1200秒。

## 成功身份的独立重放与审计

v5运行release `d212fe7717dea52aadbd9a5cbe6a77092ab87aea`，原命令累计522.760秒，clean replay 547.342秒。原与replay均为818原文件保持、40生成输出精确SHA、323叶/12程序、交付CLI通过。最终Session为completed。独立审计不用正式seal实现，复算标准库类型清单、所有冻结组件Git对象、父证据、原及replay逐叶日志和总数、真实ELF字节及实际容器不存在。

| 精确产物 | 字节数 | SHA-256（原与replay相同） |
| --- | ---: | --- |
| `libtorrent.so.53` | 36557648 | `e1fb5e3cc780a0ab55c061876ae9b7f9590573516584184f38447f20bc845236` |
| `rtorrent` | 45339592 | `aa53e2cdeb02f8b525cea709bfa6a8411731bf5709a5fb10aca6ded3c7368c18` |

用户可在相同依赖环境中将两文件置于同目录，以LD_LIBRARY_PATH指向该目录运行客户端；本任务不承诺脱离系统依赖的静态单文件交付。静态readelf核验客户端实际需要libtorrent.so.53，库本身SONAME也为libtorrent.so.53；其余ncurses/zlib/curl/crypto/C++运行库等由固定依赖镜像提供，清单见会话elf-dependency-inspection.json。没有运行外部swarm/跟踪器端到端联网测试，不主张跨主机/跨架构复现。

## 证据、检查与下一阶段

准备inventory `068a733046409120a4dbddd7e0405076c7808d5be43e809b1ff662580d12c0f5`。

- `cpp-build-rtorrent-reference-v1`：`/home/yiwei/.codex/outputs/forge-rtorrent-reference-v1`；inventory `37fba75a47d6ff13e194a5fbd6a7025e57ce0cfbf30bad32392261383329b4a5`；独立audit valid=true。
- `cpp-build-rtorrent-reference-v2`：`/home/yiwei/.codex/outputs/forge-rtorrent-reference-v2`；inventory `25c21eb1fe9a6db60bafc9284fc2cfa1394063732b5dcfbb6480b71c6769afc4`；独立audit valid=true。
- `cpp-build-rtorrent-reference-v3`：`/home/yiwei/.codex/outputs/forge-rtorrent-reference-v3`；inventory `0e2db9e4dddaa681b29b4334c977f9eeda75cabe1336b6ce6b1227282aab7047`；独立audit valid=true。
- `cpp-build-rtorrent-reference-v4`：`/home/yiwei/.codex/outputs/forge-rtorrent-reference-v4`；inventory `a8525457265bad00a5ea65006624dbe6e29f16ebf88f42f0e4f91b3d0f2b4022`；独立audit valid=true。
- `cpp-build-rtorrent-reference-v5`：`/home/yiwei/.codex/outputs/forge-rtorrent-reference-v5`；inventory `c8521d231dfabfe2353eaf0f4172837f60780f12ad43b2cd058a377996ac9066`；独立audit valid=true。

完整派生结果：benchmarks/analyses/cpp-build-rtorrent-reference-v1-results.json。协议：benchmarks/manifests/cpp-build-rtorrent-reference-{preparation-v1,v1,v2,v3,v4,v5}.json及同名preregistrations。工程日志、失败审计及修正、独立审计实现和发布/知识库收据：/home/yiwei/.codex/outputs/forge-rtorrent-reference-session-2026-10-21/。首次环境检查的Shell格式错误、首次准备审计路径排序错误、首次参考审计不支持多行的错误日志均保留，原raw未修写。

相关针对性测试32项通过，后端产品2380 passed、44 skipped、27 warnings；Ruff及格式检查通过。历史pytest临时目录权限清理告警保留。没有前端改动，环境缺pnpm，不安装前端依赖。发布以最终结果HEAD的三CI及GitHub实际merge/Issue状态为准，只合科研依赖分支，不进main。

这增加一个具有完整源码依赖/系统环境、原测试与精确交付的C++任务资格，能用于后续公平比较准备；不产生规划收益、模型排名、自然恢复率或holdout证据。下一步先冻结该任务的开发助手/策略角色及项目族暴露，再验证三策略共同装配、测试、恢复和验收接口；付费比较需新的明确身份及有效预算/时窗。其他候选保持原pending、不按方法结果挑选，旧libconfig九槽/RQ3分母/P2/主线和用户HTML不变。
