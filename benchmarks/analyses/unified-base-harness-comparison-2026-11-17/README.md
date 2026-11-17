# 统一基座18项目Harness完整比较

[完整报告](../../../docs/research/2026-11-17-unified-base-harness-comparison-results.md)。身份cpp-build-unified-base-harness-comparison-flash-v1，原18项目×两组共36槽。LH_v0_common/LH_v1完成18/18、15/18，费用0.5923218/0.8198265美元，请求97/132。本轮不支持更新组整体优势；libffi补依赖路径有局部收益。结果待用户审核，未修改论文。

- `analysis.json`：封存分析的复制，含全18分母及规划/恢复开销。
- `project-table.md`、`slots.csv`、`slots.json`：全18与逐槽结果。
- `verification.json`：229响应计费/身份、36cleanup和138容器引用核对。
- `source-diffs.json`：11项原输入变化完整diff；`source-review.json`另含新增兼容宏与后审。
- `derive.py`：只读原件生成派生数据，需要项目Python环境及Docker；不调用Provider。后审为独立人工解释，不由脚本覆盖。

原件：`/home/yiwei/.codex/outputs/forge-unified-base-harness-comparison-flash-2026-11-17-v1`。
inventory SHA-256：`a5e98c4039efb92d466db5cdef142477732b2c2f71ea064c214a66025378f2af`。

旧E58/E59及三项目观察保持，不拼接槽或增加独立项目样本。本轮之后先审核结果，未追加付费实验。
