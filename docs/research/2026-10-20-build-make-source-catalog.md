# 第二批Make来源：不把目标名称当测试执行

跟踪#496，独立身份 `cpp-build-make-source-catalog-v1`。固定六候选，5项精确来源成功、1项metadata请求失败；全部槽位保留、无替换。0Provider/0构建/0Docker，仅只读来源资格，不是构建成功或自然失败样本。

| 固定候选 | 来源commit前12位 | 完整测试线索与决定 |
| --- | --- | --- |
| kokke/tiny-AES-c | 23856752fbd1 | Makefile:55–58的make test执行三种AES长度的完整测试。test.c:28–36提示未定义模式时也会exit0，因此要核对三种模式实际输出；此前typed-action等历史已有实际暴露，不称新holdout。 |
| libcrc/libcrc | 无 | 精确owner/name的GitHub metadata失败，原始响应和head失败记录保留；不静默修正为其他owner。 |
| h2o/picohttpparser | 465a7ff09fbd | Makefile:33–37的make test通过Perl prove运行test-bin，包含ASan/UBSan；.gitmodules要求picotest子模块。可继续设计，但须先固定gitlink完整SHA与额外源码，不能删掉测试框架或关闭sanitizer。 |
| jedisct1/libhydrogen | 264bf4290219 | Makefile:43–48实际执行tests/tests，make check指向完整test；tests/tests.c:475–490调用全部自测。可设计参考任务，不添加NDEBUG或选择性跳过自测；静态库是独立交付。 |
| clibs/buffer | 736ba3cc161d | Makefile:2–4生成并运行test，test.c:243–261调用全部18项测试。可设计参考任务，交付含库源码的真实测试可执行物；保留全部assert。 |
| clibs/commander | 3e79dd3cb0dd | Makefile:2–3仅生成test，test.c是CLI演示、没有断言测试集。暂缓完整oracle定义；不能只凭make test或--help宣称完整功能通过。 |

有限历史检索固定21614b36和915a6d67的benchmarks/docs/research；tiny-AES-c有21行URL命中，含旧资格。其余五项无命中，不证明全历史/模型训练未见。后续任务角色须在新模型outcome前冻结；数据准备不等于学习过选择器，也不能直接宣布最终holdout。

原始 `/home/yiwei/.codex/outputs/forge-build-make-source-catalog-v1/`，41普通文件/228,597 bytes，inventory canonical SHA-256：
`1cd3b892a03273cf289fc36b823163b0c794f1c1bf988ab460840a19050288ee`。
独立审计 `/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/make-source-catalog-v1-audit.json`，valid=true；核验每个精确head、归档、普通文件索引和冻结组件快照。运行后仅为测试补全scripts导入路径，未改运行代码或冻结证据；首次孤立pytest的导入错误日志保留，原测试显式PYTHONPATH后12/12通过，补全测试入口后默认孤立调用同样12/12通过。Ruff通过；默认产品回归1895 passed/44 skipped（CI模式，live测试关闭）。

下一步：独立资格可纳入libhydrogen、buffer和固定子模块后的picohttpparser；tiny-AES-c仅作已见开发控制。commander和来源失败项保留暂缓。任何真实构建在当前#493串行参考批结束后执行，避免并行资源干扰；所有来源判断尚不支持方法效果、成功率或成本收益。
