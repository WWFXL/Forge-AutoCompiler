# 项目状态快照 (Project State Snapshot)

跨 Claude Code session 的项目状态流水。按 CLAUDE.md §7 维护。

## 进行中 (In Progress)
<!-- 跨 session 未完成的工作。完成后挪到「最近变更」。 -->

- 2026-07-27 — Issue #52 artifact oracle 结构化差异
  - 分支: `feat/issue-52-artifact-oracle-diff`，基于 `main@82a29a9e`。`run_oracle()` 在不改变既有 pass 判定公式的前提下，输出排序且最多 64 项的 expected-only、observed-only、type mismatch 与 matched identity；clean replay 比较另输出 type/size/SHA-256/smoke exit+output hash 差异。
  - 安全: 只保留 `/artifacts` 相对路径、三类 artifact type、非负大小、SHA-256、smoke 退出码和输出哈希；不复制 smoke command/output、模型文本、宿主路径或凭据。旧 replay 没有逐产物比较时明确 `available=false`，不伪造诊断。
  - 当前证据: runner/protocol/evidence `204 passed`，后端全量 `1665 passed, 29 skipped`，真实 Docker CMake executable、Make static/shared、Autotools static 三组 `3 passed`；22 条本地历史 ledger hash chain 通过，后端 Ruff/format、Compose、前端串行 lint/typecheck 与容器对账通过。未调用模型、未重跑/替换 v6、未创建 v7。
  - 待完成: 复核 diff、中文提交并推送，创建 Draft PR，等待 Ready CI 后 squash merge；随后更新 Obsidian 并冻结 v7 设计入口。

## 最近变更 (Recent Changes)
<!-- 倒序，最新在上。 -->

- 2026-07-27 — 分离 compiler 四类预算并闭合终结证据
  - 范围: 为未来协议显式分离模型轮次、LangGraph 递归、compiler 总墙钟与 post-build 预留；旧 `compiler_max_turns` / `subagent_timeout_seconds` 继续作为兼容回退，v1-v6 policy payload、manifest、Schema、validator、runner 与 ledger 保持不变。
  - 终结: 新增 `model_turn_limit`、`graph_recursion_limit`、`compiler_wall_clock_timeout`、`post_build_reserve_exhausted` 单一分类；终结事件只记录有界数字/布尔预算快照，所有失败路径继续先停 worker、清理真实编译容器再 finalize。
  - 证据: 聚焦 `68 passed`，后端全量 `1674 passed, 28 skipped`，Ruff 与 Compose config 通过；真实 Docker 四预算分支 `4 passed`，前端 lint/typecheck 通过，冻结实验资产无差异。未调用模型、未重跑或替换 v6，也未创建 v7。

- 2026-07-26 — 实现 Issue #50 的冻结构建参数前置契约
  - 范围: 在实验真实 build 执行前，从此前成功 configure 或当前复合 configure+build 命令中按有序 token 子序列验证 CMake/Autotools 冻结参数；缺参返回 `126 policy_rejected`，不执行 build、不进入 post-build、不启动 replay。submit gate 继续作为第二道防线。
  - 证据: CMake/Autotools 正反例及复合命令 `8 passed`，相关回归 `173 passed, 1 skipped`，后端全量 `1626 passed, 48 skipped`；Ruff、Compose config、v6 五条 ledger 和 22 个 baseline component 审计通过；真实 Docker 非模型场景确认 build 未执行且无 replay。
  - GitHub: 中文提交 `3c18eb98`，Draft PR #53；Draft backend/frontend lint 已通过，Unit Tests 在 Draft 状态下 skipped。v1-v6 manifest、Schema、validator 与 ledger 未改写，没有模型调用或 v7 运行。

- 2026-07-26 — 完成 C/C++ pilot v6 五个不可替换 physical attempt
  - 结果: 五条 ledger 的 hash chain、离线 gate、终结与 orphan reconciliation 有效，0 orphan、0/5 oracle pass。`hiredis` 到达 submit/clean replay/delivery 后被 artifact oracle 拒绝；`libcheck`/`libgit2` 暴露 subagent timeout，`sysstat` 暴露 recursion limit，`libgit2`/`sysstat` 同时暴露参数契约过晚。
  - 边界: v6 证据冻结，不 retry、replacement、fallback 或回填；后续修复只能进入新协议。

- 2026-07-26 — 重排 Issue #38 的 C/C++ pilot v5 冻结协议
  - 范围: 从当前主干冻结独立 v5 manifest、Schema、validator 与 runner 路由，记录 capability、selected 与 executed identity；v1-v4 与既有 ledger 保持字节不变。
  - 边界: 只重排与审计协议，不调用模型、不创建、执行、覆盖或 replacement 任一 physical-attempt slot，也不启动 v6。

- 2026-07-26 — 重排 Issue #34 的多构建系统 identity policy
  - 范围: 将旧堆叠单提交重放到 `main@1bcf0caa`；分离仓库 capability set、实验 selected path 与 submit 时由成功命令证明的 executed path，保留 `expected_build_system` 的证据兼容性。
  - 边界: identify 只校验 selected 属于 capability set；submit 仍要求 executed 等于 selected，缺少证明或换路均拒绝。v1-v5 manifest、Schema、validator 和既有 ledger 均不改写。

