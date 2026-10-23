# 新C++库任务资格、策略比较与恢复基线

Issue #625。本轮为真实数据采集、结果分析及必要的任务接口修复。用户确认8小时/新增模型费用累计20美元，UTC2026-10-23 01:27:52–09:27:52（北京时间09:27:52–17:27:52），准备计入，无自动重试、补槽或旧身份续跑。主要问题是：通用工具候选＋Workflow＋失败Agent在新增C++来源上的成本与适用条件，以及失败后恢复是否值得进一步做独立配对消融。

## 已得到的结果

新增rang、ELFIO及bit7z三个完整来源/依赖输入已固定，三者最终都获得各自任务与环境下的独立参考资格。真实三策略批次产生12个尝试：11工程strict，但按文字完整范围仅10完成、1漏示例、1因HTTP402未进入方法执行。这个差别完整保留，不把原11布尔改写为10，也不把它们混作同一成功率。

工具规划与强工具Agent各自4/4实际满足完整范围，工具的统一保守估费低26.72%，总槽耗时高54.90%；两任务/两重复的有限描述支持成本与时间取舍。模型策略中一个槽关闭示例，另一个槽受Provider阻断，因此本批没有完成公平的完整三方比较，也不能据总费用给模型策略排名。rang单独两次重复三方均符合完整任务，工具/模型均12请求、强工具23请求；模型在这个任务上比工具初始失败后恢复更便宜。工具候选不是所有任务上都优于模型初始规划。

付费批次最后一次请求返回HTTP402且没有完整usage，按预先停止规则停止全部新增付费，后续恢复配对十槽和修正比较均未调用模型。已知估费$1.55561604、未知请求1按$0.80预留，保守占用$2.35561604；这不是Provider账单，不能推定402免费。剩余预算不等于服务已经可用，也不解除未知用量停止条款。零模型参考、基线和分析继续开展。

## 来源与任务资格

沿上一阶段固定20项目录中的rank8/16/18及原commit收集完整源码，不刷新HEAD或替换候选。上游rang/ELFIO/bit7z分别21/261/242原文件；归档固定依赖后分别285/508/2211原及依赖文件，原字节和链接不变，依赖统一放`.forge-deps/`。这些是固定依赖源码资源任务，不能称毫无辅助的开放网络构建。

| 任务 | 原作者编译/测试端点与精确交付 | 独立参考终态 |
| --- | --- | --- |
| rang | header-only的三个原程序all_rang_tests/colorTest/envTermMissing，默认6case全部通过、21断言；15为源码静态SUBCASE声明数，不冒充独立运行计数；原CTest及另外两输出程序执行，交付三个程序 | 首次完整参考/clean replay/cleanup通过 |
| ELFIO | header-only，全部十个默认示例编译、原ELFIOTest的73有效测试/74CTest注册全量执行，精确交付ELFIOTest | 旧裁判误计失败保留；新独立注释计数修正资格完整通过 |
| bit7z | 原默认功能/7-Zip26.01/文件系统测试开启，三个原程序全部默认测试，精确交付libbit7z64.a | root旧测试失败保留；镜像原普通用户上下文的新独立完整参考通过 |

ELFIO原四个测试源文件在去掉单行注释后有82个TEST宏，其中9个在ELFIOTest1.cpp212–457行的块注释内；剥除后为73，与实际运行一致。旧参考所有有效测试已通过，但硬编码82/83导致拒绝。`cpp-build-library-elfio-qualification-v1`只修正73/74计数和输出标记，其余来源、依赖、构建、全部测试、精确交付与重放不变。旧失败不续跑、不回填；不是为方法成功率降低裁判。

bit7z原root参考首个程序572case中571通过、1失败（13断言），原测试在用户目录测试`..`，日志中的基准目录为`/`。镜像已有ubuntu(uid1000、原`/home/ubuntu`)，新`cpp-build-library-bit7z-user-reference-v1`保持root构建，仅以正常普通用户执行原三个程序，同时记录真实UID与用户目录，未覆盖HOME、未修改任何源码或测试字节。三个程序原构建及clean replay均完整通过：572/342/342case、161621/155344/155344断言。权限、平台、隐藏测试仍按作者原条件执行，不将未执行分支记通过；不把跨环境资格修正称方法效果。原root后两程序/交付/replay未观察，不记失败。新普通用户资格不补入原root参考分母或本轮12槽。

所有资格均要求原及依赖文件保持、精确真实编译产物、同不可变镜像干净重放及实际容器不存在。原三个资格候选分母、20项目录和旧30项分母保留；不同独立身份分别报告。三者均指定CMake，不增加跨构建系统覆盖；rang/ELFIO是原作者编译端点，不称完整公共头文件安装包。主机源码已有开发暴露，非holdout。

