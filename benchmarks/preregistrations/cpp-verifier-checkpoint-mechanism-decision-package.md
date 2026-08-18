# Verifier-driven repair failure checkpoint 机制实验决策包

> 状态：设计冻结候选，`collection_authorized=false`，`provider_canary_authorized=false`。跟踪 Issue：#145。

## 决策摘要

首轮采用**分阶段 provider 方案**：先用一个 primary provider 完成受控 failure checkpoint 的机制 canary 和 6 个配对 checkpoint pilot；只有首轮完整、证据闭合且另行授权后，才用第二个 provider 做 3 个配对 checkpoint 的可移植性复制。natural failure 作为独立 stratum，只接收其他已授权运行自然产生的 eligible checkpoint，不为凑样本重复运行或回填。

本阶段只冻结设计，不调用 provider、不创建 physical attempt、不启动 Docker，也不读取任何密钥。下一工程门禁应先用确定性模型验证受控 fault injection，之后才能请求 provider canary 授权。

## 研究问题与 estimand

### Primary estimand

在同一个 eligible pre-replay actionable failure checkpoint 内，baseline 与 treatment 获得相同的消息、容器 rootfs、bind-mount 状态、预算、模型和工具，仅反馈 payload 不同。主要 estimand 是：

> 结构化 verifier repair packet 相对当前 baseline verifier payload 对 post-exposure candidate repair conversion 的配对条件效应。

分析单位是一个完整 checkpoint pair，不是单个 arm、单次模型请求或项目。primary outcome 为：arm 在 continuation 上限内至少一次后续 submit 通过 candidate verification，并且原 actionable classification 不再出现。

### Secondary outcomes

- 前 2 次 post-checkpoint provider request 内是否再次 submit。
- clean replay 是否通过、Oracle 是否通过、terminal delivery 是否通过。
- 后续 submit 次数、failure transition、provider requests、recorded tokens 和 continuation wall-clock。
- timeout、cleanup、hash/identity drift 和 pair completeness。

自然任务 ITT、candidate conversion、clean replay 和 terminal success 必须分别报告。到达 checkpoint 之前的 parent cost 与 checkpoint 之后的 continuation cost 分栏显示，不能隐藏或重复计入。

## Stratum 与解释边界

| Stratum | 来源 | 首轮计划 | 可回答的问题 | 禁止外推 |
| --- | --- | --- | --- | --- |
| controlled | 确定性构建准备后注入预注册的 artifact staging fault，再由真实 verifier 产生 failure | primary provider 6 pairs | packet 在固定 fault class 上是否改变 repair conversion | 不能外推为真实仓库总体收益或自然 failure 发生率 |
| natural | 其他已授权 C/C++ ITT 运行自然产生的 eligible actionable failure | 当前不设最低数、不主动采集 | packet 对真实 failure checkpoint 的条件效应 | 不能与 controlled pair 池化，也不能替代自然任务 ITT |

两个 stratum 分开编号、分开分母、分开报告。provider 也作为独立复制层，不把不同 provider 的 pair 池化后排名模型。

## Checkpoint 入组与排除

### 共同入组条件

1. failure classification 属于冻结 repair-packet Schema 的 actionable 集合。
2. `replay_attempts == 0`，failure 发生在 clean replay 前。
3. submit、failure、Session、ledger head、message checkpoint、environment manifest 和 budget manifest identity/hash 全部闭合。
4. capture 位于中性 ToolMessage 已持久化、下一次 provider request 尚未开始的位置。
5. 父容器与四类 bind snapshot 成功冻结；两臂从同一 continuation image 和只读 archive 派生。
6. capture 时剩余资源至少能为每个 arm 分配完整的 8 requests、8 turns、24 graph steps、600 秒 work 和 120 秒 cleanup 上限。
7. 敏感信息扫描通过，checkpoint 中不包含密钥值、Authorization header、完整模型正文、宿主私密路径或未白名单 stdout/stderr。

### 共同排除条件

- provider/endpoint、daemon、preflight、cleanup、finalization 或 budget failure，而不是 actionable verifier failure。
- 已开始 clean replay，或 failure 依赖 replay container identity。
- parent 已 finalized、存在迟到写入、capture 未 committed、hash 漂移、两臂可写目录共享或容器名截断碰撞。
- 剩余预算不足、实际模型身份不可核验、工具/prompt/模型配置在两臂间漂移。
- 同一个 parent checkpoint 的重复派生；历史 Slot 7/10 fixture 不能伪装成可续跑 checkpoint。

### Controlled fault v1