- 2026-07-26 — 重排 Issue #33 的非交互澄清修复
  - 范围: 将旧堆叠的单提交重放到 `main@b0e9b0e5`；标准仓库 URL + exact commit 明确允许直接进入隔离编译，活跃实验只对 Lead 的首次澄清返回冻结 policy，并记录有界 `agent.clarification_auto_answered` 证据。
  - 安全与兼容: 不记录问题、回答、prompt 或模型文本；第二次澄清与普通交互仍结束回合等待用户。v1-v5 manifest、Schema、validator 与既有 ledger 均不改写。

- 2026-07-25 — 重排并验证 Issue #32 的运行级异步 event-loop ownership 修复
  - 范围: 将旧堆叠中的单提交增量重放到 `main@2cfbf795`；已有运行 loop 时直接创建 compiler 后台 task，无运行 loop 的同步兼容调用仍使用隔离线程。
  - 兼容: v4 runtime current-tree gate 仍拒绝随后合法的 `executor.py` 漂移；历史 component blob 审计与冻结 manifest/Schema/validator/ledger 保持不变。executor 测试 fixture 不再 reload 模块，避免 enum class identity 伪失败。
  - 证据: v4/executor 聚焦 `48 passed, 1 skipped`，后端全量 `1565 passed, 27 skipped`；Ruff、format、`py_compile`、Compose config 与 diff 检查通过。
  - 边界: 仅实现与验证修复；不调用模型、不执行或替换任何 pilot，不改写 v1-v5 protocol/ledger。

- 2026-07-25 — 记录有界的 agent 工具失败与无编译动作终态证据
  - 文件: `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py`、`backend/packages/harness/deerflow/compile/evidence.py`、`scripts/forge_benchmark_runner.py` 及对应测试
  - 动机: Issue #26；区分 endpoint、agent/tool、build、submit/replay 与 completion 失败域，避免 tool exception 仅留在 stderr、模型完成却没有编译动作只表现为 `submit_missing`
  - 安全与语义: `agent.tool_failed` 仅白名单记录角色、工具名、tool-call ID、异常类、sync/async 与 `terminal=false`；仅在模型请求已完成、流显式结束、零编译工具调用时记录终态 `agent.no_compile_progress`。不读取或写入 prompt、模型内容、工具参数、stdout/stderr、异常文本、headers、密钥或宿主路径。
  - 边界: 专用 Schema 同时保护 append/verify 并覆盖 digest-valid 篡改、终态后拒写和敏感内容；保留 PR #27 异步 runner、PR #28 identity gate、v3 history/current-tree 审计；v1-v5 manifest、Schema、validator、runner hash 与 ledger 未改写，也没有模型调用或 pilot replacement。
  - 证据: 聚焦 `50 passed`，兼容/历史/异步/compile lifecycle `261 passed, 6 skipped`，后端全量 `1543 passed, 26 skipped`，真实 Docker mismatch `1 passed in 17.82s`；Ruff check、`py_compile`、Compose config、`git diff --check`、冻结资产与无遗留 compile/replay 容器通过。前端没有差异；lint 为 7 个既有 warning，format、typecheck/build 分别被既有格式与 i18n 类型问题阻塞。

- 2026-07-25 — 重排并验证 Issue #30 的 C/C++ pilot v4 协议
  - 范围: 将旧堆叠提交重放到当前 `main`；基线改为已审阅的 PR #29 squash 提交 `1e4bad22117ad01058310a8625925e7801a8eff2`，保留 v1-v3 历史协议和既有 ledger 字节不变。
  - 证据: manifest validator、v1-v4 benchmark/runner `134 passed, 7 skipped`、后端全量 `1563 passed, 27 skipped`、真实 Docker build-system mismatch `1 passed in 17.95s`、Ruff、format、`py_compile`、Compose config 与 `git diff --check` 通过。
  - 边界: 仅实现、复核和冻结协议；不调用模型、不创建或替换 pilot physical attempt，也不启动 v6。

- 2026-07-21 — 冻结并校验 benchmark case 的构建系统身份
  - 文件: `backend/packages/harness/deerflow/compile/evidence.py`, `backend/packages/harness/deerflow/compile/operations.py`, `backend/packages/harness/deerflow/tools/builtins/agent_compile_tools.py`, `backend/packages/harness/deerflow/tools/builtins/task_tool.py`, `scripts/forge_benchmark_runner.py` 及对应测试
  - 动机: Issue #25；把 manifest `cases[].build_system` 写入 `ExperimentPolicy` 和首条 ledger policy，compiler prompt 固定 CMake/Make/Autotools 路径，避免声明的实验条件与实际构建路径漂移
  - 行为: `identify_build_system` 后记录 expected/observed identity；不匹配时在 compiler 子代理启动前失败终结并清理 Session，submit gate 再独立复核，不修改 v1/v2/v3 manifest、Schema 或既有 ledger
  - 证据: policy/runner/prompt/terminalization/submit gate 聚焦组 `150 passed`，异步 client、v2/v3 历史 gate、取消与 task 兼容组 `242 passed, 6 skipped`，后端全量 `1532 passed, 26 skipped`；真实 Docker mismatch `1 passed in 16.83s`，确认 CMake fixture 在预期 Autotools 时不会进入 compiler 且无遗留 compile/replay 容器；Ruff、format、Compose、冻结资产、前端串行 format/lint/typecheck/build 与 `git diff --check` 通过