## 真实三策略数据与范围缺陷

`cpp-build-library-strategy-comparison-v1`固定rang/ELFIO×三策略×两次新鲜重复，先全第一轮再第二轮，DeepSeek Pro thinking low与上一批同资源/相同完整费用计量。工具沿原task-selected通用模板，不按新项目补配置规则。两Workflow共用装配和只读恢复；强工具保留自己的执行工具能力，因此是完整策略比较，不能称所有harness能力完全相同或纯规划单因素。

下表为全部尝试的资源流水，模型行含范围缺陷和服务停止，不能直接作公平三方排名。

| 策略 | 完整范围完成/原4槽 | 范围未满足 | 方法执行未观察 | 模型请求 | 已知保守估费 | 总槽分钟 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 工具规划Workflow＋失败Agent | 4/4 | 0 | 0 | 18 | $0.52818876 | 10.74 |
| 模型规划Workflow＋失败Agent | 2/4 | 1 | 1 | 16已知＋1未知 | $0.30659904，未知另预留$0.80 | 4.93 |
| 强工具Agent | 4/4 | 0 | 0 | 43 | $0.72082824 | 6.93 |

四个工具槽都在实际失败后交接并完成，全部18次请求/$0.52818876属于恢复，不存在本批工具零模型完成。rang初始configure缺doctest，Agent补依赖准备并重新配置；ELFIO通用BUILD_TESTING开关不等于作者ELFIO_BUILD_TESTS，build能成功但无完整原测试，固定检查拒绝后Agent修订。四槽都是观察到的恢复轨迹，没有本批相同新鲜无恢复对照，不能据此声称恢复因果增益或最小后缀重执行的独立收益。

模型有完整usage的初始规划为三个episode，共16请求/$0.30659904，平均每episode约$0.10219968；第四个episode首请求HTTP402无usage，不按零成本规划纳入这个均值。rang两重复工具/模型/强工具分别12/12/23请求、$0.30800880/$0.21993840/$0.37654320，均满足完整范围。请求数相同不代表费用相同：输入、输出及恢复材料量不同。这个单任务结果支持保留模型初始规划参照，而不是继续假定模型规划没有收益。

ELFIO模型slot5显式关闭默认示例，原工程oracle仍通过，因为文字协议“全部默认示例”没有进入共同任务明确义务及可执行检查。独立审计原及replay配置/十个文件后将其记为协议范围未满足；作者73测试本身通过，不称作者测试失败。slot12HTTP402未进入规划/构建，不解释为模型不会构建。原工程strict=11和原raw完全不改，不换成较弱端点来制造完整成功。

`cpp-build-library-strategy-comparison-v2`已准备12槽新候选：共同显式完整编译义务、补原examples/CMakeLists材料，并在原全部测试后检查ELFIO_BUILD_EXAMPLES=ON及十个示例ELF文件。通用工具模板、依赖、模型、资源、源码、原测试、精确交付与replay不变；新增检查已对封存参考原构建/重放产物实际通过，也拒绝了旧slot5反例。两个局部回归覆盖关闭示例与缺一个程序，不重复免费参考全构建。该候选尚未执行、未绑定新增付费许可；先恢复Provider及解除停止状态，才能启动，不能把候选当结果。

## 固定分母分层验证（RQ3）

旧RQ3的14/43及18/6分母和结果均不改。本批新12槽独立列报，不与旧批混合估计：最新build、固定作者测试oracle、暂存和clean replay均11通过/0失败/1未观察；原源码与实际cleanup各12通过；文字完整范围则10完成/1未满足/1未观察。工程strict的11/1不是完整协议范围计数。过程中的失败与恢复另保留，终态通过不抹去过程失败。

这里的漏示例是我们任务接口与裁判覆盖缺陷，不是新发现作者功能bug，也不是自然误接受率或验证层提高方法成功率的证明。它说明“完整作者测试＋replay通过”仍须以完整任务义务为前提。该观察支持继续研究构建领域的可执行任务合同和分层验证，但不自动成为独立新通用算法或已经成立的第二创新点。

## 恢复研究与当前执行边界

`cpp-build-tool-recovery-ablation-v1`已在新方法结果前固定snappy/simdutf/yaml-cpp/libtommath/tinyxml2五个已见、工具初始可规划任务，每项失败即停/同失败Agent恢复一对，共10槽。离线初始5/5准入；check初始拒答不属于执行后恢复估计对象。受HTTP402/未知停止影响，本十槽全部未观察，不填成功或失败。