首轮只使用一个可解释 fault family：已按冻结 recipe 生成有效目标 artifact，workspace 中保留可恢复的真实构建输出，但首次 submit 前确定性地让 `/artifacts` 缺少 required artifact；随后调用真实 verifier 产生 pre-replay `candidate_verification_failed`。fault injection 必须先写入独立的白名单 evidence 事件，不能改写 verifier、Oracle、ledger 历史或 repair packet。

pilot 使用 Autotools、CMake、Make 各 1 个冻结 case，每个 case 2 个 checkpoint，共 6 pairs。实现该 fault 前必须先通过 0-provider 非模型 gate，证明 injection 可重复、两臂同源、移除 injection 后真实 candidate 可通过，并且 cleanup 后无 orphan。

## Arms 与唯一允许差异

| 项目 | Baseline | Treatment |
| --- | --- | --- |
| 最后一个 feedback ToolMessage | 当前中性 verifier failure payload | 同一 payload 加入 schema-valid `repair_packet` |
| model/provider/system prompt/tool schema | 相同 | 相同 |
| capture 前消息和 next node | 相同 | 相同 |
| continuation image 与只读 snapshot | 相同来源 | 相同来源 |
| requests/turns/steps/token/time budget | 相同 | 相同 |

arm/thread/session/container/workspace identity 必须不同，这是隔离所需的管理差异，不属于 treatment。除上述 identity 与最后一个 ToolMessage content 外，canonical initial state 必须逐字段相同。

两臂串行运行，不并发。6 个 pair 以两个 checkpoint 为一个 block；每个 block 固定一对 baseline-first 和一对 treatment-first，块内排列由 `SHA-256(protocol_id + "|" + block_index)` 的最低位决定。schedule 在第一个 arm 启动前写入授权 manifest，运行后不得调整。

## Provider 方案比较

| 方案 | 优点 | 主要问题 | 决策 |
| --- | --- | --- | --- |
| 单 provider | 成本低、减少模型异质性、最适合先验证机制 | 不能说明跨 provider 可移植性 | 用于 primary pilot |
| 双 provider 同时展开 | 可同时观察可移植性 | 成本约翻倍，网络与模型差异会放大解释难度 | 不采用 |
| 分阶段 provider | 先回答机制，再以独立复制检查方向一致性 | 总周期更长，需要两次授权 | 推荐 |

primary 候选为 DeepSeek `deepseek-v4-flash`，secondary 候选为 RichLab `gpt-5.5`。这是网络路径和成本管理的执行顺序，不是模型能力排名：冻结 pilot 的 provider canary 延迟分别约 0.724 秒和 3.851 秒，但单次 canary 和单个 project block 都不足以排名模型。每一阶段仍必须重新核验 endpoint、配置模型、actual model、timeout 和 retry；任一缺失都停止。

## Continuation 预算

冻结 pilot 的两个 actionable checkpoint 提供的只读锚点如下：

| Evidence | capture 前成本 | checkpoint 后完整轨迹 | 前 2 请求窗口 |
| --- | ---: | ---: | ---: |
| Slot 7 / openthread / DeepSeek baseline | 20 completed requests，160,123 tokens | 16 started、14 completed、2 timeout、130,264 tokens | 7.283 秒再次 submit，26,028 tokens，仍失败 |
| Slot 10 / mupdf / RichLab treatment | 15 started、14 completed、1 timeout、62,896 tokens | 1 completed request、6,083 tokens、10.800 秒，无再次 submit | 同完整轨迹 |

这两个样本只用于给出保守上限，不能估计 provider 或 treatment 效应。整槽平均 59.7k tokens 不能代表 checkpoint continuation；Slot 7 的前 8 次后续请求为 7 completed、1 timeout、57,575 tokens、339.429 秒。

每个 arm 冻结为：

- provider requests：最多 8；model turns：最多 8；graph steps：最多 24。
- request timeout：300 秒；provider retry：0；fallback：禁止。
- work wall-clock：600 秒；cleanup reserve：120 秒；total：720 秒。
- expected recorded tokens：60,000；maximum recorded-token ceiling：120,000。
- primary 的快速响应 landmark 为前 2 次请求，但不会在第 2 次请求后自动终止；完整 primary outcome 继续观察到任一 arm ceiling。