- 2026-07-19 — 让 benchmark runner 通过原生异步事件流执行 compiler 子代理
  - 文件: `backend/packages/harness/deerflow/client.py`, `scripts/forge_benchmark_runner.py`, `backend/tests/test_client.py`, `backend/tests/test_forge_benchmark_runner.py`, `backend/tests/test_forge_benchmark_v3.py`, `backend/CLAUDE.md`
  - 动机: Issue #24；为 embedded client 增加与同步事件语义一致的 `astream()`，runner 通过 `asyncio.run()` 消费 LangGraph `agent.astream()`，使 async-only `task_tool` 不再进入 `StructuredTool does not support sync invocation`，且不增加阻塞包装或改写 v1/v2/v3 协议与 ledger
  - 证据: async-only `StructuredTool` 单次调用和 stream/chat `19 passed`；benchmark/evidence/runner/terminal/cancellation `129 passed, 2 skipped`；compile `115 passed`；定向 Ruff、format、`py_compile` 与 `git diff --check` 通过
  - 实机: Compose/DooD 中以独立非 pilot thread 和 `gpt-5.4` 完成 `CMakeHelloWorld@6fda0b1` 的 Lead -> async task -> compiler -> submit -> clean replay -> finalize；Session `completed`，16,504 字节 ELF 的 SHA-256 为 `33114a53b889e9b6d810929a1420a24c33ac04b3646a26e180cfca62b93a0c20`，两个容器均已删除

- 2026-07-19 — 完成 pilot v3 五个 physical attempt 并审计三类新阻塞
  - 文件: `.compile-sessions/benchmark-evidence-v3/`（本地 Git 忽略的 append-only ledger）, `.claude/memory/project.md`
  - 结果: `fmt`、`hiredis`、`libcheck`、`libgit2`、`sysstat-nondeterministic` 五份 ledger 的 hash chain 与离线 gate 全部有效，全部为 `submit_missing`，0 submit、0 clean replay、0 replacement、0 遗留 compile/replay 容器；`fmt`/`hiredis` 首个 lead 请求超时，`libcheck`/`sysstat` 在 exact clone 后的后续 lead 请求超时，`libgit2` 模型成功返回但没有编译工具调用
  - 修复证据: `libcheck` 与 `sysstat` exact commit 匹配，证明 Issue #16 clone ownership 修复生效；两个 session 都为 `failed`、已 finalized 且容器删除，证明 Issue #17 兜底生效；`libcheck`、`libgit2`、`sysstat` 的成功响应均记录 `actual_model=gpt-5.6-sol`，证明 Issue #18 提取生效
  - 新发现: embedded runner 的同步 `DeerFlowClient.stream()` 不能调用 async-only `task_tool`；manifest `build_system` 未进入 `ExperimentPolicy`，`libcheck` 声明 Autotools 但 observed 为 CMake；tool failure 与模型成功但 0 编译动作都缺少有界 ledger 事件。已创建 Issue #24、#25、#26；v3 不做 replacement，修复后必须冻结新协议版本

- 2026-07-18 — 冻结包含 Issue #16/#17/#18 修复的 C/C++ pilot v3 协议
  - 文件: `scripts/forge_benchmark_v3.py`, `scripts/forge_benchmark_runner.py`, `benchmarks/manifests/cpp-pilot-v3.json`, `benchmarks/schemas/forge-cpp-benchmark-v3.schema.json`, `benchmarks/README.md`, `backend/tests/test_forge_benchmark_v2.py`, `backend/tests/test_forge_benchmark_v3.py`, `backend/tests/test_forge_benchmark_runner.py`
  - 动机: 在不修改 v1/v2 协议和五份 v2 ledger 的前提下，以 `371f678e` 冻结 ownership、session terminalization 与 actual-model 提取修复；runner 默认路由 v3，同时继续接受历史 v1/v2，并保持 `compose-dood`、`gpt-5.6-sol`、120 秒、0 provider retries、无 fallback 和 Memory/Skills 关闭
  - 证据: v3 canonical digest `d67ab40eb75db7edd01dbf760ec3b01ca495c08a3bdb05f4f33f07ce90e1b92f` 在 Windows/WSL 一致；Schema meta/instance validation、benchmark/runner/evidence `114 passed, 2 skipped`、compile `115 passed`、model/evidence `38 passed`、真实 Docker `4 passed in 90.68s`、定向 Ruff/format、`py_compile` 与 `git diff --check` 通过；提交前 preflight 除预期 `forge_clean=false` 外全部匹配

