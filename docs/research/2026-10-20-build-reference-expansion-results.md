# 十项完整参考任务资格：七项合格，三项保留未合格

跟踪#493，独立身份`cpp-build-reference-expansion-v1`；人工参考、零Provider、零模型费用。固定10槽全部执行，各一次，无修订/重试/替换，10项cleanup均成功，无对应残留容器。7项通过预定任务资格；Forge completed为8项，其中libzip额外原始文件合同不通过，不将其混入7项合格集。

| 项目 | 固定完整功能验证 | Forge终态 | 本阶段资格与原因 |
| --- | --- | --- | --- |
| uncrustify | 全14项CTest | completed，replay passed | 合格 |
| libpng | 全37项CTest通过 | failed，未replay | 未合格：参考stage写`build/libpng16.a`，源码当前生成`libpng18.a`；不是编译或测试失败 |
| libzip | 全199项CTest通过 | completed，replay passed | 未合格：默认文档生成改写110个原有man/*.html，违反额外原始普通文件不变义务；不把它说成Forge交付失败 |
| libsndfile | 全143项CTest；固定外部codec/MPEG功能开关 | completed，replay passed | 合格 |
| libtommath | 完整./test，OK/NOP/FAIL=50/0/0 | completed，replay passed | 合格 |
| libtomcrypt | 完整./test，passed30/failed0/nop1，固定GMP后端 | completed，replay passed | 合格；上游NOP如实保留，不改成全算法均执行 |
| libsodium | 完整make check，TOTAL105/PASS105 | completed，replay passed | 合格 |
| libverto | 完整make check，TOTAL6/PASS6，三个后端开发依赖已装 | completed，replay passed | 合格；不据此声称每种后端均有独立覆盖率 |
| check | 完整make check，顶层与递归套件成功（汇总1/1及9/9），保留timeout tests | completed，replay passed | 合格，不把套件汇总当全部内部assert数量 |
| libffi | 依赖安装后bootstrap失败，尚未configure/build/check | failed，未replay | 未合格：autoreconf报告未定义LT_SYS_SYMBOL_USCORE，停止；不能判断目标不可修或测试能力 |

libpng/libffi的raw Workflow状态为`budget_exhausted`，因为冻结协议max_handoffs=0，首次失败没有交接名额便如此封口。它们剩余墙钟仍分别约1709/1714秒，不是耗尽1800秒构建时间。停止原因以上述真实命令/日志为准，不以状态名误判成“项目过难/模型预算不足”。未改变原始状态或事后补跑。

## 身份、执行与审计

运行release：`21614b36c94fc29dd6dabb6576592a7965ad5e3c`。
Manifest：`benchmarks/manifests/cpp-build-reference-expansion-v1.json`，SHA-256：
`d2e7ec92561a1f693bf4093c718ade807706f9f39b78d4f064c9579f6e4eaefc`。
对应预注册冻结CPU2、方案1800s、命令600s、replay900s、32命令/0交接；运行期间全部components未变。

原始：`/home/yiwei/.codex/outputs/forge-reference-expansion-v1/`。
47,586普通文件/70链接/565,838,840 bytes；inventory canonical SHA-256：
`34614ceaf61f45f383ea46bfacf4490e0e888417ea40c150b5bdee04b99ae011`。
全部原始观察、失败、工作区、配方、完整测试与replay日志及组件source-snapshot已封存；不为资格失败移除文件。

独立只读审计：`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/reference-expansion-v1-audit.json`，valid=true。审计重新枚举全部普通文件/链接、核对inventory与组件快照、逐项原始源码普通文件、Session/replay和资源。9项原始文件未变，libzip的110项变化与原记录一致；10项cleanup均成功、对应compile/replay容器0残留。额外合同未过不等于封存完整性失败。

实现相关12项回归、运行release默认产品1892 passed/44 skipped、Ruff/format与输入预检通过；随后#496独立来源代码的默认产品1895 passed/44 skipped。当前结果/入口仅文档更新，不重跑或修改已封存数据。

## 支持与不支持的结论

支持7个固定参考任务在该镜像/主机/完整功能范围下的严格可复现执行，并为三系统比较提供任务和oracle。它们使用人工参考方案，不支持模型成功率、状态适应、成本节省或OSS总体推断。多个仓库已有开发/metadata暴露，不宣称全历史或训练未见。

这三项未合格分别是配方路径、生成文档与bootstrap条件问题，不构成同一机制的负结果，也不说明验收阈值应降低。libpng/libzip已有工作区完整测试通过，libzip还有严格交付成功；libffi后续构建能力仍未知。本批永久封口；如未来修正参考配方或文档生成方式，必须新身份、不替换本批槽位。本轮选定比较项目不依赖这三项，优先验证研究问题，不为凑全成功返工。

下一步：按已提交协议执行#498七槽状态/验证控制，再执行#500两项新Make完整参考。#502已在新模型outcome前固定六仓库：uncrustify/libhydrogen/libsodium/libsndfile/buffer/libverto；其中四项已通过本批，两项Make待资格，不替换失败项。uncrustify原始完整测试203.7s、replay264.0s，说明旧canary单命令180s不适用；新比较双方共同采用更长时限，完整测试与验收不降低，并在父阶段全部封存后才修改共享组件与冻结manifest。

本阶段费用0；共享新增已知估算仍$1.31364420，另旧live未知预留$1，当前无未结束付费阶段。#470共享$20与北京时间2026-10-20 07:00总截止不变。
