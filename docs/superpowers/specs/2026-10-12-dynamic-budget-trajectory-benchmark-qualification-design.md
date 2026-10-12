# 动态预算多步轨迹 benchmark 资格设计

> 日期：2026-10-12
> Tracking Issue：[#423](https://github.com/WWFXL/Forge-AutoCompiler/issues/423)
> 工作类型：零 Provider 数据资格与基础设施验证

## 1. 研究问题

Forge 能否在 CMake、Make、Autotools 的全新项目族上构造可恢复、可重复且预算守恒的多步构建轨迹，使后续动态预算研究具备以下最小前提：

1. 每个状态绑定同一个 source、image、workspace、artifacts、message 和 budget checkpoint；
2. 同一个 checkpoint 的两次 clean continuation 得到一致的结构化结果；
3. direct action 完成后重新观察状态，再决定下一动作；
4. 每个动作记录前、增量和后的六维预算；
5. 项目 block 的共享预算能够接收 `stop` 释放的 reservation，并被后续项目消费。

本阶段不训练、不实现也不评价动态预算 controller。通过只表示轨迹 benchmark 的执行与计量基础合格。

## 2. 实验单位和项目

实验单位是一个 `state checkpoint -> bound direct action -> successor observation`。每个 checkpoint 派生两个隔离的真实 Docker continuation。两次 continuation 均从只读快照解包，不共享可写 workspace 或 artifacts。

固定 9 个项目族，三种构建系统各 3 个；它们未出现在 Jev 正式 comparison v6 的 12 个 evaluation 项目族中。每项目固定 3 个连续状态，共 27 个状态、54 个 continuation：

- CMake：`gabime/spdlog`、`CLIUtils/CLI11`、`jarro2783/cxxopts`；
- Make：`libtom/libtommath`、`kokke/tiny-AES-c`、`antirez/kilo`；
- Autotools：`rsyslog/libestr`、`rsyslog/libfastjson`、`enki/libev`。

所有仓库、exact commit、动作角色、命令和声明产物均写入 manifest。运行开始后不允许 replacement、backfill 或命令修改。

## 3. 状态与 checkpoint

每个状态记录：

- source identity：repository URL、exact commit 和 canonical source hash；
- 完整 Docker image ID；
- workspace 与 artifacts 的只读 tar 快照及 SHA-256；
- 上一步结构化 observation 的 canonical message SHA-256；
- 动作前共享预算快照及 canonical SHA-256；
- 上述字段合成的 checkpoint SHA-256。

continuation 结果比较退出码、结构化 successor、workspace content tree hash、artifacts content tree hash 和声明产物 hash。stdout 仅作为诊断证据哈希和有界预览，不作为重复一致性的必要条件，避免工具进度文本造成伪差异。

两次 continuation 一致且成功后，仅 replica 1 的 successor 文件系统成为下一状态；replica 2 永久保持独立。动作失败或不一致时立即停止 identity，不自动拼接 Agent。

## 4. 六维预算与共享预算

预算向量为：

`wall_clock_milliseconds / provider_requests / input_tokens / output_tokens / provider_cost_microusd / build_executions`。

Provider 四项在本阶段必须始终为 0。每个状态的资格动作包含两个物理 continuation，因此 `build_executions` 增量固定为 2；wall clock 增量为两次容器内动作的实测毫秒之和。每条记录必须满足 `before + delta = after`，block 最终用量不得超过固定上限。

每个构建系统构成一个共享 block：总上限为 900 秒和 18 次 build executions。前两个项目各预留 6 次执行；第三个项目初始为 0，另有一个冻结的 `stopped-reservation` 预留 6 次执行和 300 秒。在第三个项目开始前执行一次纯账本 `stop`，把该 reservation 原子转移给第三个项目。第三个项目的 6 次 continuation 必须从释放后的 allocation 中扣除。

该转移只验证预算语义和守恒，不评价停止策略是否有效，也不把未运行的 reservation 计为失败任务。

## 5. 资格门槛

以下门槛必须全部通过：

| 门槛 | 阈值 |
| --- | --- |
| 项目覆盖 | 3 个系统各 3 个唯一项目族，且不与 Jev v6 evaluation 重叠 |
| 多步覆盖 | 9/9 项目各 3 个连续状态，共 27 个 |
| checkpoint 绑定 | 27/27 状态六类身份和组合 SHA-256 完整 |
| clean continuation | 54/54 continuation 分类终结，全部 exit 0 |
| 重复一致性 | 27/27 状态的两个 successor 结构与 content hash 一致 |
| 预算守恒 | 27/27 `before + delta = after`，3/3 block 不超限 |
| stop 转移 | 3/3 block 的 6 次执行 reservation 原子转移并被第三项目消费 |
| direct 后观察 | 27/27 action 后形成新的权威 observation，没有 composite Agent action |
| cleanup | 0 个本 identity 受管容器残留 |

全部通过，决定为 `proceed_to_agent_continuation_qualification_design`。任一门槛失败，决定为 `stop_before_agent_continuation_and_controller_implementation`。

## 6. 解释与权限边界

本 identity 可以创建一次零 Provider evidence。它允许 Git source fetch、Docker continuation、报告生成和只读审计；禁止读取 credential、调用 Jev/Agent/其他 Provider、创建模型 attempt、导入历史 outcome 或修改冻结 evidence。

通过不说明动态预算 controller 提高成功率、降低成本或优于固定 Flow；也不说明这些确定性成功路径代表自然构建失败。失败只定位 benchmark 的恢复、确定性或计量缺口。
