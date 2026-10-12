# 进展感知结构化 Agent Harness 资格设计

## 研究背景

Issue #430 的固定 Agent continuation v2 在 9 个冻结 checkpoint、27 个正式 arm 上得到 `12/27` strict success，其中 6 个 arm 因 recorded-token 预算耗尽停止。只读轨迹显示，失败不只来自模型无法生成构建命令：

- `cxxopts-r1` 已完成 build、smoke 和 artifact staging，却未及时提交；
- `kilo-r1` 已暂存有效静态库，之后仍继续无效动作；
- `CLI11` 与 `cxxopts` 的部分 arm 长时间重复诊断；
- `libfastjson` continuation 利用了 checkpoint 中已有的 `configure`，提交 recipe 却遗漏 fresh replay 所需的生成步骤。

因此 v2 只能评价 `deepseek-flash + 300k token + 当前受限 ReAct Harness` 的组合，不能把失败单独归因于模型或预算。Issue #433 先隔离 Harness 因素。

## 研究问题

在模型、预算、checkpoint、工具权限和严格裁判不变时，进展感知结构化 Harness 是否能让受限 ReAct Agent 更稳定地：

1. 识别当前编译进展和下一项未满足义务；
2. 避免连续诊断和已就绪后的额外命令；
3. 在候选就绪后及时调用提交工具；
4. 选择包含 checkpoint 前置步骤的 fresh replay recipe；
5. 减少发送给 Provider 的历史消息和 recorded tokens。

本设计首先完成零 Provider 工程资格，不在工程门禁阶段估计 Agent 效果。

## 对照边界

### H0：当前 Runtime v3

H0 保持 `AgentWorkflowRuntimeV3`：

- 使用 `langchain.agents.create_agent()`；
- 使用 Compiler Agent system prompt；
- 只暴露 `run_container_bash` 与 `submit_candidate_v1`；
- CandidateVerifier 在 candidate freeze 前执行；
- external evaluator、functional oracle、provenance 和 clean replay 在 Agent 外部执行；
- 使用完整消息历史，不注入每轮权威进展快照；
- 不对连续但参数不同的诊断调用做无进展门禁；
- candidate readiness 只由提示词软约束。

### H1：Progress-aware Runtime v4

H1 继承 Runtime v3 的工具、预算、候选验证和外部严格终点，仅增加以下 Harness 机制。

#### 1. 权威进展快照

每次模型请求前重新加载 `CompileSession`，生成版本化 `AgentWorkflowProgressSnapshot`：

- Session、构建系统和 target identity；
- 各 command role 的成功、失败和超时计数；
- 最近命令的 ID、role、exit code、workdir 和有界命令预览；
- 全部成功 build、smoke、artifact-stage command ID；
- 按 Session 顺序列出的 fresh replay 候选 command ID；
- `/artifacts` 下的非符号链接普通文件相对路径；
- target pattern 与 staged artifact 的确定性匹配；
- `candidate_ready`、连续诊断数和自上次可观察进展后的工具调用数。

快照只来自权威 Session 和文件系统，不读取模型自述，不修改历史 evidence。

#### 2. 确定性上下文裁剪

Provider 请求保留：

- 初始任务消息；
- 最近两个完整 model/tool interaction；
- 当前未闭合 tool-call 对；
- 最新权威进展快照。

更早消息保留在 LangGraph 内存状态和 evidence 中，但不重复发送给 Provider。裁剪不得制造 dangling tool call，也不得删除当前未返回的 tool result。

#### 3. 候选就绪门禁

当同时存在成功 build、成功 artifact-stage 和至少一个 staged file 时，`candidate_ready=true`。在同一 command frontier 上，Agent 必须先调用 `submit_candidate_v1`；新的 `run_container_bash` 调用被 Harness 拒绝并返回结构化原因。

若 CandidateVerifier 拒绝提交，Harness 记录该 frontier 已尝试提交，允许 Agent 根据结构化 rejection 执行修复。Harness 不自动提交、不自动接受候选，也不把 readiness 当作成功。

#### 4. 连续诊断无进展门禁

若最近 4 个已执行命令均为 `diagnostic`，且期间没有新的成功 build、artifact-stage 或 staged file，则下一次 diagnostic 调用被拒绝。Agent 必须选择 dependency/configure/build、提交已就绪候选，或结束失败。

该门禁按 role 和权威进展判断，不只比较完全相同的命令字符串。

#### 5. Recipe 闭包建议

快照按 Session 顺序列出所有成功且可进入 replay 的 `dependency`、`dependency_setup`、`configure`、`build`、`artifact_stage` command ID。它是提交建议，不自动改写 Agent 的 payload；CandidateVerifier 和 external evaluator 继续决定 recipe 是否真实闭合。

## 明确不做

- 不更换模型、温度、thinking、streaming 或 Provider retry；
- 不提高 token、请求、工具、命令或时间预算；
- 不接入 Jev 或动态预算 controller；
- 不自动生成任意 Shell 命令；
- 不让 Harness 绕过 `submit_candidate_v1`、CandidateVerifier 或 S0-S5；
- 不修改 Issue #430 的 manifest、runner、report 或 raw evidence；
- 不在本阶段运行 Claude Code、Codex 等通用 Agent Harness。

## 零 Provider 资格门禁

独立 identity 为 `cpp-progress-aware-harness-qualification-v1`，只允许脚本模型和真实 Docker/checkpoint，不读取 credential，不调用 Provider。

必须通过：

1. 结构化快照只使用权威 Session，序列化稳定且不包含绝对宿主路径；
2. 上下文裁剪保留初始任务、最近完整交互和未闭合 tool pair；
3. ready frontier 上额外命令被拒绝，提交被允许；
4. verifier rejection 后允许修复，新的 progress frontier 再次要求提交；
5. 连续 4 个无进展 diagnostic 后，第 5 个 diagnostic 被拒绝；
6. checkpoint 前成功的 replay command ID 出现在 recipe 建议中；
7. H0 行为保持不变；
8. Runtime v4 在真实 Docker checkpoint 上由脚本模型完成 build、stage、一次 ready 拒绝、submit、CandidateVerifier、external evaluator 和 clean replay；
9. cleanup 后受管容器为 0，旧 evidence inventory 不变。

任一门禁失败即停止 Provider H0/H1 比较，先修复或放弃 H1 identity，不用模型调用掩盖工程缺陷。

## 后续 Provider 比较候选

零 Provider 门禁通过后，另行冻结 Provider identity。候选设计为 CLI11 state-2、cxxopts state-3、kilo state-3 三个困难 checkpoint，H0/H1 各 3 次，共 18 个 arm；两臂共享 `deepseek-flash`、单臂 300,000 recorded tokens、24 requests 和相同严格终点。

Provider 比较的主结果是 strict success 和 candidate submission；次要指标包括 budget exhausted、recorded tokens、请求数、命令数、连续诊断拒绝、ready-to-submit 延迟、recipe closure、墙钟和费用。正式样本、成本上限、顺序、停止规则和门槛必须在调用 Provider 前预注册。

## 解释边界

零 Provider资格只能证明 H1 工程机制真实接线且不破坏严格终点。未来 H0/H1 Provider 比较也只评价冻结 checkpoint、模型和预算下的 Harness 增量；不能直接推广到自然失败、开放世界、其他模型或通用 Agent。

