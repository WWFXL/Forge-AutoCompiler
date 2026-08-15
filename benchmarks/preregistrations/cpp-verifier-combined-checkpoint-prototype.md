# Verifier-driven repair 三层 combined checkpoint 非模型原型预注册

## 研究问题

消息、环境和预算三个独立 feasibility gate 已分别进入主干。本门禁只回答：能否在 actionable submit 后、下一 continuation 前，以一次 neutral capture 原子绑定三层状态，并从同一父 checkpoint 派生身份同步、可写状态隔离且可冷恢复的 baseline/treatment。

## 冻结范围

- 跟踪 Issue：#141。
- 只新增组合 manifest、组合编排原型和聚焦测试；三个既有原型及其固定 hash 保持不变。
- 使用 SQLite message checkpointer、deterministic environment manifest/overlay 与 fake budget clock/counters。
- Provider、Docker、formal physical attempt、model token：实际调用或消耗均为 0。
- 不修改生产 Compiler、Compile Session、`_ACTIVE_EXPERIMENTS`、Oracle、clean replay、自然任务 ITT runner 或冻结 evidence。
- 不授权 provider canary、mechanism slots、随机顺序、样本量或 token ceiling。

## 原子 capture 契约

1. message graph 先执行一次 fake actionable submit，并暂停在 `continue_model` 前。
2. 对冻结的完整 message state 计算 canonical SHA-256。
3. environment 与 budget capture callback 按固定顺序执行，二者接收同一个 `capture_id` 和 message state SHA-256。
4. environment `run_id`、budget `checkpoint_id` 必须等于组合 `capture_id`；environment arm identities 必须与组合 arm plan 相同。
5. 只有三个组件全部通过各自校验后，才发布 `forge-combined-checkpoint-1.0.0` manifest；失败路径不发布父 manifest 或 arm。

## 组合 manifest

- 固定 capture point 为 `after-actionable-submit-before-continuation`，父状态必须为 neutral。
- message 组件固定 fixture identity/hash、neutral thread 和 canonical state hash。
- environment 组件固定 run identity、manifest hash 与 continuation image ID。
- budget 组件固定 checkpoint identity 与 manifest hash。
- arm plan 同时固定 baseline/treatment 的 message thread、session 与 environment identity。
- manifest 使用 canonical JSON SHA-256；运行时另保留 committed digest，拒绝重算 hash 后替换 arm plan。

## 派生与恢复规则

- 派生前和恢复前重新验证组合 manifest、三个组件 hash、neutral message next node 与 arm identity。
- 每臂使用独立 message thread/session、environment overlay 和 budget runtime。
- canonical initial combined state 屏蔽允许的 arm identity 与 feedback 差异后必须相同。
- 任一臂环境写入、预算 claim 或恢复不得改变另一臂和只读父 manifest。
- SQLite 关闭重开后从父 manifest 派生两臂，不重新 capture message/environment/budget。
- fake continuation 前分别 claim 一个 graph step 和 compiler model turn；这只是预算计数，不构成 provider 请求或 token 消耗。

## 通过条件

- capture callback 顺序、共同 identity 与共同 message hash 被测试固定。
- environment/budget 任一 callback 失败时不发布组合父状态或 arm。
- baseline/treatment 初始 canonical combined state 相同，三层身份同步派生。
- 冷恢复不重复 capture 前 submit；两臂 fake continuation 各执行一次且不能二次恢复。
- environment overlay、预算 claim 和 message continuation 跨臂隔离，父 manifest 字节不变。
- 组合 manifest、message fixture、environment manifest 或 budget manifest 在恢复前漂移时，先拒绝再消费预算。
- provider calls、Docker calls、formal physical attempts 与 model tokens 均为 0。
- 聚焦 pytest、消息/环境/预算原型相邻非 Docker 回归与 Ruff check/format 通过。

## 失效条件

- 三个组件只是独立调用，没有共同 capture identity/message state hash 或原子发布边界。
- callback 失败后仍能派生 arm，或 arm identity 只修改消息层而未同步环境/预算层。
- 任一臂写入或 claim 污染另一臂或父状态。
- 组件漂移后仍执行 fake continuation或消费 continuation budget。
- 发生真实 provider、Docker、formal attempt 或 model token 消耗。

## 解释边界

通过只证明三层实验原型可在一个确定性组合契约中原子绑定、派生和冷恢复；不证明真实 Compile Session/container 生命周期、provider client、网络连接或历史 actionable failure 可以端到端续跑，也不产生 verifier repair 因果效果。通过并合并后，下一阶段才评审真实生命周期接线，任何模型实验仍需独立预注册和授权。