另以独立身份`cpp-build-tool-no-recovery-observation-v1`采集同固定五项的零模型首次失败即停基线；它是新的实验数据，不是重复免费产品回归，也不补入原十槽。所有模型入口预先拒绝、传model=None、不读凭据，若首次失败则后续阶段未观察，若无失败则完整测试/交付/replay/cleanup。五项全部观察并封存：simdutf/tinyxml2严格完成，snappy/yaml-cpp/libtommath首次失败即停；0模型请求/Token/费用，原及replay源码、精确产物和实际cleanup独立审计valid。总槽471.97秒，结果见`benchmarks/analyses/cpp-build-tool-no-recovery-observation-v1-results.json`。

| 固定任务 | 最新build | 首次固定检查与后续观察 |
| --- | --- | --- |
| snappy | 通过 | 必需配置HAVE_LIBLZO2未满足；作者完整CTest、交付/replay未观察 |
| simdutf | 通过 | 全部固定原测试、交付、replay和cleanup通过，0模型strict |
| yaml-cpp | 通过 | YAML_CPP_BUILD_TESTS=OFF；作者完整CTest、交付/replay未观察 |
| libtommath | 通过 | ./test未构建，执行入口缺失；不能称作者测试用例失败，交付/replay未观察 |
| tinyxml2 | 通过 | 全部固定原测试、交付、replay和cleanup通过，0模型strict |

本独立固定5槽的build为5通过，固定检查2通过/3失败，交付和replay各2通过/0失败/3未观察，源码与cleanup各5通过。三次差异定位于配置或测试准备，不能冒称三项作者功能bug。2/5说明原通用方案有适用条件，与既有恢复轨迹方向一致；没有同批新鲜恢复臂，不用跨批旧成功作配对因果估计，也不据5个已见项目估计总体构建成功率。

## 证据与复核

会话根：`/home/yiwei/.codex/outputs/forge-library-expansion-session-2026-10-23`。来源/输入/参考、完整费用/每次响应、typed inventory、组件与Git release、原文件/链接、精确产物和实际容器清理均有独立审计。版本化数值见`benchmarks/analyses/cpp-build-library-strategy-comparison-v1-results.json`；其provenance列出具体审计与分析脚本路径/SHA。原raw不可修改，分析与报告不是原事件的替代真源。

| 独立身份 | raw目录（均位于/home/yiwei/.codex/outputs） | inventory SHA-256 |
| --- | --- | --- |
| cpp-build-library-full-sources-v1 | forge-library-full-sources-v1 | 7cff54145a8d5867136e8b8a6264b0a9b655ee9c72b51db744698d0302ea79cf |
| cpp-build-library-inputs-v1 | forge-library-inputs-v1 | 456cd80553a39d1a5f2fbd2c9df505591a9072da8cdd5aa2304399ff4b55e449 |
| cpp-build-library-reference-v1 | forge-library-reference-v1 | 2f28ae859043255cd62ec3cc286627ee542361aa1d5df6ac639f1c488923874e |
| cpp-build-library-elfio-qualification-v1 | forge-library-elfio-qualification-v1 | ed7d103e7287c204ed634c60abad7ec625ca42f3e2caa95552d2b9a62347e6e3 |
| cpp-build-library-strategy-comparison-v1 | forge-library-strategy-comparison-v1 | cb30b094b747c21a124d0212c3ce013be82205bbba09cd0a155ab7a3efe7dc36 |
| cpp-build-library-bit7z-user-reference-v1 | forge-library-bit7z-user-reference-v1 | 48025086b5b2cfaddf29c2e6c982951dcfed5554e8f82f3c1908196a95e5ce0c |
| cpp-build-tool-no-recovery-observation-v1 | forge-tool-no-recovery-observation-v1 | 21be3340801fca99c2856f33ec7ef82460d9ab7151bf6cabfa3fd450fcd49626 |

资格汇总另见`benchmarks/analyses/cpp-build-library-qualification-results.json`。来源10局部检查/输入1实际归档检查及相关参考检查已随各准备阶段记录；新比较义务拒绝1项、恢复开关1项、示例遗漏回归2项及CLI/Ruff通过，未重复免费参考全构建或本地全量产品测试。实际构建均用于参考资格或真实实验数据；发布以最终HEAD CI和GitHub合并状态为准。

研究主线、P2和旧分母保持。后续工作登记[Issue #626](https://github.com/WWFXL/Forge-AutoCompiler/issues/626)。下一项需要用户决定的是Provider恢复及未知停止解除后的有效费用/时窗授权，随后优先完成已准备的完整义务比较与真正的恢复配对。没有必要为局部成本取舍否定硕士主线，也不应把本批范围缺陷包装为完整三方胜出。
