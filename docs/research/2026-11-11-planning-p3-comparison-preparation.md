# 已审核P3与P0：固定R2的比较准备

2026-11-11；Issue #739。阶段为研究基础设施：解除下一次规划Harness公平比较的执行阻塞，尚无P3效果结论。用户已审核P3并要求“开始执行”；本批正式模型预算与时窗尚未确认，准备没有读取Provider凭据、没有真实请求，新增模型费0。

## 可以直接执行的比较

[协议](../../benchmarks/preregistrations/cpp-build-planning-p3-fixed-r2-comparison-flash-v1.md)、[manifest](../../benchmarks/manifests/cpp-build-planning-p3-fixed-r2-comparison-flash-v1.json)、[入口](../../scripts/forge_planning_p3_comparison.py)。身份为`cpp-build-planning-p3-fixed-r2-comparison-flash-v1`，manifest SHA为`64512a124a63213241de38f6bcaa676b8f4e0066096d090cceba39485f27227a`。

18项目×P0_R2/P3_R2、各一次共36槽，不做机械双重复。两组分别独立规划，唯一变化是已审核3902字节P3初始指导；恢复完全相同R2，规划指导不追加到恢复提示。Flash low、源码、任务、网络、资源、Workflow、独立检查相同；无经验、无配方复用。只重绑定原R2共同提示哈希，原指导及候选来源SHA保留，不改默认P0、不改论文。

| 构建系统 | 六个项目 |
|---|---|
| CMake | libarchive、json-c、libexpat、Libsoundio、Civetweb、Leveldb |
| Make | toybox、vlmcsd、tiny-AES-c、pwnat、linenoise、libbpf |
| Autotools | nettle、libgcrypt、jansson、shc、snapraid、Rnnoise |

来源为既有CompileAgent与CXXCrafter公开项目目录；源码版本先锁定、再采集与装配作者依据，三系统交错，方法先后各9次且每系统各3次。具体版本、作者引用、既有目录接触见[选择](../../benchmarks/fixtures/planning-p3-fixed-r2-comparison-v1/selection.json)及[任务](../../benchmarks/fixtures/planning-p3-fixed-r2-comparison-v1/tasks.json)。排除P3/E55来源与旧H1/H2开发评价项目；不把未用于提案等同于训练未见，不称最终holdout。主要组件来自作者普通入口，未增加复杂定制目标；辅助示例、完整测试不构成额外主任务。

## 准备中的失败与范围

首次Civetweb采集因HTTP正文中断`IncompleteRead(147456 bytes read)`失败；原件`forge-planning-p3-source-preparation-v1/Civetweb/result.json`保留。同commit独立补采为`forge-planning-p3-source-preparation-network-recovery-v1`，不是正式方法槽重试，未替换项目。

dsvpn在任务冻结前排除：作者帮助固定退出254，而当前独立原生检查只接受0至123，普通成功运行又要求VPN权限/网络。为避免本轮同时改验证器而换选同目录Make项目toybox；原源码/排除原因保留。没有依据任何P0/P3结果换样。采集18项完成不等于18项参考构建全部通过；仅按作者材料装配主目标和独立检查，未开展新一轮大规模参考资格。

源文件归档保存在`/home/yiwei/.codex/outputs/forge-planning-p3-source-preparation-v1`、`forge-planning-p3-source-preparation-network-recovery-v1`、`forge-planning-p3-toybox-source-preparation-v1`；组合索引`forge-planning-p3-assembled-sources-v1/result.json`指向各原始尝试。

## 必要验证与新增证据

7项针对性检查通过，覆盖排期/项目排除、两组独立规划且同R2、无效身份及超预算在读取凭据前拒绝、固定组件/候选保护、初始和恢复费用归因；Ruff/格式、manifest实际归档核验与Git差异检查通过。pytest退出清理提示涉及既有`/tmp/pytest-of-yiwei/garbage-*`权限，不属于本次运行目录，没有修改旧目录。

实际调用本轮executor进行两条json-c受控接线：各一份脚本初始方案→不存在的CMake target自然返回失败→同一R2脚本修订→主构建→轻量检查→交付→真实干净重建→清理。两条全通过；每条一次脚本初始、一次脚本恢复，真实Provider请求0/Token0/费用0。读取实际请求材料核验：P0不带规划附加指导；P3初始含完整审核原文；两份恢复均含相同R2且不含P3。四个容器的8个名称/ID独立inspect均不存在。

[接线摘要](../../benchmarks/analyses/planning-p3-preparation-2026-11-11/summary.json)链接原件`/home/yiwei/.codex/outputs/forge-planning-p3-wiring-probe-v1`，含脚本、原请求材料、日志、原/重建产物与两条结果；这只证明接线，不计自然规划成功或Harness效果。未重复产品全量本地测试；发布CI按仓库规则运行。

## 正式运行与后续决定

建议新增硬上限5美元、确认起4小时，共36固定槽；每槽0.40美元/1800秒，总预算和时窗优先。全部初始/失败/纠错/恢复费用计入；P3已付离线提案0.317073美元、R2提案0.139614美元单列。无自动重试、不补槽；未知用量、模型标识异常、清理失败停止整批。到限保留未启动/未观察。

授权文件绑定identity、manifest SHA、用户答复、UTC起止、maximum_cost_usd、automatic_retry=false及既有credentials_env_file；通过新授权门禁才加载既有接入。获得本批授权后直接采集，不再追加工程资格。报告完成、总费/时、初始与恢复分项、无恢复完成与代表性失败；小幅及混合收益均如实解释。结果交用户审核后才写论文。

发布收据：准备提交`546f090a`，PR #740三项CI通过，合并`c151dbaca300a742cb96f2be9910ffd64f7aaea8`，Issue #739关闭。知识库固定入口及本轮准备笔记已同步；不改变manifest、正式0/36与未绑定新预算时窗的边界。