- 2026-07-20 — 将 Issue #18 / PR #21 的 actual-model evidence 修复重排到 `main@796cf05a` 并完成本地验证
  - 文件: `backend/packages/harness/deerflow/compile/evidence.py`, `backend/tests/test_experiment_evidence.py`, `.claude/memory/project.md`
  - 动机: LangChain `ModelResponse.result` 是结构化 message 列表，旧 helper 把整个列表当成单个候选，因而漏读 `AIMessage.response_metadata`；新实现最多遍历 8 个 message，允许模型身份与 usage 来自不同 message
  - 安全边界: 只读取 `response_metadata.model_name/model` 和三项非负整数 token usage；unsafe model 与布尔 token 被拒绝但不改变模型调用结果；不读取或保存 content、prompt、response body、headers、异常文本、密钥或宿主路径，provider 未提供身份时保持 `actual_model=null`
  - 证据: 模型/evidence `46 passed`，benchmark/runner/evidence `104 passed, 3 skipped`，带 Git 的 v2 历史测试 `10 passed`，后端全量 `1507 passed, 22 skipped`；后端 Ruff/format、Compose config、前端串行 format/lint/typecheck/build、diff 和无遗留容器检查通过
  - 边界: v1-v5 manifest、Schema、validator、协议哈希和 ledger 未修改或重跑；本阶段没有模型请求，等待 PR 完整 CI 与合并
- 2026-07-20 — 将 Issue #17 / PR #20 的 runner Session 终结修复重排到最新主干并完成本地验证
  - 文件: `scripts/forge_benchmark_runner.py`, `backend/tests/test_forge_benchmark_runner.py`, `backend/tests/test_compile_replay_docker.py`, `.claude/memory/project.md`
  - 动机: runner 在嵌入式 client 正常返回、异常或提前退出后，先同步终结该 physical attempt thread 的未完成 Compile Session，再清理 orphan；首次终结未闭合但 orphan 清理成功时幂等重试，endpoint failure、Session lifecycle 与 orphan cleanup 保持独立证据域
  - 证据: runner 单测 `12 passed`，benchmark/evidence `100 passed, 3 skipped`，带 Git 的 v2 历史测试 `10 passed`，compile runtime/terminal/cancellation `115 passed`，后端全量 `1503 passed, 22 skipped`，真实 Docker exact clone/session finalization/clean replay `4 passed in 94.88s`；改动文件 Ruff/format、Compose config、前端 lint/typecheck/build、冻结资产和 diff 检查通过且无遗留容器
  - 边界: 全量 Ruff 的 4 个错误均位于未改动且与 `origin/main` 相同的 `scripts/check.py`、`scripts/forge_benchmark.py`；Issue #22 计划中的 v2 current-tree drift 测试语义提前并入本 PR，继续要求旧 runner 漂移被明确拒绝；v1-v5 manifest、Schema、runner hash 与 ledger 未修改或重跑，未启动 v6 pilot；CI 与合并待完成
- 2026-07-20 — 将 Issue #16 / PR #19 的 exact-commit clone ownership 修复重排到最新主干并完成本地验证
  - 文件: `backend/packages/harness/deerflow/compile/operations.py`, `backend/tests/test_compile_runtime.py`, `backend/tests/test_compile_replay_docker.py`, `.claude/memory/project.md`
  - 动机: 从旧堆叠基线提取单一修复，在 `git init` 后、首次 `git -C`/fetch 前配置容器内 `/workspace/repo` 为 `safe.directory`；保持 remote URL、完整 commit、普通 clone、clean replay、artifact gate、v1-v5 协议和 ledger 不变
  - 证据: compile runtime/terminal/cancellation `115 passed`，后端全量 `1500 passed, 21 skipped`，真实 Docker exact clone 与两条 clean replay `3 passed in 89.62s`；全量 Ruff、Compose、前端 lint/typecheck/build、diff 和无遗留 compile/replay 容器检查通过

- 2026-07-20 — 将 v2 pilot 协议与既有五 case 审计重排到主干，并增加 squash provenance 校验
  - 文件: `scripts/forge_benchmark_history.py`, `backend/tests/test_forge_benchmark_v2.py`, `benchmarks/README.md`, `.claude/memory/project.md`
  - 动机: v2 历史实验绑定 `d845b735`，而 Issue #11 重排后 head `561b38ce` 被 squash 为 `9e002f45`，Git ancestry 不再连续；在不改写 v2 manifest、Schema、validator、runner、canonical digest 或 ledger 的前提下，显式验证 baseline blob、两端 tree 身份和 successor ancestry
  - 证据: `561b38ce` 与 `9e002f45` 的 tree 均为 `29aa07d5...`；WSL 宿主正向审计通过且无关旧分叉 head 被拒绝；benchmark/v1/v2/runner `91 passed, 3 skipped`，compile/model 聚焦 `152 passed`，后端全量 `1499 passed, 20 skipped`，真实 Docker replay `2 passed in 77.60s`；全量 Ruff、Compose、前端 lint/typecheck/build、frozen-byte 与 diff 检查通过

- 2026-07-20 — 将 physical-attempt evidence ledger 重排到最新主干并修复模型工厂测试契约
  - 文件: `backend/tests/test_lead_agent_model_resolution.py`, `.claude/memory/project.md`
  - 动机: PR #13 在 `main` 已包含 Issue #10 后改为单提交增量；模型工厂新增实验 thread/role 参数后，同步测试替身并断言普通会话不会携带实验 thread ID
  - 证据: benchmark/ledger/runner `87 passed`，compile runtime/terminal/cancellation `114 passed`，模型 middleware/factory `30 passed`，后端全量 `1489 passed, 17 skipped`，真实 Docker replay `2 passed in 75.55s`；Ruff、Compose、前端 lint/typecheck/build、冻结资产、diff 与敏感信息检查通过

