# 三系统构建方案与工具Agent配对比较 v1 结果

跟踪 #502。独立身份 `cpp-build-plan-agent-paired-comparison-v1`，UTC2026-10-19T19:08启动、20:49封存。固定六仓库、三系统、两重复、双臂的24槽全部观察，12配对双方均严格completed；独立审计valid=true，用量完整、原始源码未改、固定完整测试/精确交付/clean replay/cleanup全部通过。阶段0未知请求，保守估算共 **$2.88930180**，原$12预留已结算。

## 身份与权威证据

- 协议/代码冻结提交：`54d1d893d95d3167f704d547a8799011330d8738`；实际启动release：`557a44c4e9127a17436b2bfb6a82108737b78cb2`。后续c293dcb8仅更新状态和预算文档，59组件与manifest未改。
- Manifest：`benchmarks/manifests/cpp-build-plan-agent-paired-comparison-v1.json`，SHA-256 `5f2cc841c38b1ed8eaee5867d2491dfce060c539aa9c3c92170729bbc74f42f2`；同名preregistration。人工参考和个人知识库未提供给真实模型。
- 同协议十二臂零Provider门禁12/12 strict，见`2026-10-20-build-plan-agent-paired-comparison-gate.md`；门禁不进入本比较分母。
- 原始：`/home/yiwei/.codex/outputs/forge-plan-agent-paired-real-v1/`。143187普通文件、184链接、1193274172 bytes；inventory canonical SHA-256 `2df552e2a26dac451b4d61690c4bc3eac59fee2fd0dcc0b3604f25c84905a91d`。`protocol.json`、`result.json`、`inventory.json`、`seal.json`与59组件快照只读。
- 独立审计：本轮外部工作目录`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/paired-real-v1-audit.json`；逐项重算inventory、原归档和源码、固定测试、精确交付/replay、原始响应/请求生命周期、Token/费用和容器清理，valid=true、issues=[]。
- 冻结分析器输出`paired-real-v1-analysis.json`，完整事件轨迹汇总`paired-real-v1-trajectories.json`，均在上述外部工作目录，不写回raw。每臂原始runner的旧kind标签保留；本阶段角色和前瞻性顺序由运行前冻结的整体协议定义。

## 完整任务集描述

| 指标 | plan | tool |
| --- | ---: | ---: |
| 严格completed | 12/12 | 12/12 |
| 模型请求 | 60 | 105 |
| 记录Token | 765692 | 1082737 |
| 保守估算费用（美元） | 1.26334296 | 1.62595884 |
| 构建/测试/暂存/诊断命令 | 52 | 66 |
| 单臂总耗时之和（秒） | 2840.27 | 3195.20 |

固定任务集合计中，plan请求少42.9%、Token少29.3%、统一单价估算费用少22.3%。这些是本任务集的描述，不是OSS总体节省率或成熟Agent排名。初始规划、读取、拒绝、重复测试与验收尾部全部计入；没有剔除失败提交。费用使用输入$1.32/百万、输出$3.96/百万的公开价保守计算，非实际账单，未使用缓存折扣。

先对每仓库两重复求均值：

| 仓库 / 系统 | plan/tool请求均值 | plan费用均值 | tool费用均值 | plan/tool总耗时均值（秒） |
| --- | ---: | ---: | ---: | ---: |
| uncrustify / CMake | 5 / 8.5 | 0.09068598 | 0.12093114 | 586.28 / 677.93 |
| libhydrogen / Make | 1 / 5.5 | 0.02611422 | 0.08650356 | 38.78 / 50.14 |
| libsodium / Autotools | 8.5 / 9 | 0.20249526 | 0.17837028 | 289.12 / 325.64 |
| libsndfile / CMake | 8 / 9.5 | 0.17602926 | 0.14251644 | 238.34 / 249.63 |
| buffer / Make | 2.5 / 8 | 0.05422890 | 0.10656030 | 61.15 / 49.97 |
| libverto / Autotools | 5 / 12 | 0.08211786 | 0.17809770 | 206.47 / 244.30 |

