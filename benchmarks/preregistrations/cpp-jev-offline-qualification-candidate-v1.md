# Jev 离线资格实验 candidate v1 预注册

## 身份与状态

- Candidate identity：`cpp-jev-offline-qualification-candidate-v1`
- Tracking Issue：[#393](https://github.com/WWFXL/Forge-AutoCompiler/issues/393)
- 上游零 Provider 资格结果：`cpp-typed-semantic-routing-pilot-v2`
- 当前状态：`candidate_zero_provider`
- 工作类型：实验基础设施。本 candidate 不产生 Jev 模型效果证据。

本文件冻结首次读取 credential 之前的研究问题、数据边界、API 合同、请求预算、停止规则和候选判据。真实 Provider 执行必须另建 authorized amendment，绑定本 candidate 的 exact Git revision、明确的 credential 读取授权、create-once evidence 路径和剩余预算。

## 研究问题

Issue #391 已在 CMake、Make、Autotools 的 6 个项目族上构造 18 个相同 coarse phase facts、不同失败根因的状态。冻结 RuleGate 只选择最低成本 `build`，top-1 和 route-acceptable coverage 都是 `6/18`；项目族 LOPO TF-IDF/逻辑回归是 `17/18`。因此本实验回答：

1. 固定版本 Jev 能否根据语义失败日志，在 `dependency`、`configure`、`build`、`escalate_agent` 中选择安全的下一动作？
2. Jev 的完整 Choice 概率经独立 calibration 项目族校准后，能否得到有用的直接执行覆盖率，同时保持零观察错误直接动作？
3. Jev 的准确率、顺序稳定性、延迟和费用是否足以支持后续 controller 资格，而不是仅复现简单文本分类器？

Jev 不负责确定可由代码读取的阶段事实，不生成 Shell 命令，也不能跳过真实构建、functional oracle、provenance、CandidateVerifier 或 clean replay。

## 数据与隔离

### Design 与 calibration

数据合同为 `benchmarks/fixtures/cpp-jev-offline-qualification-source-pool-v1.json`。12 个项目族来自阶段 A 已核验的 source/build/oracle 合同，但不复用阶段 A 的状态结果作为新标签。

| Split | CMake | Make | Autotools | 状态数 |
| --- | --- | --- | --- | ---: |
| design | `libsoundio`, `cjson` | `stockfish-11`, `xxhash` | `rnnoise-0.1.1`, `libogg` | 18 |
| calibration | `leveldb`, `fmt` | `8cc`, `zstd` | `jansson`, `libyaml` | 18 |

每个项目构造三个状态：缺失编译输入、失效构建状态、错误 build target。三类状态向模型暴露相同字段和相同动作顺序，不暴露 fault 名称、项目 ID、项目族、绑定命令或预先计算的标签。状态日志保留真实构建工具输出。

每个状态的真实动作标签必须由隔离副本中的候选动作执行、严格终点和重复 replay 形成。旧 Agent 动作和阶段 A outcome 都不是真值。若 reference closure、候选动作有界终结、重复一致性或三个构建系统的动作覆盖失败，则停止在数据资格阶段，不调用 Jev。

### Evaluation

Evaluation 只读绑定：

- 路径：`benchmarks/reports/cpp-typed-semantic-routing-pilot-v2.json`
- 文件 SHA-256：`ea2e126e81cfca374900436fa670015b28b3cc3f9d8c83e746ae2c92d2badfed`
- 项目族：6
- 状态：18
- Provider evaluation：最多一次

Design、calibration、evaluation 项目族必须完全不重叠。Issue #391 的 evaluation 已经作为零 Provider 难度审计公开，研究者也可读取其状态和标签；它只可作为**冻结的受控故障 holdout**，不是研究者盲测集。

本 candidate **不满足全局 commit 时间后移**：部分 design/calibration exact commit 晚于 v2 中的项目。因此结果不支持未来时间外推、自然失败总体或开放世界故障覆盖声明。若后续论文需要时间迁移结论，必须另建时间后移 evaluation identity。

## API 与模型合同

官方合同审计见 `docs/research/2026-10-09-jev-api-contract-audit.md`。正式请求固定为：

- Endpoint：`POST https://api.typesafe.ai/v1/systemone`
- SDK：`typesafe-sdk==0.7.3`
- 模型：`jev-1.13.0`
- Credential 环境变量：`TYPESAFE_API_KEY`
- Timeout：30 秒
- SDK `max_retries`：0
- SDK debug 日志：关闭

禁止使用会漂移的 `jev-latest` 或 `jev-preview`。响应 `model` 必须精确等于请求模型，必须保存 request ID、usage、完整概率、confidence、费用和端到端延迟；不得保存 API key 或 Authorization header。

SDK 默认 `max_retries=2`，正式 runner 必须显式覆盖为 0。任何 HTTP、timeout、rate-limit、版本或响应合同错误都只形成一次物理请求，并立即停止当前批次。

## 请求合同

每个状态只向 Jev 发送：

- `build_system`
- 确定性的 `phase_facts`
- `remaining_budget`
- `semantic_failure_log`
- `candidate_action_costs`

一次请求包含两个语义相同的 Choice：

1. `next_action_primary`：`dependency`, `configure`, `build`, `escalate_agent`
2. `next_action_order_sensitivity`：上述顺序完全反转

两题必须共享同一个 state、instructions 和 option descriptions，只允许 criteria 顺序不同。主分析使用第一题；第二题只审计 Jev 1.13 官方记录的 Choice 顺序敏感性。Jev 只返回动作 ID 和概率，不生成命令。

四选一 confidence 的官方公式为 `(p_max - 0.25) / 0.75`。它是最高概率的单调变换，不作为独立研究信号。响应验证必须检查 choice 是最高概率项、概率 key 完整、概率总和在 `1e-6` 内等于 1，并以 `0.02` 容差复算 confidence。

## 开发、校准与冻结顺序

1. Design 最多两轮，每轮 18 个请求。第一轮后只允许依据 design 错误修改一次 Choice instructions 或 criteria；必须保存修改前后完整文本与原因。不得读取 calibration/evaluation Provider 结果来修改问题。
2. 第二轮结束后冻结最终问题。若使用第二轮，第一轮仍保留为开发证据，不计入最终模型指标。
3. Calibration 运行 18 个请求。对三个直接动作的每个 `state × action` 对，以 Jev 给该动作的概率为输入、真实 outcome 是否 route-acceptable 为标签，拟合一维 Platt scaling；`escalate_agent` 不进入该拟合。
4. Platt 输入为裁剪到 `[1e-6, 1-1e-6]` 后的 `logit(p_action)`；实现固定使用 scikit-learn `LogisticRegression(C=1.0, solver="liblinear", random_state=393, max_iter=1000)`。Calibration 必须同时含正负标签，否则停止，不进入 evaluation。
5. 在 calibration 的 18 个主选择上，从观测到的校准概率值由高到低枚举门槛，选择满足零错误直接动作时覆盖最大的门槛；并列时选更高门槛。`escalate_agent`、顺序不一致或低于门槛都拒答。若覆盖少于 `6/18`，停止。
6. 固定 prompt、校准器和门槛后，evaluation 只运行一次。所有 18 个响应 create-once 封存后才读取冻结 label 做分析。

## 基线与指标

基线为：

- `RuleGate`：只读取 phase facts 和动作成本，固定选择 `build`。
- TF-IDF/逻辑回归：沿用 Issue #391 的 word `(1, 2)` n-gram、`sublinear_tf=True`、`max_features=5000` 与 one-vs-rest `liblinear` 配置；只用 design 与 calibration 的 36 个状态训练，evaluation 不参与拟合或调参。
- Jev raw：主 Choice 的 argmax 与原始 confidence。
- Jev calibrated gate：冻结 Platt scaling、顺序一致性和 calibration 门槛。

主要报告：top-1 最优动作准确率、route-acceptable coverage、校准门禁直接执行覆盖率、错误直接动作数、按构建系统结果和顺序一致数。

支持性报告：Macro-F1、Brier score、ECE、风险-覆盖曲线、拒答率、input/output token、模型费用、端到端延迟，以及相对 RuleGate 和 TF-IDF 的逐状态差异。18 个 evaluation 状态只支持描述性比例和逐状态结果，不报告虚假的高精度显著性结论。

## 进入 controller 的候选门槛

只有以下条件全部成立，才将决定记为 `proceed_to_controller_replay_qualification`：

- evaluation top-1 至少 `15/18`；
- calibrated gate 直接执行覆盖至少 `6/18`；
- 错误直接动作 `0`；
- 正序与逆序 Choice 至少 `16/18` 一致；
- CMake、Make、Autotools 均至少有一个正确直接动作；
- 实际请求、token 和费用均未超过预算，且没有版本或响应合同漂移。

任一条件失败，决定为 `stop_jev_controller_and_keep_offline_result`。不得根据 evaluation 结果更换模型、改 prompt、改阈值、改 split、替换状态、retry、backfill 或只报告成功样本。

通过门槛只表示 Jev 有资格进入冻结响应的零 Provider controller 回放，不证明端到端成功率非劣、成本下降或可部署。

## 预算与停止规则

- Design：最多 36 请求
- Calibration：最多 18 请求
- Evaluation：最多 18 请求
- 总请求硬上限：72
- Input token 硬上限：1,000,000
- 按当前官方单价计算的 Jev 模型费用硬上限：`$0.042`
- Output token：按官方当前定价免费，但仍记录 usage

任何 credential/API/timeout/rate-limit 错误、模型版本漂移、字段缺失、概率 key 漂移、概率非法、预算越界或 create-once evidence 冲突都立即停止当前批次并保留失败记录。Evaluation 不允许物理 retry、replacement 或 backfill。

## 当前权限边界

本 candidate 只授权官方文档审计、依赖锁定、数据合同、模拟 HTTP/SDK、测试和零 Provider preflight。它明确不授权：

- 读取 `TYPESAFE_API_KEY` 或 `jev-apikey.txt` 内容；
- 调用 `/v1/models` 或 `/v1/systemone`；
- 创建 Provider attempt 或写 formal Provider evidence；
- 运行新的 Docker outcome collection；
- 实现 controller；
- 修改 Issue #391 或任何历史冻结 evidence。
