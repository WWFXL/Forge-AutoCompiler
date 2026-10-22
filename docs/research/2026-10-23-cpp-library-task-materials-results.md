# 固定20项C++来源的构建与测试合同材料审阅

Issue #623；身份cpp-build-cpp-library-task-materials-v1。当前工作为来源数据采集、静态结果分析和后续任务准备基础设施，不是新的构建效果实验。主36槽比较已完成发布，固定20项来源目录亦已完成发布，两者与本材料队列分开。

## 新增证据与范围

沿父目录原20个排名/精确commit与root tree，不按方法结果选样、不替换/补位。按预先冻结的文档/构建文件名、一级测试树及最多4项排序CI工作流，20/20采集终结，0失败/未观察，92个材料路径/62个Git树/92个blob/620831字节。20/20仅指完成已声明范围的采集，不表示完整源码图或任务合同闭合。全部task_qualified=false，参考构建/完整作者测试/精确交付/clean replay/方法结果仍未观察。

0新增模型Provider/模型凭据/Token/费用/上游源码执行/Docker。原4小时截止UTC2026-10-22 19:37:37不延期；主批估费仍$3.65815560/未知0/财务闭合，不混旧费用、不重试或补位。

## 逐项任务义务

下表是采集终态后的静态解释，不是预注册排除判据或可运行性排名。所有结论保留逐字引文、原文件行号、Git blob与SHA-256，见版本化JSON。原CI描述不是本机通过证据。

| 排名/仓库 | 原文能够确立的事实 | 后续任务闭合义务 |
|---|---|---|
| 1 rachitiitr/DataStructures-Algorithms | README介绍算法/数据结构教学，固定根范围未见构建入口；不能据此判定整个仓库不可编译。 | 需逐子目录确定单一作者目标、原测试和交付，不能将多个链接项目替代当前候选。 |
| 2 microsoft/DirectXTK | README明确Windows SDK；本仓库测试接入有WIN32条件，另指向外部测试库。 | 当前Linux任务尚未定义；需固定支持端点与外部测试图，不能把仅库编译当完整作者测试。 |
| 3 microsoft/DirectXTex | README明确WSL/GCC11支持，测试接入仍为WIN32条件。 | Linux库/工具构建与完整测试范围应分别核验，不凭DirectX名称排除，也不把零CTest当通过。 |
| 4 fastfloat/fast_float | 头文件库；FASTFLOAT_TEST默认OFF；补充测试默认ON并引用远端数据。 | 完整doctest/补充数据/嵌套build_tests图和交付端点待固定；旧有限暴露命中保留。 |
| 5 bloomberg/bde | 根CMake要求BdeBuildSystem，并进入thirdparty/groups/standalones。 | 需取得BdeBuildSystem和完整嵌套测试/资源；Readme.md不在固定大小写文件名范围，不能称README不存在。 |
| 6 microsoft/DirectXMath | 主库INTERFACE；非Windows需要sal.h；README指向独立测试仓库。 | 需冻结sal.h和外部测试源码，明确真实编译交付，不能交一个虚构静态库。 |
| 7 microsoft/DirectXTK12 | README声明Windows/Direct3D12环境，作者测试接入受WIN32条件约束。 | Linux下相同任务的适用性未闭合；不适用需合同证据，不能记模型构建失败。 |
| 8 agauniyal/rang | 主库INTERFACE；BUILD_TESTING默认ON，但all_rang_tests仅在找到doctest时创建；Linux CI安装doctest-dev。 | 优先补doctest版本、完整原测试叶/入口和源码图；交付须明确原有编译程序与头文件的角色，不能只看ctest exit0。 |
| 9 0voice/Awesome_c-cpp_Projects | README自述为500+项目的分类索引，根材料没有单一构建任务。 | 需确定当前仓库本身可定义的作者目标；不从链接中替补一个好构建项目。 |
| 10 cycfi/q | Q_BUILD_TEST/IO默认ON；infra子模块/自动获取，QIO测试涉及音频和MIDI依赖。 | 需闭合infra/音频依赖、资源与全部原测试；不为了省事静默关闭默认IO义务。 |
| 11 matt-42/lithium | 根配置要求Boost/CURL/PostgreSQL/OpenSSL等，进入多个libraries和嵌套tests；有vcpkg子模块。 | 数据库开发依赖、vcpkg固定版本和嵌套作者测试尚待闭合，不能仅根configure作为资格。 |
| 12 cneben/QuickQanava | 根配置要求Qt6 Core/Quick/Qml/QuickControls2，样例受选项控制。 | Qt版本与运行环境、src/tests原入口及实际交付待读；不能由本轮未采到测试CMake断言不存在测试。 |
| 13 jfalcou/eve | EVE_BUILD_TEST进入config依赖模块和嵌套doc/unit/random测试树。 | 配置选项、依赖与CPU/测试目标图待完整冻结；原有限暴露命中，不称新holdout。 |
| 14 digint/tinyfsm | README声明header-only，固定根范围没有构建/测试入口材料。 | 需审阅examples等子树，明确作者原有可编译目标；不因没有根标记断言不可用。 |
| 15 saucer/saucer | saucer_tests默认OFF；Linux后端依赖Qt或WebKitGtk，源码还有多个远端依赖。 | 需前瞻冻结backend、GUI测试运行环境、远端依赖图和全原测试，不能事后换轻端点当方法成功。 |
| 16 serge1/ELFIO | 头文件库，ELFIO_BUILD_TESTS默认OFF；测试使用GoogleTest并同时有整包入口和gtest_discover_tests。 | 优先补GoogleTest/二进制fixture/原示例图，区分CTest注册与叶计数；交付应是预先定义的原编译程序/头文件组合。 |
| 17 microsoft/DirectXMesh | README明确WSL/GCC12支持，但本地测试接入仍有WIN32条件。 | 需冻结DirectXMath/headers与外部作者测试，Linux构建可用性和完整测试任务分开判断。 |
| 18 rikyoz/bit7z | 真实STATIC库且有Ubuntu测试工作流；测试依赖7-Zip运行库和固定Catch2源码。 | 优先补7-Zip头文件/共享库、测试资料和完整CPM图，冻结原测试/库交付后独立参考；不能只构建libbit7z跳过原测试。 |
| 19 MITK/MITK | README支持Linux；默认superbuild和BUILD_TESTING，根配置含Qt6/外部项目图。 | 完整外部源码/测试数据/资源与交付边界未闭合，静态材料不是参考构建通过或失败。 |
| 20 Restream/reindexer | 根CMake委托cpp_src；Ubuntu CI存在gtest/CTest路径。 | 需进入cpp_src及原测试脚本/依赖图；readme.md不在固定大小写范围，不能宣称无说明或无测试。 |

