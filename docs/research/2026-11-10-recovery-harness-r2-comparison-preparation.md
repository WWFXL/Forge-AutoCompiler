# 已审核 R2 的新项目恢复比较准备

用户已回复“审核通过”，接受结合当前系统实现得到的 `R2_system_context` 候选。候选原文、来源和提示差异仍见[复分析报告](2026-11-10-recovery-harness-system-context-proposal.md)，SHA 为 `270becfd8fe2c0c89d0d7ab8c820893cdc6ae7cdd9d2c50e95ecb11f84263743`。这次批准不等于候选已有效或允许直接入文。

本阶段属于**基础设施与比较准备**：消除新项目、共享方案与恢复方法装配的执行阻塞，不产生模型效果。正式比较仍为0/36；新增模型费用0，不读真实凭据、不请求Provider。H0仍默认、论文v0.10不改。

## 公平比较安排

[固定协议](../../benchmarks/preregistrations/cpp-build-recovery-harness-r2-comparison-flash-v1.md)与[manifest](../../benchmarks/manifests/cpp-build-recovery-harness-r2-comparison-flash-v1.json)绑定新身份 `cpp-build-recovery-harness-r2-comparison-flash-v1`，manifest文件SHA `7392fcb8b92cd8b2f8a5e5044bbbc6464545cba804708844793d787f975e81d3`。

| 项目 | 两组共同设置 | 唯一处理差异 |
| --- | --- | --- |
| 初始方案 | 每项目一次H0规划，完整方案/SHA在两个干净会话共享 | 无 |
| 模型和权限 | deepseek-flash thinking low；三只读工具，返回方案，Workflow执行 | 无 |
| 自然失败恢复 | 相同交接、上下文、预算、纠正与清理机制 | H0共同提示／共同提示加已审核R2指导 |
| 任务与判定 | 简洁主构建；当前共同修复、国内HTTPS源、2 CPU、successful-rebuild-v1 | 无 |
| 排期 | 18新项目×两方法，每项目每法一次；三系统交错、方法交替先行 | 无 |

18次共同规划任务不等于18次模型请求：工具读取、结构纠正可能需要多次请求，全部计费。共同规划只实际支付一次；解释独立部署成本时，两方法均计完整初始规划。另列新提案0.139614美元和此前提案0.106807美元，不混入本轮新增支出，也不声称完整历史生命周期成本已核清。

## 为什么使用这些项目

延续用户希望覆盖不同项目的要求，从已有三论文来源池选择新的开发评价集，不重复E53的18项目，也不重复优化器的来源项目。固定版本、论文来源、作者引用和独立主目标见[任务目录](../../benchmarks/fixtures/recovery-harness-r2-comparison-v1/)。当前版本的任务/manifest URL检索未命中既有实验，来源池本身的名称出现不能误当实际运行；本集不称最终holdout或随机代表总体。

| 构建系统 | 项目（各一次） |
| --- | --- |
| CMake | mozjpeg、rtl_433、stderred、Libfacedetection、zlog、Lwan |
| Make | libtree、masscan、wrk、libbcrypt、sxhkd、uhubctl |
| Autotools | libpcap、tmux、flex、goaccess、file、xz |

候选元数据检查先于任何新模型结果。libui当前固定版本仅支持Meson，明确排除并保留；uhubctl改归Make、zlog使用作者支持的CMake、stderred使用根Make包装的src/CMake入口。源码18/18采集完成，不以参考构建或模型成绩筛选。较新的项目依赖/工具版本未保证可用，遇实际失败仍保留，不换样本。

公开任务只给固定源码、构建系统、环境和统一的普通主目标。独立主要组件、参考命令、轻量输出断言与产物路径不送模型。辅助demo/benchmark不充当主要目标；不要求完整作者测试。Lwan/wrk作者版本/用法分支原生退出1，事前使用独立Python断言同时检查该退出及实际版本输出，不接受其他失败或空输出；这只是轻量启动检查，不称业务功能正确。

## 必要验证及保留失败

沿用 `forge_recovery_harness_comparison.execute/paid_callbacks`，新增小入口只装配新任务、候选及本轮分析。公共Workflow、提示、工具和模型未修改；不另建执行器。新分析不复用旧R1标签、旧18/6硬编码或旧提案费用，并保存规划失败时两恢复处理未观察。

相关19项零Provider检查、修改文件Ruff及格式通过。使用真实付费回调的装配路径但把模型替换为明确脚本、不加载凭据：libtree共同规划给出受控不存在目标，两组各收到同方案，真实交接后返回作者正常方案。脚本回复中Flash标识仅用于走真实meter路径，不能当Provider服务或模型身份验证。

- **v1两条保留**：两组均恢复并完成主构建和暂存；原独立参考误以为 `libtree --version` 输出含名称，实际仅`3.2.0-dev`，因此轻量断言拒绝，重建未启动，cleanup成功。不能称重建失败或Harness未能构建。
- **v2两条通过**：依据固定源码的显式`--help`分支改用`Usage: libtree`断言，两组均完成受控恢复、主构建、轻量检查和实际干净重建，cleanup成功。同一初始方案哈希，两次自然失败的说法不成立：失败是人工注入，恢复回复为脚本。
- 原`definitions.json/tasks.json`及v1原件保持；本次正式候选只绑定独立`definitions-v2.json/tasks-v2.json`，不是回填旧运行。4编译＋2重建容器的12项名称/ID实查不存在。

[准备汇总](../../benchmarks/analyses/recovery-r2-preparation-2026-11-10/summary.json)保存逐条分层、时间、原件哈希及清理结果。原件为服务器 `forge-recovery-r2-runtime-check-20261110-v1/v2`；源码为 `forge-recovery-r2-sources-20261110-v1`；会话 `forge-recovery-r2-preparation-20261110-v1`保存元数据、检索范围、实际回调脚本和日志。未额外做18项目完整参考构建或本地产品全测；仅这些接口与路径验证，不能证明一般兼容率或R2成功率收益。

## 当前停止点

旧1美元授权只覆盖已完成提案，不能转为新36槽比较授权。建议新批最多5美元、确认起4小时，无自动重试、不补槽，未知用量/模型标识异常/清理失败停止整批。先完成本准备与发布，再由用户确认本批费用和窗口；不重新审核同一候选。

获授权后直接采集36槽，不再重复准备检查。先报告主构建/交付/实际重建分层、全费用时间、恢复暴露和逐项目原因，再由用户审核结果并决定是否采用及写论文。即使有正负混合取舍也完整报告，不用事后改裁判换取方法成功；不将本批与E53跨版本差值归因R2。
