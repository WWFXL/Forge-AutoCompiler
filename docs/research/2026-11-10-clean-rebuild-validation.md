# 成功重建标准与三个遗留项目的针对性验证

本轮是共同工程修复与真实构建验证，不是 H0/R1 效果比较。用户已批准下一阶段前两项：采用成功重建标准，对 wasm3、libhv、ggmorse 做少量端到端验证后结束共同修复。跟踪 Issue #719；0 Provider、0 Token、0 新增模型费用。论文 v0.10、E53 原结果及失败保持，不启动 R2。

## 新标准

新 attempt 显式记录 `comparison_policy=successful-rebuild-v1`，区分成功重建和逐字节可复现。

| 观察 | 是否影响新运行通过 |
| --- | --- |
| 同一固定源码归档/commit、镜像 ID 与成功步骤配方；空环境构建、验证命令成功 | 必须 |
| 相同交付相对路径集合，非空、有效且类型一致的产物 | 必须 |
| 可执行物以相同命令和工作目录复验、退出 0 | 必须 |
| 实际构建及重放清理成功，源码/测试保护通过 | 必须 |
| 跨重放文件大小、SHA-256、smoke 输出内容或哈希相同 | 仅诊断 |
| 已接受原交付物在 finalize 前大小和 SHA-256 保持 | 必须，防止交付物被修改 |

所有预期值、实际值、相等性仍保存在 `ReplayArtifactComparison`。`diagnostic_differences` 保存大小/哈希/输出差异；`mismatches` 只保存阻止重建通过的问题。路径缺失、多余文件、类型错误、空文件、命令失败和超时不会因为新标准而通过。原源码归档、配方快照与镜像身份的完整性检查保持。

旧身份下的严格字节标准、原始终态和 E53 的均 11/18 交付不重标、不补跑；新旧标准不直接合并统计。字段 `reproducible_delivery_completed` 在新 attempt 下表示按声明标准成功重建，不是字节相同或完整功能等价证明。

## 固定材料与实际运行

三项目均复用 E53 的源码归档及共同 H0 初始方案，构建命令未改；只把公开任务镜像统一绑定到已部署的国内 HTTPS APT 镜像 `sha256:8123220a201ac4d00cda0dc985b9db7227cd909bb93ca6c25fd82cafce5cd887`，同步参考任务哈希。原冻结 manifest/方案原件不改。构建 2 并行、单命令 180 秒、实际重放 600 秒；规划与恢复均不调用模型。

wasm3 按作者 `platforms/app/main.c:1047–1077,1254–1256` 登记 `/artifacts/wasm3 --version`，要求退出 0 及 `Wasm3` 标识。该版本输出包含 `__DATE__` 和 `__TIME__`。libhv、ggmorse 的独立主组件是库，轻量运行记为不适用；不把默认 GUI 示例或完整作者测试变成额外任务目标。

首次独立身份 `cpp-build-clean-rebuild-validation-2026-11-10-v1` 的三条路径实际终结。wasm3、libhv 完成；ggmorse 的 APT 依赖安装 93.55 秒、子模块下载 75.15 秒均退出 0，配置也退出 0，但 README 文件身份变化触发源码保护，未执行主构建或重放。没有自动模型重试。

ggmorse 的 `CMakeLists.txt:2,13–14` 明确以 `configure_file(... @ONLY)` 从 `README-tmpl.md` 生成 README。模板只有 `@PROJECT_VERSION@` 一个变量，独立代入 `0.1.0` 后与原 README 字节相同，SHA-256 为 `7e14382529803a3fc2968d53aab2e99b06da923f5179195b6846bfd9d9e1f48b`。这是文档文件身份重写，不是原源码或测试内容变化。

因此保留 v1 失败，并建立仅含 ggmorse 的独立工程 v2，使用 #715 已有机制登记精确生成文档、原模板、内容哈希和原权限；构建命令、主要组件、源码/测试及镜像不变。没有重跑已通过的 wasm3/libhv，不把 v2 替换成 v1 首次成功。

| 新运行路径 | 主构建/交付 | 轻量运行 | 实际干净重建 | 跨重建差异 | 总耗时 |
| --- | --- | --- | --- | --- | ---: |
| v1 wasm3 | 通过 | 原生 --version 通过 | 通过，28.62秒 | wasm3 SHA-256、含编译时间的版本输出不同；libm3.a相同 | 58.97秒 |
| v1 libhv | 通过 | 库，不适用 | 通过，51.58秒 | libhv.a、libhv.so SHA-256不同 | 104.00秒 |
| v2 ggmorse | 通过 | 库，不适用 | 通过，133.45秒 | 本次libggmorse.so大小和SHA-256相同 | 326.23秒 |

三条最终路径合计489.20秒；连同v1 ggmorse保留失败共四次、662.97秒，不是首次3/3。v2 ggmorse依赖安装93.31秒、子模块准备77.39秒、配置1.03秒、编译16.65秒；这些原命令均退出0。新环境的依赖问题已在此次真实完整路径中解除，但这不是与旧环境的受控网络加速比较。

四次编译容器、三次重建容器均已删除，14项名称/ID实查不存在。保护输入检查通过的三条最终路径中，ggmorse的README内容与原文件相同但文件身份重写，按独立声明例外报告；不把README身份保持冒称通过。所有构建/恢复模型请求为0；完整作者测试未要求，记`not_required`。

## 证据位置

- [派生汇总](../../benchmarks/analyses/clean-rebuild-validation-2026-11-10/summary.json)：三项目、四次实际运行、费用/时间、诊断差异与原始Session指针/哈希，不修改任何原结果。
- [v1材料](../../benchmarks/fixtures/clean-rebuild-validation-v1/cases.json)和[v2仅ggmorse材料](../../benchmarks/fixtures/clean-rebuild-validation-v2/cases.json)：固定源码/镜像/方案、作者入口和生成文档声明。
- 服务器原件：`/home/yiwei/.codex/outputs/forge-clean-rebuild-validation-20261110-v1/`及同名`v2/`；每份保留`scope.json`、`source-snapshot/`、`summary.json`、各项目`result.json`、`.compile-sessions/.../session.json`、命令日志及实际`replay/`。
- 会话收据：`/home/yiwei/.codex/outputs/forge-clean-rebuild-session-20261110-v1/`，含cleanup逐项检查和派生汇总哈希。运行基线为`e033a7a0e9a632ec68d1356747fc7869f61cd81f`加scope冻结源码SHA；全部执行源码与最终发布文件逐项相同，后续只补报告与状态。

## 验证与边界

运行时/重放相关 168 项及轻量验证、取消、Harness 导入边界 25 项通过，修改文件 Ruff 与格式检查通过。检查包括允许哈希/大小/输出差异，以及继续拒绝空产物、集合/类型不符、运行失败和原交付物接受后变更。这些检查只支持机制实现，不增加模型效果分母。

本轮只能说明这些固定材料在已声明环境中的工程行为，不能估计成功率提升、R1 收益或任意仓库的兼容率；未要求的完整作者测试不记通过。后续若继续 Harness 研究，仍先审核新提案，再授权比较、审核结果，用户同意后才写论文。
