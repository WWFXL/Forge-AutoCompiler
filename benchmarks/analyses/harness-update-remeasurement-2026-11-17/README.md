# E59：共同修复后18项目Harness重新测量

[完整报告](../../../docs/research/2026-11-17-harness-remeasurement-results.md)。原18项目×两组共36槽；原项目重新评价，不增加独立项目样本。结果待用户审核，未写论文。

- `analysis.json`：封存分析的逐字复制，含全18分母和规划/恢复开销。
- `slots.csv`、`project-table.md`：逐槽和全18对照。
- `verification.json`：201响应独立计费、无未知用量、36cleanup和138容器引用核对。
- `source-review.json`：所有原输入变化与归档的完整diff及后审。
- `tool-error-replay.json`：libass真实工具错误消息在观察器中的零Provider复现。
- `derive.py`：只读原件并生成上述派生文件，需本项目Python环境与Docker。不调用Provider。

原件：`/home/yiwei/.codex/outputs/forge-harness-update-repaired-comparison-flash-2026-11-17-v1`。
inventory：`88527cf899deda76a5bdf886c47eab7bc52f90659a54caf5c32cc407fe60b832`。

LH_v0_common/LH_v1完成17/18、16/18；请求95/106，费用0.5317215/0.5208339美元，累计1696.91/1625.56秒。新组少费2.05%、少时4.21%，同时少完成一个且有两个早期失败，不能解释成同等质量的效率提升。旧E58证据与论文保持。