- 2026-07-20 — 将 C/C++ benchmark 协议重排到最新主干并完成发布前验证
  - 文件: `scripts/forge_benchmark.py`, `backend/tests/test_forge_benchmark.py`, `benchmarks/README.md`, `benchmarks/manifests/cpp-pilot-v1.json`, `benchmarks/schemas/forge-cpp-benchmark-v1.schema.json`, `.github/workflows/backend-unit-tests.yml`
  - 动机: 在不改写 v1-v5 冻结 manifest、Schema、记录器或账本的前提下，把 Issue #10 的协议增量从旧 clean-replay 分支重放到 `main`；Forge 组件按 manifest 声明的历史 Git revision 校验，当前 recorder 与 Schema 仍按工作树字节校验，CI checkout 获取完整历史以执行同一严格检查
  - 证据: 聚焦回归 `183 passed`，后端全量 `1470 passed, 17 skipped`，后端 Ruff、前端 lint/typecheck/build、Draft 2020-12 meta-schema、冻结资产、diff 与敏感信息检查通过
- 2026-07-18 — 完成 v2 五 case 首次 physical pilot 并保留失败证据
  - 文件: `.compile-sessions/benchmark-evidence/`（本地 Git 忽略的 append-only ledger），`.claude/memory/project.md`
  - 动机: 在 clean-tree preflight `ready=true` 后，以 `gpt-5.6-sol`、0 provider retries、无 fallback、Memory/Skills 关闭和 `compose-dood` 严格串行执行 `fmt`、`hiredis`、`libcheck`、`libgit2`、`sysstat-nondeterministic`；每个 slot 在首个模型请求前已有独立 ledger，未 replacement
  - 结果: 5/5 ledger hash chain 与离线 gate recomputation 有效且无 mismatch，但 5/5 oracle 均为 `submit_missing`，0 submit、0 clean replay；`fmt` 未创建 session，`hiredis`/`sysstat` 因 WSL bind mount Git ownership 导致 clone 128，`libcheck`/`libgit2` 出现冻结 120 秒 endpoint timeout；所有 reconciliation 成功且最终无残留容器
  - GitHub: Draft PR #15；Issue #14 已回帖；新增 #16（clone safe.directory）、#17（异常后 session 终态）、#18（actual model 证据）

- 2026-07-18 — 冻结可执行的 C/C++ pilot v2 协议与 Compose/DooD preflight
  - 文件: `scripts/forge_benchmark_v2.py`, `scripts/forge_benchmark_runner.py`, `benchmarks/manifests/cpp-pilot-v2.json`, `benchmarks/schemas/forge-cpp-benchmark-v2.schema.json`, `benchmarks/README.md`, `.gitignore`, `backend/tests/test_forge_benchmark_v2.py`, `backend/tests/test_forge_benchmark_runner.py`
  - 动机: 保持 v1 字节不变，以 `d845b735` 作为必须被 clean HEAD 包含且组件无漂移的运行实现基线，冻结 Issue #11 的 20 个 runtime/evidence 组件与 4 个协议文件，显式校验 `compose-dood` 并解除新版 instrumentation blocker；`run` 在首个模型请求前还会核验自身确实位于带 Docker socket 的 `deer-flow-dev/langgraph` 容器；本地 evidence/results 已忽略，避免首个 ledger 使后续 case preflight 误报脏工作树
  - 证据: Windows/WSL canonical digest 一致；v2 Schema 通过 Draft 2020-12 meta-schema；benchmark/runner `92 passed, 1 skipped`，compile `114 passed`，model `30 passed`，真实 Docker replay `2 passed in 66.68s`；20 个 baseline Git 组件哈希、真实容器内 topology gate、定向 Ruff/format、`py_compile`、`git diff --check` 与无遗留容器检查通过

- 2026-07-18 — 实现 C/C++ pilot runner 与 physical-attempt evidence ledger
  - 文件: `scripts/forge_benchmark_runner.py`, `backend/packages/harness/deerflow/compile/evidence.py`, `backend/packages/harness/deerflow/compile/operations.py`, `backend/packages/harness/deerflow/agents/middlewares/llm_error_handling_middleware.py`, `backend/tests/test_experiment_evidence.py`, `backend/tests/test_forge_benchmark_runner.py`
  - 动机: 在首个模型请求前持久化实验尝试，以 hash chain 记录物理模型请求、命令、submit/replay/delivery gate、actual model/endpoint 和 orphan reconciliation；runner 强制 exact commit、镜像、依赖、环境、有序构建参数、replay delay、模型重试/超时与 compiler 预算，且拒绝重复 slot、fallback、密钥/宿主路径和终态后写入
  - 证据: benchmark/ledger/runner `87 passed`，compile runtime/terminal/cancellation `114 passed`，模型 middleware/factory `30 passed`，真实 Docker replay `2 passed in 63.14s`；定向 Ruff/format、`py_compile`、Compose config、`git diff --check` 与 WSL preflight 通过

