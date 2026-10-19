# 独立Make来源目录 v1

跟踪#496，独立身份 `cpp-build-make-source-catalog-v1`。用于补充三系统任务来源，不替换#492里的失败/暂缓候选。固定顺序：kokke/tiny-AES-c、libcrc/libcrc、h2o/picohttpparser、jedisct1/libhydrogen、clibs/buffer、clibs/commander。

先冻结全部完整当前head，再逐项一次下载精确commit归档。复用#492只读采集：不解包、不执行、不构建，0Provider/0Docker；保留部分下载和单项目失败，继续其余，不自动重试、不替换。压缩64MiB/展开256MiB/每文件16MiB/40000成员；拒绝越界、跨项目根链接、特殊文件、重复成员和Git元数据。只读源码索引/行号摘录与原始归档一并封存，外部独立审计。

历史URL检索限定21614b36与915a6d67中的benchmarks/docs/research；命中区分metadata与实际开发，未命中不证明全历史或训练未见。来源收集不等于任务资格、构建成功、自然失败或最终holdout。测试入口必须核验真执行，不把make test名称自动当通过oracle。

截止UTC2026-10-19 22:45（北京时间06:45），服从#470总任务07:00截止。与#493参考任务并行时只做网络/只读资料采集，不运行重型构建，不改其冻结组件；不发生模型费用。后续参考资格或模型评估另建身份并冻结功能范围与共同终点。
