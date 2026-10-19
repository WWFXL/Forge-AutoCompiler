# 扩展来源目录：12个固定候选及完整测试入口

跟踪 #492，身份 `cpp-build-source-expansion-v1`。12/12精确来源成功保存，独立内容/归档/commit/inventory审计valid=true。**仅来源可用，不是构建成功。** 本阶段0Provider、0构建、0Docker，不执行下载项目中的指令，也没有按结果替换候选。

## 来源审阅与后续任务

| 固定候选 | commit前12位 | 构建与完整测试入口 | 来源层决定及约束 |
| --- | --- | --- | --- |
| uncrustify/uncrustify | 365d4611c7d5 | CMake、BUILD_TESTING、tests子目录、全量CTest | 可设计参考任务；README.md:64–95，CMakeLists.txt:609起。不得只测--version。 |
| pnggroup/libpng | 18ea3e9404a0 | CMake、PNG_TESTS及PNG_SHARED、全量CTest | 可设计参考任务；CMakeLists.txt:527起表明只有tests和shared同时启用才注册测试。只构建静态库再空CTest不能通过任务。 |
| nih-at/libzip | f3ff798f3d90 | CMake、BUILD_REGRESS、Python nihtest、全量CTest | 可设计参考任务，先固定nihtest依赖；INSTALL.md:38–40及regress/CMakeLists.txt:90–97。不允许以缺少nihtest关闭regression。 |
| erikd/libsndfile | b9103bd48b6c | CMake、静态库、BUILD_TESTING、全量CTest | 可设计参考任务；README.md:129–138、CMakeLists.txt:71–75/929起。共享库会关闭测试；外部codec特性必须在任务里明确，不让各臂自行缩小范围。 |
| libtom/libtommath | ae40a87a9200 | GNU Make生成test，然后显式./test | 可设计参考任务，但已在轨迹/Agent continuation历史中暴露；README.md:46–51、makefile:91–98。make test不是测试执行。 |
| libtom/libtomcrypt | 6c6d5104de66 | GNU Make生成test，然后显式./test及完整自测 | 可设计参考任务，但typed-action历史已有实际资格记录。README.md:135–139、makefile:77–81、tests/test.c:519–520；固定数学后端，不关闭算法自测。 |
| ariya/FastLZ | b1342dabcf52 | tests/Makefile:4–10执行roundtrip | 暂缓：根无Makefile，tests/test_roundtrip.c:375依赖compression-corpus子模块；.gitmodules给出URL，但当前归档不包含子模块。后续必须固定额外源码，不能跳过语料。 |
| sisong/HDiffPatch | 3b9dca715ca4 | Makefile默认all含unit_test的编译 | 暂缓：Makefile:96起依赖多个相邻源码目录，unit_test目标只编译；需固定全部依赖和完整测试执行合同，不关闭默认压缩/校验特性来凑资格。 |
| jedisct1/libsodium | 60b751cd1441 | Autotools、test/default/Makefile.am完整TESTS、make check | 可设计参考任务；此前source catalog仅有metadata URL暴露，当前检索范围不足以宣布全历史未运行。 |
| latchset/libverto | 8e944f22dcce | Autotools、tests/Makefile.am:16–18六个TESTS、make check | 可设计参考任务；configure.ac支持glib/libev/libevent模块，需保证至少有效后端并明确模块范围。 |
| libcheck/check | 35d9cc011faa | Autotools、checkmk与tests的完整make check | 可设计参考任务，但hybrid-workflow历史已实际开发暴露。README.md:45–48和两个Makefile.am；不得关闭timeout tests以规避失败。 |
| libffi/libffi | bc5538673672 | Autotools、DejaGNU、完整make check | 可设计参考任务，必须装DejaGNU并核验真实非零执行数和失败摘要，不能只凭make退出码。README.md:193–196；source pool存在metadata URL。 |

以上为源码审阅后的条件性可执行性判断，尚未运行构建或核验Linux交付闭合。10个候选可继续设计参考任务，2个因外部源码/测试边界暂缓；不把它们替换为其他项目，也不把暂缓算自然构建失败。

## 历史暴露核验范围

固定检索两个已知提交5512ff60与915a6d67的benchmarks、docs/research，按owner/name不区分大小写匹配。libsodium命中旧source catalog；libffi命中source pool；libtommath命中轨迹与Agent continuation；libtomcrypt命中typed-action资格；check命中hybrid-workflow资格。其余七个无URL命中。**无命中不证明全Git历史、模型训练或所有外部任务未见。** 未来开发/评估角色须单独预先冻结；本次参考审阅不提供模型outcome，仍不能直接称最终holdout。

## 证据与验证

原始目录 `/home/yiwei/.codex/outputs/forge-build-source-expansion-v1/`：各项目保存GitHub head原始响应、完整commit、精确tar.gz、全成员索引/普通文件哈希、链接文本及构建/测试文档带行号摘录。截断摘录不替代归档，本文重要判断另从tar只读核验对应完整文件。先冻结全部12个head后才依次下载；无自动重试，无来源执行。

78普通文件/15,914,049 bytes，inventory canonical SHA-256：
`49214164eab150f68fe950975cc81e8b36f143534545068ce2751c4137f39c62`。
独立审计 `/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/source-expansion-v1-audit.json`，同时核对原始head、精确归档和索引中的每个普通文件内容。9项归档边界/失败保留回归通过，Ruff通过。最初系统Python3.10因UTC别名导入失败、尚未创建evidence；启动日志保留，实际采集使用仓库Python3.12，未改已冻结runner。

下一步是独立零Provider参考资格：固定任务、完整功能oracle、精确交付、环境和停止条件，逐项目保留失败，不在真实canary运行中并行重型构建。这项基础设施工作解决“可公平比较且测试真实执行”的样本前提，不计为方法效果或论文创新点已经成立。