- 2026-07-18 — 冻结 C/C++ pilot 协议、manifest、证据 Schema 与原子 JSONL 记录器
  - 文件: `scripts/forge_benchmark.py`, `backend/tests/test_forge_benchmark.py`, `benchmarks/README.md`, `benchmarks/manifests/cpp-pilot-v1.json`, `benchmarks/schemas/forge-cpp-benchmark-v1.schema.json`
  - 动机: 用 5 个 exact-commit C/C++ case 固定模型、端点、WSL/Docker、镜像、超时/重试与 lifecycle 口径，并让每条 run record 可校验、可锁定、可重复拒绝且不含密钥或宿主路径；本阶段只完成采集基础设施，未发起模型 pilot
  - 证据: benchmark `75 passed`，compile runtime/terminal/cancellation `108 passed`，Ruff check/format、`py_compile`、Draft 2020-12 meta-schema、Windows/WSL manifest digest 对照及独立 P1/P2 复核通过

- 2026-07-17 — 自动在独立容器中验证候选构建 recipe，并把 replay 证据纳入完成条件
  - 文件: `backend/packages/harness/deerflow/compile/docker_runtime.py`, `backend/packages/harness/deerflow/compile/manager.py`, `backend/packages/harness/deerflow/compile/operations.py`, `backend/packages/harness/deerflow/compile/schemas.py`, `backend/tests/test_compile_runtime.py`, `backend/tests/test_compile_cancellation.py`, `backend/tests/test_compile_replay_docker.py`
  - 动机: 使用不可变镜像 ID、空 workspace/artifacts 和只读 recipe 执行 clean replay，严格比较产物集合、类型、大小、SHA-256 与 smoke 输出；用 session termination fence、持锁 container checkpoint、超时后按名称对账和终态白名单合并处理取消/超时竞态
  - 证据: compile runtime/terminal/cancellation 共 `108 passed`，真实 Docker integration `2 passed`，Ruff check/format 与独立 P1/P2 复核通过
  - GitHub: PR #9 已 squash 合并为 `a4ffdbde`，Issue #7 已关闭

