# 后续项目的源码与测试入口资格目录

Issue #477。身份 `forge-build-source-catalog-v1`，固定六候选先于首次来源请求；禁止原身份替换项目。全阶段0构建、0模型请求，仅公开源码与原始构建/测试文件审查。此阶段提供后续公平比较的任务来源，不能当构建成功率或方法效果。

| 候选 / 指定入口 | 原文观察 | 资格决定 |
| --- | --- | --- |
| richgel999/miniz / CMake | 根CMake `BUILD_TESTS` 注册一个 `catch_tests`；Catch源码已包含，无submodule | 可进入构建资格；固定开启测试，必须发现并实际执行非空CTest集合 |
| mity/md4c / CMake | 根CMake不注册CTest；`scripts/run-tests.py` 执行调用、所有文本suite及病理输入测试 | 可进入构建资格，但须使用原Python入口、保留其上游允许失败规则，不能拿空CTest冒充测试 |
| madler/pigz / Make | `Makefile:80-97` 的 `test` 执行压缩完整性和字节数断言；zlib为依赖 | 可进入构建资格；保留上游条件compress分支和Shell语义，不称完整`tests`目标 |
| HardySimpson/zlog / Make | 根`test`只进入`test/`执行make；该Makefile只编译程序；CMake另有筛选的执行集合 | 暂缓，先为Make定义明确且有依据的执行oracle，不能静默换CMake或把编译当执行 |
| troglobit/libite / Autotools | `autogen.sh`执行autoreconf；m4已包含；`test/Makefile.am`列21项TESTS | 可进入构建资格，固定全部21项，权限敏感测试应按环境事实解释 |
| libmaxmind/libmaxminddb / Autotools | 原固定owner/name请求404 | 来源不可用；可能是文书错误，不是构建或方法失败，纠正仓库须另立来源身份 |

每项exact commit与原始归档哈希见 `benchmarks/manifests/cpp-build-source-catalog-v1.json`。五个已取源码的tree未截断且无gitlink，原始归档保留。未执行源码内任何指令；其中指示仅作为数据阅读。

历史隔离检查只覆盖仓库 `6a49ee26` 和 `915a6d67` 两个已知前序提交的 `benchmarks/`、`docs/research/` 中六个owner/name URL，未命中。不能据此声称全部历史未见、模型训练未见或最终holdout资格已成立。后续正式设计仍需项目族/开发暴露记录审计；一旦构建或查看模型结果，这些项目即成为开发暴露。

原始目录 `/home/yiwei/.codex/outputs/forge-build-source-catalog-v1/`：500 files / 5,800,000 bytes，inventory canonical SHA-256 `4f97f8b1f0963eec12d1e5df41464d46a0090458ea6bc80fa89e8ae5044c4705`，独立只读inventory审计通过。原始source/result/scope/review不再追加。

下一步以独立零Provider身份对有明确oracle的项目做固定顺序资格，先核验源码归档、测试真实执行、产物和干净重建。资格失败不能按结果挑替代项目，新的来源或任务修订另存身份。当前四项“可进入资格”都还没有构建结果。