plan在libsodium和libsndfile上费用更高，buffer总耗时也更高；不能说每个项目均受益。libsodium第二次plan为11请求/155588 Token/$0.25922952，libsndfile第二次plan为10请求/135746 Token/$0.20782608，均包含较多源码调查。uncrustify第二次plan与tool均6请求，plan反而更贵；请求数不等同费用。

## 预定关联组重采样描述

libhydrogen/libsodium按同维护者合为一组，其余四仓库各一组，共五组；两重复不作为独立项目。按预注册20000次、seed20261020，使用第500/19500顺序统计量。下表为每臂的plan减tool：

| 指标 | 六仓库均值差 | 固定关联组重采样95%分位范围 |
| --- | ---: | ---: |
| strict completed | 0 | [0, 0] |
| 美元 | -0.03021799 | [-0.065373528, +0.00359238] |
| 请求 | -3.75 | [-5.7, -2.35714] |
| Token | -26420.42 | [-46638.8, -7098.36] |
| 命令 | -1.16667 | [-2.2, -0.41667] |
| 总耗时（秒） | -29.58 | [-60.11, -4.27] |

这是固定任务/关联组下的波动描述，非OSS总体置信区间，不做显著性或非劣检验。费用范围跨过0，不能宣称跨项目稳定成本优势；strict范围[0,0]也不证明总体可靠性非劣。

## 轨迹审计与归因限制

12个plan臂全部初始revision1完成，交接/修订均0。此批未激活失败恢复，不能证明RQ2状态适应、P2或可学习选择器增量。

11/12个tool臂共发生19次严格提交拒绝：supporting_command_not_in_recipe 12次、recipe_role_not_allowed 6次、recipe_command_out_of_order 1次。唯一无提交拒绝的是libsodium第一重复。它们主要是把smoke ID当supporting build、将smoke纳入recipe或乱序；构建与固定测试已成功，随后模型自行纠正并通过原严格验收。uncrustify第一重复共有4次拒绝，不能只统计最后一次verification而少计。所有拒绝成本保留，部分轨迹还重复执行了完整测试。

全批失败Shell记录4条，均为diagnostic（libsodium两重复共3、libsndfile第二重复1）；没有构建或固定测试命令失败。不能把这些诊断退出码当作项目构建失败。全部最终交付及replay严格通过，不用提交拒绝数估计自然误接受率。

因此两路径差异同时包含方案组织、调查/调度、自动维护命令ID和由接口负担引起的额外操作。当前工具接口不是成熟Agent的代理，不能把全部差异归于初始规划。该结果支持“此固定任务集的方案路径请求/Token更少且均完成”，不支持普遍成本改善、状态恢复效果或通用机制首创。

## 下一决定与检查

采用 #504 已在相关第二重复结果出现前固定的自动配方溯源接口探针：libsndfile/buffer/libverto三系统，使用新鲜plan与自动ID工具路径各两次，共12槽；先六臂零Provider门禁，再最多$6真实预留，仍共享$20。条件为本批完整、用量与独立审计闭合、手工ID问题确认且时间允许；均满足，不按费用差异是否正向作准入。选样时点记录`auto-provenance-candidate-selection.json`，UTC20:22:49，当时所选第二重复结果均未产生。后验选择明确披露，不把跨批差值当自动编号因果效应。

原严格验收、源码与失败证据不改。冻结执行前25项相关回归、1920项默认产品回归通过；后续候选准备后当前工作树为1929 passed/44 skipped（新增9项属#504，不在本批59组件内），后端全量Ruff通过、517文件格式检查通过。发布仍须最新结果head三项实际CI成功后合并，未进main。

共享账本已把本阶段$12预留结算为$2.88930180；本轮已知保守估算累计$4.20294600，另旧live测试未知预留$1，当前占用$5.20294600。预留不等于支出。绝对截止仍为北京时间2026-10-20 07:00；新臂/请求至少留3600秒，最后15分钟仅清理/交接。