- 2026-07-17 — 生成固定源码且可在全新 C/C++ 编译容器中回放的候选构建脚本
  - 文件: `backend/packages/harness/deerflow/compile/operations.py`, `backend/tests/test_compile_runtime.py`, `README_zh.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `backend/CLAUDE.md`
  - 动机: 从审计轨迹中筛选成功 bash 步骤，固定实际 clone URL 与完整 commit SHA，隔离宿主路径并把 replay 生成失败纳入验证；两次独立 `autocompiler:gcc13` replay 均得到相同 16,504 字节 ELF 和基线 SHA-256

- 2026-07-15 — 支持在 Windows + WSL2 中运行 Docker 开发环境和嵌套编译容器
  - 文件: `scripts/wsl-check.sh`, `scripts/docker.sh`, `docker/docker-compose-dev.yaml`, `docker/compile/Dockerfile`, `backend/packages/harness/deerflow/config/paths.py`, `backend/packages/harness/deerflow/compile/docker_runtime.py`
  - 动机: 统一服务可见路径与宿主 Docker 可见路径，补齐编译镜像、网络、配置模板和可复现的 WSL 启动流程

## 待办 (TODOs)
<!-- 发现但未做的事。带 file:line 指针。 -->

- 清理与当前源码不一致的后端测试模块引用，例如 `backend/tests/test_aio_sandbox_local_backend.py:1` 和 `backend/tests/test_channels.py:14`。
- 统一 `backend/tests/test_subagent_timeout_config.py:261` 对 `max_turns` 的期望值与当前实现默认值。
- 完成 Issue #52 的 Draft PR、Ready CI、squash merge、Issue 自动关闭和主干复验；Issue #52 合入前不创建 v7、不调用模型、不重跑 v6。
- 当前 `backend/packages/harness/deerflow/compile/manager.py` 的 lifecycle lock 是进程内锁；部署多个后端进程前，需要改为文件锁/数据库事务或带版本号的 CAS，并增加跨进程竞态测试。

## 已知问题 (Known Issues / Pitfalls)
<!-- 工作中踩过的坑、限制或意外行为。 -->

- WSL 用户目录中的 `.local` / `.cache/uv` 可能由旧容器以 root 创建，原生 WSL 执行 `uv` 会报 `Permission denied`；不要改写权限掩盖来源，测试可把 `UV_CACHE_DIR`、`UV_PYTHON_INSTALL_DIR` 与 `UV_PROJECT_ENVIRONMENT` 指向用户可写的独立目录。
- Docker Hub 匿名 token 与 Ubuntu archive 在当前网络下可能分别超时或返回 502；本机可从 Canonical 官方 Amazon ECR 拉取同源 Ubuntu 基础镜像并改回本地 `ubuntu:24.04` 标签，apt 构建可显式传可信镜像站，但不得把临时镜像源写进冻结实验协议或伪装成既有 image ID。
- 协作语言约定：后续 GitHub Issue、Pull Request、评论、评审说明和提交说明默认使用中文；分支名、代码标识、命令和必要技术术语继续遵循仓库的 ASCII/既有命名规范。若外部协作明确要求英文，先向用户确认。
- PowerShell -> WSL -> `bash -lc` 的多层命令可能提前展开临时 `$repo` 变量，使 Docker bind mount 退化为 `/frontend/...`；一次性容器优先传完整 WSL 绝对路径，启动失败后先按固定名称清理并确认无残留。
- Docker Desktop 与 WSL 原生 Docker Engine 是两个独立 daemon，镜像、网络和容器不共享；Forge 命令必须始终在同一套 daemon 上执行。
- WSL 的 `127.0.0.1` 代理不能直接传入 Docker build；编译镜像代理必须使用容器可达地址。
- 后端全量 Ruff 当前有 4 个本次改动之外且与 `origin/main` 相同的既有错误：`scripts/check.py` 的 3 个 UP045 与 `scripts/forge_benchmark.py` 的 1 个 I001；本次改动文件的 Ruff check/format 已通过。
- 成功 bash 记录只是候选 recipe；失败命令可能留下持久副作用。进入研究基线前必须在新容器与空 `/workspace`、`/artifacts` 中实际 replay，不能把 `repro_bundle` 生成成功等同于独立复现成功。
- Windows 挂载目录在编译镜像中可能触发 Git `dubious ownership`；replay 初始化仓库后必须把 `/workspace/repo` 加入 `safe.directory`。
- 不要把含 `$()`、重定向和多层引号的后验校验直接嵌进 PowerShell → WSL → `docker run ... bash -lc`；参数可能被中间层重解释。应先单独运行 `bash /repro/build.sh` 获取退出码，再用独立命令检查类型、输出与哈希。
- `docker run` 客户端超时不证明 daemon 没有稍后创建容器；replay 必须使用确定性名称，在超时后反复对账并幂等删除，且 create/checkpoint/parent cleanup 必须由同一 session lock 串行化。
- 取消、超时与同步 submit 可能持有不同的 stale session 副本；第一条持久化 termination reason 必须胜出，终态后的 cleanup 只能按 `attempt_id` 白名单合并可变清理字段，不能覆盖镜像、commit、recipe、产物或检查证据。
- Manifest 中声明的模型、端点、镜像和运行参数只是实验意图，不是实际运行证明；observed 字段必须由 runner 从真实请求、Forge 状态和 Docker 结果写入。
- Benchmark run record 必须固定 recorder 与 Schema 的 SHA-256；只固定 manifest 不足以证明不同批次使用了相同采集语义。
- 默认 physical-attempt ledger 写入 `benchmarks/evidence/`；该目录必须保持 Git 忽略，否则第一个 case 创建 evidence 后会让后续 clean-tree preflight 全部失败。忽略只影响版本控制，不得覆盖或删除本地 append-only ledger。
- Windows/WSL bind mount 的 initial exact-commit clone 在 `git init` 后也必须配置容器内 `/workspace/repo` 为 `safe.directory`；只在 clean replay 配置不够，pilot 已观察到 clone 退出 128。
- runner 的 orphan reconciliation 删除容器不等于 Compile Session 已终结；endpoint timeout 后必须同步 authoritative session 终态，否则 session 可能停在 `ready`。
- compatible endpoint 的成功 response 可能不提供实际模型字段；`configured_model` 与请求 endpoint 不能事后回填为 `actual_model`，缺失必须保持 `null` 并单独决定是否阻塞正式实验。
- 没有观测到的实际模型、镜像 ID、submit/replay 结果等字段必须保持 `null`，不能用 manifest 声明值、预期结果或事后推断补齐证据。
- 历史 manifest 的 Forge 组件哈希必须按其声明的 Git revision 读取 blob 校验；把它永久对照最新工作树，会在 stacked PR squash 合并或后续 instrumentation 后产生伪漂移。协议记录器与 Schema 仍应按当前字节校验；最小后端镜像没有 Git 时，由运行时 preflight 校验当前工作树。
- Rebase 等价不能伪装成 Git ancestry：`d845b735` 不会因为其重排版本最终 squash 到主干就成为 `9e002f45` 的祖先。历史审计必须固定原 baseline tree、审阅后的 rebased head、squash successor 和相同 successor tree，并拒绝不在该 successor ancestry 上的 head。
- 7.4 GiB WSL2 中不要并行启动前端 lint、typecheck 和 Next.js build；三个一次性 Node 容器会耗尽内存并让 WSL 服务超时。应串行执行，给每个容器设置内存/CPU 上限和独立匿名 `.next` 卷；无真实认证密钥的 CI build 使用仓库支持的 `SKIP_ENV_VALIDATION=1`。
- 一次性前端测试容器的镜像内置源码可能落后于主干；lint/typecheck/build 应只读挂载当前 `frontend/src`、`public` 和 `next.config.js`，format 还要挂载其扫描到的根级 Markdown/配置文件；使用独立 `.next`，不能在运行 `next dev` 的容器内并发构建。
- Actions checkout 默认 `fetch-depth: 1`；需要读取 manifest 固定历史 revision 的 benchmark 测试必须显式获取完整 Git 历史，否则本地完整 clone 通过而 CI 会因找不到历史路径失败。
- Compose 中只读挂载的 `/repo` 适合 runner/preflight，但 Ruff/pytest 必须关闭仓库内缓存；需要格式化时使用一次性可写 bind mount。WSL 宿主当前没有 `uv`，标准库 runner 可直接运行，依赖完整的回归测试继续在 LangGraph 开发容器中执行。
- Manifest 的 CMake/configure 参数必须确定性注入 compiler prompt，并按有序 token 子序列验证；只检查参数集合会掩盖顺序敏感的配置偏差。
- 在仓库根直接启动 Compose 会改变 project name，并可能因网络网段重叠创建失败；开发服务必须继续使用既定 `deer-flow-dev` project/启动脚本。
- Compose 开发容器只把完整仓库只读挂载到 `/repo`，而 `/app/backend` 仅是后端源码挂载；依赖仓库根资产的 pytest/Ruff 必须从 `/repo/backend` 运行，并使用 `/app/backend/.venv` 解释器、关闭仓库内缓存。
- 从大型冻结协议文件派生新版本时，单次命令输出可能被工具上限静默截断；必须分块读取并在冻结哈希前校验 JSON 解析、行数和机械替换后的完整字节相等性。
- JSON Schema 内部若使用 `#/$defs/...` 根引用，实例校验必须把完整 schema 交给 validator；直接抽出 `$defs.manifest` 会失去根定义并产生 `PointerToNowhere`，这属于校验命令错误，不是 schema 失效。
- `DeerFlowClient.stream()` 仍是同步兼容 API；任何可能调用 coroutine-only 工具的 embedded consumer 必须使用 `DeerFlowClient.astream()`，不能用阻塞包装破坏取消/终止语义。
- 冻结协议的 current-tree gate 与历史 provenance audit 目的不同；合法修改 runner 后，前者应继续拒绝漂移，后者必须从已审阅的协议提交读取冻结 blob，不能永久依赖当前工作树。
- Physical-attempt policy 已由 Issue #25 冻结 `cases[].build_system` 并校验 expected/observed identity；ledger 仍未记录有界的 agent tool failure/no-action completion，在 Issue #26 完成前仍不能把 0 submit 解释为 compiler 能力结果。
- Codex/PowerShell 对 `wsl docker exec` 的外层命令超时不保证容器内 Python 已停止；本次真实委派在外层 10 秒超时后仍继续到 clean replay。必须先检查 `docker top`、Session 终态和 label 容器，再决定是否重跑或清理，避免重复任务。
- Ledger 事件名的首段不允许下划线；`build_system.checked` 不符合 `^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*)+$`，应使用 `build.system_checked`。新增事件必须先用 recorder 的真实 append/verify 路径测试，不能只断言 mock 调用。
- 开发容器的完整仓库位于只读 `/repo`，`/app/backend` 只是可写后端挂载；benchmark 测试会从工作目录推断仓库根，因此必须从 `/repo/backend` 启动并复用 `/app/backend/.venv`。从 `/app/backend` 运行会因缺少根目录 manifest、Schema 和 Dockerfile 产生大量伪失败。
- Ruff 必须从 `/repo/backend` 启动以加载 `backend/pyproject.toml`；从 `/repo` 启动会退回默认格式规则，把原本符合仓库配置的 runner 误报为需要大范围格式化。只读挂载下同时使用 `--no-cache`。
- Tool error middleware 为继续 Agent 推理会生成包含异常详情的 `ToolMessage`，但该内容只能面向当前模型，绝不能进入实验账本。`agent.tool_failed` 必须在异常捕获点从原始异常对象提取类型名，并用专用白名单 Schema 拒绝详情、prompt、参数、stdout/stderr、secret 和宿主路径。
- `test_create_deerflow_agent.py` 仍有 17 个与当前 factory 不一致的既有 feature/sandbox/anchor 期望，例如要求已删除的 `SandboxMiddleware`；本次扩展执行得到 27 passed/17 failed，而与本次变更直接相关的 `test_always_on_error_handling` 单独通过。不要把这些旧测试失败归因于 agent evidence import，也不要在 #26 中顺手改动。
- 真实 Docker 集成依赖 GitHub clone，偶发 `Recv failure: Connection reset by peer` 可能在进入待测逻辑前失败；先确认按 label 无遗留容器，再只重跑该场景。本次副作用拒绝场景首次网络失败，单独重跑后 `1 passed in 32.63s`。
- 完整 `test_client.py` 当前有 3 个与 v4 无关的既有 artifact 路径期望不一致：测试期待 `must start with`/`PathTraversalError`，实际 `Paths.resolve_virtual_path()` 返回 `Unsupported virtual path` 的 `ValueError`；v4 扩大回归为 `431 passed, 3 skipped, 3 failed`，stream/chat 定向测试仍为 `19 passed`。不要在 benchmark 协议提交中顺手修改。
- 原生 async stream 不自动保证模型 client 的 event-loop ownership。`task_tool` 已在 Lead 的 async loop 中时，不能再通过 `thread pool -> asyncio.run()` 为 compiler 创建第二个 loop；保留同步兼容调用的隔离线程路径，并用 loop-bound 回归保护该边界。
- Windows Git 的 HTTPS push/ls-remote 可能无输出挂起，而 `gh api` 正常。回退到 Git Data API 时要以 base tree 和 changed blobs 创建单提交，比较本地/远端 tree SHA，并把本地分支 ref 对齐远端 commit；不能只验证 PR 页面可见。
