# Confirmatory v1 recovery 决策包

## 状态与边界

本文记录 Issue #241 的只读 recovery 决策。Confirmatory v1 保持为一次因 mechanism failure 关闭的确认性尝试；其 runner、manifest、Schema 和 evidence 均不修改。本决策阶段为 0 provider、0 credential read、0 model token、0 formal evidence write。

冻结 release 为 `b2218e4bc1414e6647106944cb0f7934a70aced0`，authorized manifest canonical SHA-256 为 `68349316cfdbe8411c49c7ffc9491760bf19fb10e0583f40a47dd0c91ea31e78`。本地 evidence 目录共 28 files / 332,783 bytes；逐文件清单见 `benchmarks/fixtures/opaque-provenance-confirmatory-v1-evidence-inventory.json`，按路径排序的 inventory digest 为 `dc7e53020af27929ea334376628c37f02236ae5510166c07109a1ddde7f5f431`。

## 冻结 outcome 语义

| Pair | v1 终态 | 后续语义 |
| --- | --- | --- |
| `pupnp-rep-01` | endpoint-censored，2,267 recorded tokens | 仅作为 v1 描述性 attrition evidence；不导入新 replication primary test |
| `ada-url-rep-01` | endpoint-censored，11,644 recorded tokens | 仅作为 v1 描述性 attrition evidence；不导入新 replication primary test |
| `args-rep-01` | 双臂 graph-step limit，paired delta 0，68,288 recorded tokens | 仅作为 v1 单 replicate 轨迹；不形成 project block，不导入新 primary test |
| `gpac-rep-01` | started marker 后因 `KeyError: reference_case_id` 失败 | 0 provider、0 token、0 Compile Session；技术上是未消费 provider opportunity，但属于已关闭 v1，不续跑 |

前三个 outcome 的数据质量和不可变性不因机制故障而消失，但它们不满足六 project block 的确认性 estimand。历史 exploratory pair 同样不池化。

## 两条路线的 estimand 差异

### 透明 recovery amendment

该路线导入前三个 v1 outcome，只对剩余 schedule 采集。最终样本会同时包含旧 release/旧 runtime 与新 release/repaired runtime，并跨越两个采集时段。其 estimand 是“给定 v1 已观察前三个 outcome 后，混合执行版本下剩余 schedule 的条件性结果”，不再等同于原预注册的单一 release 确认性效应。即使 `gpac-rep-01` 没有消费 provider opportunity，这条路线仍构成 v1 停止后的 extension，并与 `replacement_forbidden`、`backfill_forbidden` 冲突。

### 独立 replication

该路线使用新 release、新 manifest identity、新 evidence directory 和同一 repaired runtime，从空目录按完整 12-pair schedule 重新采集。旧 v1 outcome 不进入新 primary test。其 estimand 是“在修复后统一 runtime 与新采集时段下，verifier-driven repair 对六个冻结 project block 的配对 provenance conversion effect”。它保留 project-level exact sign-flip test 的可解释性，也允许把 v1 作为独立的机制失败与 attrition 报告。

## 决策

选择独立 replication。理由按优先级为：

1. 避免在同一 primary estimand 中混合 release、runtime 和采集时段。
2. 遵守 v1 禁止 replacement/backfill/extension 的冻结边界。
3. 不因知道前三个 outcome 后再决定哪些 observation 复用而引入结果依赖选择。
4. 新实验仍可报告 v1 的 82,216 total recorded tokens 与机制失败成本，但不把它们计入 replication 预算或效应估计。

## Capture-before-commit 安全门禁

Issue #239 的真实 repair gate 发现：capture evidence callback 在 coordinator commit 前抛错时，底层 reconcile 可能把 preparing capture 标记为 cleaned，而 parent Compile Session 容器仍需由调用方显式清理。Issue #241 的版本化 adapter 必须在单个 pair 执行期间精确跟踪本次新建 session，并在异常时反向、幂等清理；禁止通过扫描并删除所有 Docker 资源来实现。真实零 provider 门禁必须在测试 finally 之前断言 managed orphan 为 0。

## 独立 replication 的前置条件

- 新 protocol/manifest/Schema/runner identity，不复用 v1 evidence directory 或 batch marker。
- 固定本 inventory digest、v1 batch marker 和三个 outcome 的 SHA-256，声明 `historical_outcomes_imported=false`。
- 完整保留六 case、12 pairs、项目内两次 arm order 对调和 project-level exact sign-flip 分析。
- 统一使用 repaired pair runtime；在发布前通过 CMake/Make 静态合同和真实零 provider Make cleanup gate。
- 新 reachability 与 batch token 单独计费；v1 的 82,216 tokens 仅进入跨尝试资源报告。
- provider 前先完成 release、manifest、空 evidence、Ubuntu 原生 Docker、0 orphan 和 credential-name-only preflight。

完成上述条件后才能授权新的 reachability 与 12-pair batch。
