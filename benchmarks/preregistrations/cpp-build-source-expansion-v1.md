# 扩展来源目录 v1：固定12候选，只读采集

跟踪 Issue #492，沿用 #470 跨阶段授权；身份 `cpp-build-source-expansion-v1`。本阶段为基础设施/来源资料采集，0 Provider、0 构建命令、0 Docker，不执行来源内任何指令，不将来源可用视作构建成功或自然失败资格。

manifest 内的12候选及其顺序是冻结候选 fixture：CMake 建议组 uncrustify/uncrustify、pnggroup/libpng、nih-at/libzip、erikd/libsndfile；Make 建议组 libtom/libtommath、libtom/libtomcrypt、ariya/FastLZ、sisong/HDiffPatch；Autotools 建议组 jedisct1/libsodium、latchset/libverto、libcheck/check、libffi/libffi。分组必须经源码核验，不替换仓库、不静默修正 owner。

先按顺序查询并保存全部完整当前 commit，之后按原顺序下载精确 commit 的 codeload tar.gz，每项一次、不自动重试；失败与部分下载保留。单项目 metadata 或来源失败不终止其余固定候选。每个归档先完整验证成员边界，再只读普通文件，不解包；保存原始归档、成员类型/内容哈希、构建和测试文档带行号摘录。最多64MiB压缩、256MiB展开、每文件16MiB、40000成员；拒绝绝对/父路径、跨项目根链接、特殊文件、重复成员、Git元数据。源码读取不等于执行其建议。

历史隔离仅检索 5512ff60d78dd6227169ca7186c930040a926377 与 915a6d678298ce64fefea752aa7d9e074c5e871f 的 benchmarks/docs/research 中 owner/name 字面匹配。记录原始命中；命中只表明 URL/metadata 可能暴露，不等于实际开发运行；未命中不代表全历史或模型训练未见。后续参考资格需要另行核验测试执行与交付完整性，不称本候选为最终holdout。

截止 UTC 2026-10-19 22:45（北京时间06:45），早于持续总任务07:00截止以保留清理交接。本阶段不预留或新增模型费用。不与真实 canary 并行重型构建；不修改其冻结组件。输出目录create-once，末尾类型化封存及独立审计；任何失败不可覆写为成功，结果分析写在外部/版本化报告。