## 对下一轮实验的影响

主36槽已给出继续工具候选＋状态触发升级路线的成本信号，不需要继续只重复现有六项目。本材料队列把扩样问题具体化为任务合同，而不是先要求新项目必须失败、必须体现策略分歧或必须胜出。应先补完整源码图、依赖版本、原作者测试入口/叶计数和精确交付，再独立参考与干净重放资格；资格通过才能进入新策略比较。

可先准备rang、ELFIO与bit7z三份有界合同草案：rang需doctest和原有程序/头文件交付定义；ELFIO需GoogleTest/fixture/示例源码并区分整包与发现的叶测试；bit7z需7-Zip运行库/头文件、Catch2、测试资料及库交付。该建议依据任务准备义务，尚未观察这些项目的新方法结果，不给三项构建资格、不替换原20分母或称holdout。header-only任务必须明确作者原有可编译端点，不能伪造一个.a，也不能只交空的interface target。

不能从项目名称或根标记排除平台：DirectXTex和DirectXMesh原文明确有WSL/GCC路径，但本地测试接入仍受WIN32条件限制，需要分开处理构建端点和完整作者测试图。根Readme.md/readme.md、Tests等大小写别名不在固定范围，未采到不等于没有；本轮不为更多好结果修改规则或重采旧身份。

## 验证与证据

2项局部门禁0.10秒（父完整20分母/snapshot拒绝缩样与篡改，已有真实git hash-object blob完整性）、Ruff/真实CLI通过；未重复免费完整构建或本地全量产品测试。候选准备一次误用系统Python3.10导入UTC失败，随后改项目Python，未创建正式raw/Provider，正式采集仅一次。

独立标准库及原生git hash-object重新核验完整typed inventory、父25文件与完整候选身份、运行release五组件与Git/snapshot、62个Git树、92个blob的精确字节、全部材料路径到父Git树的逐段映射，以及固定路径规则下应采材料/跳过项；valid=true。20项静态解释的每一引用又按原文与SHA-256逐字核验，未导入采集器当独立裁判。

- release：f9ab0c4cbfa15e5030081adf379d4257128700a1；raw /home/yiwei/.codex/outputs/forge-cpp-library-task-materials-v1。
- inventory：8e5ea8a16cd13f0a9b7c43d82dab89a33d9d2bf9ce9a14c45281bccec3972929（274文件/2101588bytes）。
- 独立审计/合同解释/发布收据：/home/yiwei/.codex/outputs/forge-replication-session-2026-10-22。
- 版本化分析：benchmarks/analyses/cpp-build-cpp-library-task-materials-v1-results.json。
- PR620已合154d34e4/619关闭；PR622已合1be4653e/621关闭，均最终HEAD三CI成功及实际发布审计valid。
- 本材料结果最终HEAD三CI后只合科研依赖分支，不进main。RQ3原固定分母/P2/主线/用户HTML保持，知识库只MCP且不注入实验Agent。