| 阶段 | 组成 | Expected tokens | Maximum tokens |
| --- | --- | ---: | ---: |
| Primary provider reachability canary | 1 request，不进入分析 | 5,000 | 5,000 |
| Primary mechanism canary | 1 controlled pair，不进入 pilot 分母 | 120,000 | 240,000 |
| Primary controlled pilot | 6 controlled pairs | 720,000 | 1,440,000 |
| Primary 阶段合计 | canary + pilot | 845,000 | 1,685,000 |
| Secondary 复制阶段 | 1 request + 1 canary pair + 3 pilot pairs | 485,000 | 965,000 |
| 两阶段合计 | 仍需分别授权 | 1,330,000 | 2,650,000 |

在每个 pair 前检查剩余 batch ceiling；不足以容纳一个完整 worst-case pair 时不启动。arm 在每次请求前检查 request/turn/step/time/token 余量，达到任一上限后禁止新请求，但 finalize/cleanup 仍必须执行。natural stratum 的 parent acquisition cost 由产生它的 ITT 协议承担，同时在机制报告中引用，不计入上述 controlled continuation ceiling。

## Canary、删失与停止规则

### 最小 canary

1. 先对当阶段唯一 provider 发送 1 个最小认证请求，记录 endpoint、configured/actual model、timeout、retry、非空响应 hash、延迟和网络接入类型；不保存响应正文。
2. 通过后运行 1 个 controlled checkpoint pair，按冻结顺序完成两臂，验证 packet fidelity、模型身份、预算、candidate conversion 记录和 0 orphan。
3. 两步均不进入 pilot 分母。primary canary 通过不自动授权 6-pair pilot；secondary canary 也必须在 secondary 阶段单独授权。

### 网络删失

- 300 秒 timeout、0 retry 保持不变；同一 arm、pair 或 provider 不自动 fallback。
- primary outcome 产生前发生 endpoint timeout，arm 标记 `network_censored`，整个 pair 不进入 primary per-protocol 分母；同时在保守敏感性分析中按未转化报告。
- primary outcome 已产生后再发生 timeout，保留 primary outcome，但 clean replay/terminal secondary outcome 标记删失。
- 一个 arm 已开始后，禁止 replacement、backfill 或用另一 provider 补齐。未启动任何 arm 且 capture 完整性 gate 失败的候选不算入组，可由下一个预先 eligible checkpoint 占用未使用序号。

### 立即停止

- provider reachability 或 mechanism canary 任一步失败。
- duplicate submit、hash/identity drift、arm 污染、secret 泄漏、actual model 不可核验、cleanup 后存在 paused/orphan 资源。
- 两个连续 pair 被网络删失，或 primary pilot 累计 2 个 pair 在 primary outcome 前被网络删失。
- batch/arm ceiling 到达，或剩余 ceiling 不足以开始完整 pair。

停止后保留已有 append-only evidence，不 retry、不删除失败记录。只有新的中文 amendment、原因复核和实验负责人授权才能 replacement。

## 分析计划

6-pair primary pilot 只报告 `both converted`、`baseline only`、`treatment only`、`neither converted`、删失和成本，不计算 p-value，不声明总体效果。若后续正式阶段积累足量完整 pair，二元配对 primary outcome 使用 exact McNemar；样本量根据 pilot 的 discordant-pair 比例重新预注册，而不是用 6 个 pilot pair 推断显著性。

secondary provider 的 3 pairs 只检查方向和接线可移植性，不与 primary 合并，也不做模型排名。natural stratum 单独报告，并保留其 ITT 来源、parent acquisition cost 和 selection mechanism。

## 进入下一阶段的门禁

1. 本决策包合并后，另开中文 Issue，只实现 controlled fault v1 的 0-provider 非模型 gate 和授权 manifest 候选。
2. 非模型 gate 通过后，实验负责人需要分别确认 primary provider canary 的 1 个请求、1 个 checkpoint pair 和 245,000 maximum tokens。
3. mechanism canary 通过后，再确认 primary 6-pair pilot 的 1,440,000 maximum tokens；不得把 canary 通过解释为自动授权。
4. secondary provider、natural checkpoint collection 和 clean-replay mismatch 均是后续独立阶段。

## 方法依据

- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)：thread-scoped checkpoint、恢复与 time travel；跨进程恢复需要持久 saver。
- [statsmodels McNemar](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html)：配对二元 discordance 的 exact 检验实现。
- [Chaos Mesh](https://chaos-mesh.org/docs/)：受控 fault injection 作为独立实验编排的成熟模式；本研究据此将 controlled 与 natural stratum 分开。

## 当前授权边界

- `collection_authorized=false`
- `provider_canary_authorized=false`
- provider calls：0
- formal physical attempts：0
- model tokens：0
- AK 读取与输出：禁止
- Docker：本阶段不使用；后续只允许 WSL2 Ubuntu 原生 `docker.service`
