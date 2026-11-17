# 修复后三项目真实自主观察

- 身份：`cpp-build-failed-project-harness-observation-flash-v1`，三个已知失败项目，各一次更新LH_v1。
- [报告](../../../docs/research/2026-11-17-failed-project-observation-results.md)：3/3主构建、交付与干净重建通过，30响应、0.2490891美元、累计618.35秒；不回填E59或自动入论文。
- `analysis.json`保留原分析副本；`slots.json`列出三项结果、错误反馈与格式拒绝；`verification.json`逐响应计费、清理及inventory核对；`source-review.json`独立保存原输入差异与后审。
- 原件：`/home/yiwei/.codex/outputs/forge-failed-project-observation-flash-2026-11-17-v1`，inventory `1b819422e993f9963cb5ad707d6905e65c6e48c51ebfe62d4a2b332ab344aa8f`。
- 复算：从仓库根目录执行`PYTHONPATH=backend/packages/harness:scripts backend/.venv/bin/python benchmarks/analyses/failed-project-observation-2026-11-17/derive.py`；仅写本派生目录，需原件及Docker可用。

本轮没有工具参数错误或方案结构拒绝，不能单独估计错误处理修复效果。libtasn1之前是基线失败、LH_v1已成功，本次不是三组配对对照，也不增加未见项目数。完整作者测试不属于本协议目标。
