# E42 派生结果

正式身份：`cpp-build-simple-system-comparison-flash-v1`，48计划槽全部终结。本目录消费同一批原件，不新增分母。

- `analysis.json`：全分母、方法汇总、逐槽和规划/恢复费用。
- `slots.csv`：48行，保留主构建/作者测试/交付/replay、全部费用和耗时；空值表示未观察。
- `by-project.json`、`paired.json`：按六项目与两重复比较，重复不是独立项目。
- `response-verification.json`：392个保存响应的Token/费用与原槽账本逐项对应。
- `read-patterns.json`：同一Agent任务中相同工具参数的重复读取；事后描述，不能推断每次读取均无用。
- `system-comparison.svg/pdf/png`：全分母图，失败早停会影响耗时；CXX完整数受测试适配限制。
- `evidence.json`：授权范围、运行release、seal和原始路径。

原件及授权/分析驱动器见服务器`forge-simple-system-comparison-flash-v1`及`forge-simple-comparison-session-v1`，不得覆盖原件。本次分析生成命令：后者`derive.py`、`read_patterns.py`、`plot.py`；既有运行脚本的`--analyze <raw>`提供基础汇总。方法、失败分类和论文用途以[结果报告](../../../docs/research/2026-11-04-simple-system-comparison-results.md)为准。
