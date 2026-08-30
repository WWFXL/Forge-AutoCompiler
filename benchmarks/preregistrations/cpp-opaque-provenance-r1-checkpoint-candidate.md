# Opaque build provenance R1 独立 checkpoint 候选

本候选承接 Issue #192 的 replication 决策和 Issue #194 的 R0 拒绝原因可观测性门禁。当前只冻结一个新的独立 checkpoint 设计，不创建 checkpoint，不调用 provider，不启动 Docker，也不写实验 evidence。

## 独立 case

- 仓库：`https://github.com/ibireme/yyjson`。
- Exact commit：`9365ddc7061033df656578bf86040048b5b5531a`。
- 构建系统、目录与目标：CMake、`/workspace/repo/build`、`yyjson`。
- 构建输出与 staged artifact：`build/libyyjson.a`、`libyyjson.a`，类型为 `static_library`。
- 依赖：`build-essential`、`cmake`。
- 来源：已审阅且 result-blind 的 `cpp-formal-v1-cases.json`，文件 SHA-256 为 `55fc4ea1cc634376b5016fa3421736a66c284b293b9b8f10185e837e12db3fee`。

该 case 的 repository、commit、target 与 staged artifact 均不同于 #190 的 `cppitertools` exploratory pair。#184 和 #190 不进入本 R1 的分析池，本候选也不是 retry、replacement、backfill 或 schedule extension。

## 冻结机制

未来双臂必须从同一个 message、environment 与 budget checkpoint 派生，顺序固定为 `baseline -> treatment`，唯一 treatment exposure 是 `forge-opaque-provenance-repair-packet-1.0.0`。Packet 继续只提供 fault/build-system/build-directory/target/proof status 和抽象 repair goal，不提供完整 shell 命令、argv 或 credential。

双臂共享 runtime-parity policy：inspection、repair build、artifact stage、submit 上限分别为 4/2/2/2，budget claim 原子化，`parallel_tool_calls=False`。Repair build 只允许冻结目录与 target；clone、configure、dependency、housekeeping、manual replay 和 compound build+stage 继续 fail closed。成功终态必须同时通过 candidate verification、clean replay 与 cleanup。

R0 `agent.tool_rejection_observed` 是未来 R1 classified rejection 的必需 companion evidence。它必须通过 `failure_id` 关联历史七字段 `agent.tool_failed`，原子记录 rejection classification、action kind、model request ID、tool ordinal 与 command SHA-256；原始命令、错误文本、模型正文、工具参数和 credential 不得持久化。未知或重复 tool-call ID 只保留旧失败事件。

## 当前授权边界

Checkpoint 与 evidence 状态固定为 `not_created`。Issue #196 只开放 `validate`、`plan` 和纯快照 `preflight`；checkpoint creation、reachability、provider call、formal attempt、pair collection、credential read、model creation、Docker execution 和 evidence write 均机械关闭，model token 上限为 0。

未来如需真实 R1，必须另建独立 execution amendment，预先冻结 checkpoint identity、provider opportunity、token ceiling 和停止规则。单 pair 仍只提供 intervention delivery 与 P2 conversion 的描述性机制证据，不估计 treatment effect、不计算 p 值、不排名模型。
