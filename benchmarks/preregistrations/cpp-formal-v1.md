# Forge C/C++ 正式分层实验预注册 v1

> 状态：采集前冻结草案。该文件和对应 JSON 不授权模型调用或正式实验。

## 研究问题

在相同 Forge 工程基线、C/C++ 项目、Compile Session、独立 clean replay、预算和串行调度下，RichLab `gpt-5.5` 与 DeepSeek `deepseek-v4-flash` 两个“模型 + provider 路径”条件的端到端 oracle pass 是否存在差异？

primary estimand 是 30 个项目等权的成功率差：每个项目、每个条件执行 3 次，先得到项目内成功比例，再计算 `DeepSeek - RichLab`，最后对 30 个项目求均值。它比较的是完整部署条件，不是脱离 endpoint、网络路径和 Agent 运行时的 foundation-model 能力。

## 样本框与选择

候选总体来自 [OSS-Fuzz 接纳项目规则](https://google.github.io/oss-fuzz/getting-started/accepting-new-projects/) 和固定快照 [`08682bfc`](https://github.com/google/oss-fuzz/commit/08682bfc14e31d12fcc94b52b4805d7994fb70fd)。OSS-Fuzz 要求接纳项目具有显著用户基础或关键基础设施价值，并公开 primary language 与 main repository；本研究不使用它的 fuzz build script，只使用该元数据建立上游项目样本框。

固定快照含 1,369 个 `project.yaml`，其中 577 个声明为 C/C++、473 个指向 GitHub。按仓库去重、排除 fuzz/example/test-only 名称，并要求未归档、非 fork、许可证明确、100–200,000 KiB、exact commit 根目录存在受支持构建标记后，得到 182 个候选：

| 构建系统 | Small | Medium | Large | 合计 |
|---|---:|---:|---:|---:|
| Autotools | 18 | 27 | 12 | 57 |
| CMake | 25 | 62 | 25 | 112 |
| Make | 5 | 5 | 3 | 13 |

构建系统优先级为 `Autotools -> CMake -> Make`；规模边界为 100–5,000、5,001–50,000、50,001–200,000 KiB。每个构建系统固定抽取 3 个 small、4 个 medium、3 个 large。排序键是：

```text
sha256("issue76-v1|lowercase_owner_repo|exact_commit|build_system|size_stratum")
```

`esp-v2` 原本是 Make/medium 的第三名，但其 exact commit 根 Makefile 的主 `build` target 编译 Go 服务，不是原生 C/C++ Make case；该不兼容在任何正式模型请求前确定，因此按同层哈希顺序使用 `fio`。后续不允许静默 replacement：采集前发现新的静态不兼容必须公开 amendment 并冻结新协议；任一正式 ledger 创建后禁止 replacement/backfill。

30 个 exact commit 的完整清单、许可证、规模、分层与 selection hash 在 `cpp-formal-v1.json`。

30 个项目使每种构建系统有 10 个项目并保持 3/4/3 规模格；每条件 3 次重复用于暴露随机运行方差。该样本量是受资源约束的分层设计，不是用 v8 的 5×1 小样本事后拟合出的 power 结论。

## 条件与调度

- 两个独立条件：RichLab `gpt-5.5`、DeepSeek `deepseek-v4-flash`。
- Lead 与 Compiler 在同一条件内使用同一模型；0 provider retries、禁止 fallback 和跨条件池化。
- 每个项目、每个条件 3 次，共 `30 × 2 × 3 = 180` 个唯一 attempt。
- 分 3 个 round 严格串行。每轮项目顺序与项目内条件顺序由冻结 seed 和 SHA-256 排序确定。
- 完整 schedule 的 canonical SHA-256 为 `9cfca53bb8c7ab8f07eb5c9a852383eb1877dc377cf56bb834b8eee3587fa469`。
- ledger 创建前的 runtime、credential、网络、endpoint canary、evidence mount、Docker、Git 或 frozen-component preflight 失败时暂停，不消费、不换序。
- ledger 创建后，timeout、构建失败或其他终态都保留为观测；只有 finalize 与 orphan reconciliation 后才推进下一 slot。

## 指标与分析

primary outcome 是独立 clean replay 后的二元 `end_to_end_oracle_pass`。primary effect 是 30 个项目等权的三次成功比例差。确认性检验为项目块上的双侧 exact sign-flip permutation test：对 30 个整数成功次数差用仓库脚本中的动态规划枚举，不使用 Monte Carlo p-value。95% CI 使用以项目为 cluster 的 100,000 次 percentile bootstrap，seed 固定为 `forge-cpp-formal-v1-bootstrap`。

只有 primary condition contrast 是 confirmatory。按构建系统、规模、failure domain 的结果和 tokens、延迟、请求、命令、submit、replay、finalization、orphan 都是 secondary/descriptive，不另作未校正显著性主张。该处理遵循软件工程小样本随机区组实验应先隔离 block effect、再比较同 block treatment difference 的建议，参考 [Empirical Software Engineering 2024](https://doi.org/10.1007/s10664-024-10504-1)。

endpoint failure 在 primary 端到端 estimand 中仍是失败，同时作为 reliability outcome 单列。去掉 endpoint failure 的子集只能探索，不能用来宣称纯模型能力差异。缺失、损坏或未终结 ledger 不得丢弃或补写，而是暂停 confirmatory analysis，按 evidence-integrity incident 处理。

## 网络与隐私

每次 attempt 前只记录：

- `access_medium ∈ {wired,wifi,mobile_hotspot,unknown}`
- restricted relay 是否启用
- endpoint canary latency
- `network_present` / `endpoint_reachable`
- Compose/DooD 等 control-plane topology

禁止记录 SSID、IP、运营商账户、代理凭据、AK 和 authorization header。网络分类不能事后推断，也不能在看到 outcome 后作为排除条件。

## 资源与停止门

v8 的 10 次 attempt 共 1,306,532 tokens、5,008.122 秒和 191 次模型请求。线性外推 180 次约为：

- 23,517,576 tokens
- 90,146.196 秒，即串行约 25.041 小时
- 3,438 次模型请求

按 1.25 planning contingency 为 29,396,970 tokens、约 31.301 串行小时。这只是 5×1 calibration 的预算量级，不是成本保证或统计 power 结论。

正式采集前必须另建 Issue，并由用户明确确认预算；还必须完成 30 个项目的文档级构建路径审计、case-specific 参数和 artifact oracle、正式 manifest/Schema/runner/image/prompt/预算冻结、180-slot schedule digest 复核、双 provider canary 与实际 Compose/DooD preflight。

## 冻结与公开注册

仓库合并只冻结可审阅资产，不等于外部时间戳注册或采集授权。正式数据采集前，应将最终 JSON、本文和 schedule digest 提交到只读、带时间戳的注册系统。OSF 将 preregistration 定义为在数据收集或分析前发布的只读研究计划，并说明注册后文件不可修改；如发生偏离，应通过新 amendment 明确记录，而不是覆盖原计划。参见 [OSF Registrations & Preregistrations](https://help.osf.io/article/330-welcome-to-registrations)。
