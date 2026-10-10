# Jev 三臂端到端 canary v1 qualification 失败记录

- 阶段：`zero_provider_qualification_startup`
- 分类：`parent_manifest_constant_mismatch`
- 异常：`AttributeError`
- 决定：`supersede_with_fresh_v2_identity`

v1 runner 在读取父 semantic-routing manifest 时引用了不存在的常量
`MANIFEST_PATH`，因此在任何 Docker action、credential 读取、Provider 调用、
model token、formal attempt 或 formal evidence 写入前失败。失败后受管资源为零，
qualification 正式报告不存在。

v1 manifest、Schema 和预注册保持只读。后续 v2 使用新的 identity、manifest、
qualification/report 路径与 evidence root，只允许修正常量名为父脚本实际导出的
`DEFAULT_MANIFEST`；不续跑、不导入、不 replacement 或 backfill v1。
