# 项目状态快照 (Project State Snapshot)

跨 Claude Code session 的项目状态流水。按 CLAUDE.md §7 维护。

## 进行中 (In Progress)
<!-- 跨 session 未完成的工作。完成后挪到「最近变更」。 -->

- 2026-08-15 — 验证 failure checkpoint 三层组合恢复
  - GitHub: 中文 Issue #141 已创建并回读；分支为 `research/141-combined-checkpoint-prototype`，基线为 `main@cd31d8df`。
  - 实现: 新增实验专用 `forge-combined-checkpoint-1.0.0` manifest，把 message、environment、budget 绑定到同一 `capture_id` 与 message state SHA-256；三层全部校验后才发布父 manifest。
  - 当前验证: 两臂同步切换 message thread/session、environment identity 与独立 budget runtime；SQLite 冷恢复不重新 capture。固定组合 manifest SHA-256 为 `bb1f6f4da5868e2e33ef1caf8c34a4645fc06641b5577669edf94f75f8449738`。
  - 证据: 聚焦测试 `10 passed`；消息/环境/预算相邻非 Docker 回归 `37 passed, 1 skipped`；Ruff check/format、`py_compile` 与 `git diff --check` 通过。
  - 边界: 0 provider、0 Docker、0 formal physical attempt、0 model token；不修改生产 Compiler、Compile Session、`_ACTIVE_EXPERIMENTS`、Oracle、clean replay 或自然任务 ITT runner。
  - 下一步: 中文提交、通过 WSL helper 推送、创建中文 PR 并等待 CI；未经新授权不合并，也不进入 provider canary 或真实实验。
  - 文件: `scripts/forge_combined_checkpoint_prototype.py`, `backend/tests/test_forge_combined_checkpoint_prototype.py`, `benchmarks/preregistrations/cpp-verifier-combined-checkpoint-prototype.md`

- 2026-08-15 — 验证 failure checkpoint 预算重建与双臂隔离
  - GitHub: 中文 Issue #139 已创建并回读；分支为 `research/139-budget-checkpoint-prototype`，基线为 `main@ffb3475c`。
  - 实现: 新增实验专用 `forge-budget-checkpoint-1.0.0` manifest、deterministic fake clock/counters 与预注册；不修改生产 `_ACTIVE_EXPERIMENTS` 或历史 evidence。
  - 当前验证: 父 manifest 固定 limits、capture 前累计成本、remaining、attempt/compiler work/total deadline 与 post-build；两臂初始 canonical budget 相同，后续五类 claim 独立，预算耗尽不阻塞 finalize/cleanup。
  - 证据: fixture manifest SHA-256 为 `7a19ec82b058587656dd3c93d7f935e274f9560cb4e0beac863f6acd88043730`；聚焦与相邻消息/环境 checkpoint 回归 `27 passed, 1 skipped`，Ruff check/format 与 `py_compile` 通过。
  - 边界: 0 provider、0 Docker、0 formal physical attempt、0 model token；下一步是中文提交、WSL helper 推送、中文 PR 与 CI，不授权组合 runner 或 mechanism slots。
  - 文件: `scripts/forge_budget_checkpoint_prototype.py`, `backend/tests/test_forge_budget_checkpoint_prototype.py`, `benchmarks/preregistrations/cpp-verifier-budget-checkpoint-prototype.md`

- 2026-08-15 — 验证 verifier failure checkpoint 的非模型分支可行性
  - GitHub: 中文 Issue #135 已创建并回读；分支为 `research/135-failure-checkpoint-prototype`，基线为 `main@1f944c8c`。
  - 实现: 从冻结 pilot Slot 7/10 派生两份脱敏只读 fixture，固定 Schema/canonical SHA-256；实验专用 fake compiler graph 使用 SQLite checkpointer，在 actionable submit 后、下一模型节点前暂停并派生 baseline/treatment。
  - 当前验证: 两臂仅 feedback ToolMessage content 与 arm/session identity 不同；SQLite 关闭重开后从 `continue_model` 恢复，capture 前 fake submit 不重复；相邻回归 `40 passed`，完整 backend Ruff check/format 通过，全程 0 provider、0 Docker、0 physical attempt。
  - 下一步: 完成中文提交、WSL helper 推送、中文 PR 与 CI；本原型不授权或实现 container rootfs/workspace 恢复。
  - 文件: `scripts/forge_failure_checkpoint_prototype.py`, `backend/tests/test_forge_failure_checkpoint_prototype.py`, `benchmarks/fixtures/failure-checkpoints/`, `benchmarks/schemas/forge-failure-checkpoint-fixture-v1.schema.json`, `benchmarks/preregistrations/cpp-verifier-failure-checkpoint-prototype.md`

- 2026-08-14 — 派生 verifier-driven repair 单次 canary amendment
  - GitHub: 中文 Issue #131 已创建并回读；分支为 `research/issue-131-verifier-repair-canary-amendment`，基线为 `main@9a63bc0a`。
  - 边界: 原失败 canary report/marker 与 authorized identity 保持不变；新 identity 使用独立 evidence 目录，只新增一次双 provider canary，成功才允许原 12 slots/6 complete pairs/2,400,000 recorded-token ceiling。
  - 实现: 新 protocol/runner/report 在 canary、attempt 和 batch 前核对旧 marker/report 的完整 SHA-256 与 0 formal ledger；模型、300 秒/0 retry、treatment、Oracle、clean replay、顺序和分析规则均继承 parent。
  - 当前验证: parent + amendment 聚焦回归 `15 passed`，Ruff check/format 与语法检查通过；canonical manifest SHA-256 为 `4ac87955e85bd7a0ed8465268ae42c2b0d2ce598bf7119c129364cba3fc87915`。
  - 下一步: 完成最终审计、中文提交/推送/PR/CI；合并后通过 Ubuntu/Compose 非模型门禁并执行唯一新 canary，双通过才运行 batch。
  - 文件: `scripts/forge_verifier_repair_canary_amendment_protocol.py`, `scripts/forge_verifier_repair_canary_amendment_runner.py`, `scripts/forge_verifier_repair_canary_amendment_report.py`, `backend/tests/test_forge_verifier_repair_canary_amendment.py`, `benchmarks/manifests/cpp-verifier-repair-pilot-canary-amendment.json`, `benchmarks/schemas/forge-verifier-repair-pilot-canary-amendment-v1.schema.json`

- 2026-08-14 — 修复 verifier-driven repair canary 冻结超时接线
  - GitHub: Issue #127 / PR #128 已完成 12-slot 授权实现；新中文 Issue #129 跟踪 canary 未应用 300 秒冻结超时，修复分支为 `fix/issue-129-canary-timeout`。
  - 真实证据: 经授权的完整 canary 中 RichLab `gpt-5.5` 4.767 秒通过，DeepSeek `deepseek-v4-flash` 在 120.246 秒以 `APITimeoutError` 失败；0 formal JSONL、0 physical attempt，12-slot batch 未启动。失败 marker/report 与此前两次操作事故 marker 均保留，未经新授权不得再次 canary。
  - 根因与修复: authorized runner 的 canary 未进入 `ExperimentPolicy`，沿用本地 120 秒配置。新 helper 在独立串行 runner 进程的模型构造临界区应用 profile 的 300 秒/0 retry，验证模型对象的有效策略后在 `finally` 恢复原配置；报告新增有效 timeout/retry 字段，不修改共享 factory、Oracle、clean replay 或历史 evidence。
  - 验证: repair 相关回归 `27 passed`，Ruff 与测试格式通过；真实无请求模型对象探针确认 RichLab/DeepSeek 的模型和 OpenAI client 均为 300 秒、0 retry，构造后本地配置恢复为 120 秒。协议组件验证通过，新 canonical manifest SHA-256 为 `ff30e38d643c211c3f2f6d33a6f9424d9410168d81ecb2c4f47ffb79e4a61875`。
  - 下一步: 完成中文提交、WSL helper 推送、中文 PR 与 CI；修复合并后只运行非模型门禁。新的 provider canary 与 12-slot batch 仍需实验负责人重新明确授权。
  - 文件: `scripts/forge_verifier_repair_authorized_runner.py`, `backend/tests/test_forge_verifier_repair_authorized.py`, `benchmarks/manifests/cpp-verifier-repair-pilot-authorized.json`, `benchmarks/schemas/forge-verifier-repair-pilot-authorized-v1.schema.json`

- 2026-08-13 — 完成 formal v4 有限诊断与新 canary amendment
  - GitHub: 中文 Issue #115 已创建并回读；实现分支为 `research/formal-v4-canary-amendment`，PR 尚未创建。
  - 授权: RichLab `gpt-5.5` 与 DeepSeek `deepseek-v4-flash` 各最多 2 次低成本诊断，首次成功即停止；之后最多 1 次新的双 provider canary，成功才执行原六槽，token 上限仍为 980,000。
  - 实现: 新 manifest/Schema/protocol/runner/report 使用独立诊断和 formal evidence 目录；诊断以 append-only started/terminal 文件计次，不保存响应正文、请求头、凭据或网络标识；新路径禁止匿名 `/models` preflight。
  - 历史边界: 旧 authorized manifest canonical SHA-256、失败 marker SHA-256、`failed` / `RunnerError`、0 provider report 与 0 formal ledger 均在每个后续门禁重新校验，旧文件不修改。
  - 当前验证: canonical SHA-256 为 `e296138d6464adc6e7c12d4ee29d1f22c178d53a463b3467e2d2442e5fd66587`；聚焦测试 `22 passed`、formal v1-v4 扩大回归 `205 passed`，Ruff、format、`py_compile`、Schema、确定性再生成、父文件/旧 marker、敏感信息、Ubuntu 原生 daemon 与 0 formal 残留容器审计通过。
  - 下一步: 完成本地验证和文档审计后中文提交、WSL helper 推送、中文 PR；主干合并后运行真实诊断，新 canary 失败立即停止，成功才执行六槽。

- 2026-08-12 — 执行 formal v4 首批完整 `cppitertools` project block
  - GitHub: Issue #111 / PR #112 已 squash 合并为 `main@05e9fdbd`，Issue 自动关闭；PR 与主干的 backend unit tests、backend lint、frontend lint 全绿。
  - 授权: 原 schedule order `1, 2, 73, 74, 153, 154`，双 condition 各三次，共 6 attempts；maximum recorded tokens 为 980,000，禁止 retry、fallback、replacement、backfill 和 v3 slot 8-10。
  - 实现: 新 authorized manifest/Schema/protocol/runner/report 保留完整 180-slot identity，只投影六槽执行；一次性 canary marker 在成功或失败后都消耗机会，首条 ledger 前要求空目录和 0 formal 残留容器。
  - 当前验证: canonical SHA-256 为 `8f05820d97054d16cc0cf1ee5646089ccf8f5c9c56108f2781ec45a70c7ccf03`；聚焦 `26 passed`、formal v1-v4 扩大回归 `221 passed`，Ruff、确定性再生成、父候选哈希、Ubuntu gate、主干 CI 和非模型 preflight 通过。
  - 当前阻塞: 唯一双 provider canary 在模型调用前被 endpoint preflight 拒绝，marker 已以 `RunnerError` 失败终结；0 provider report、0 formal ledger、0 residual container，六槽采集没有开始且不得直接重试。
  - 下一步: 等待实验负责人确认当前网络接入介质，并决定是否授权只读 endpoint 诊断和新的 canary amendment；获得确认后必须另建中文 Issue/PR 和协议 identity，保留当前失败 marker。

## 最近变更 (Recent Changes)
<!-- 倒序，最新在上。 -->

- 2026-08-31 — 完成 Issue #232/#233 六 case 确认性 lifecycle 零 provider 门禁
  - 文件: `scripts/forge_opaque_provenance_confirmatory_lifecycle_gate.py`, `scripts/forge_opaque_provenance_confirmatory_candidate_v2_protocol.py`, `backend/tests/test_forge_opaque_provenance_confirmatory_lifecycle_gate.py`, `backend/tests/test_forge_opaque_provenance_confirmatory_lifecycle_gate_docker.py`, `backend/tests/test_forge_opaque_provenance_confirmatory_candidate_v2.py`, `benchmarks/manifests/cpp-opaque-provenance-confirmatory-candidate-v2.json`, `benchmarks/schemas/forge-opaque-provenance-confirmatory-candidate-v2.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-candidate-v2.md`, `benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-lifecycle-zero-provider-gate.md`
  - 根因: `sql-parser-shared` 的 v1 空 bootstrap 会因 checkout 文件 mtime 决定 `make library` 是消费已跟踪生成文件还是重新运行 Bison；四次 lifecycle 为 2 次通过、2 次 `sha256_mismatch`，路径、类型和大小一致但 SHA-256/build-id 不同。
  - 修复: v2 只显式冻结 `cd src/parser && bison bison_parser.y --output=bison_parser.cpp --defines=bison_parser.h --verbose`；parent 在独立 subshell 执行 bootstrap，避免改变后续 Make 工作目录。v1 protocol 保持逐字不变，12-pair schedule identity 保持 `3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134`。
  - 验证: 固定镜像 `sha256:900d7ce4b902b79df5c64ffab88631b251538f1bde578c4dd2bf91558e9d1554`；`sql-parser-shared` 稳定性门禁连续两次通过，最终六 case lifecycle `6 passed in 453.74s`，相邻回归 `115 passed, 6 skipped`，最终聚焦 `25 passed, 6 skipped`；Ruff、pycompile、确定性再生成、diff 与后置 0 orphan 均通过。
  - 边界: 0 provider、0 credential read、0 checkpoint、0 formal attempt、0 model token、0 正式 evidence write；Issue #232 已记录 v1 失败和停止决策，Issue #233 跟踪唯一修正，尚未授权 provider runner 或 12-pair 采集。

- 2026-08-31 — 冻结 Issue #230 opaque provenance 六 case 确认性 pilot 候选协议
  - 文件: `scripts/forge_opaque_provenance_confirmatory_candidate_protocol.py`, `backend/tests/test_forge_opaque_provenance_confirmatory_candidate.py`, `benchmarks/manifests/cpp-opaque-provenance-confirmatory-candidate.json`, `benchmarks/schemas/forge-opaque-provenance-confirmatory-candidate.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-candidate.md`
  - 实现: result-blind 冻结 CMake `pupnp/ada-url/args` 与 Make `gpac/fio/sql-parser-shared`，每 case 两个 replicate 且项目内对调 arm order；`sql-parser` 使用独立 shared-library oracle，不修改旧 formal protocol。
  - 排除: `mruby` 的 Rake/submodule 混杂、已有模型 evidence 的 `janet`、smoke 无判别力的 `lodepng` 与错误的 `sql-parser-static` identity 均由静态合同拒绝。
  - 验证: schedule identity 为 `3f35dd8c245cb7e9db6069f63cf133c98fbfdf6813a11e3fa2306a5eb34c2134`；聚焦与相邻回归 `60 passed`，Ruff check/format、pycompile、确定性再生成、diff 与敏感信息扫描通过。全阶段 0 provider、0 credential read、0 Docker、0 formal attempt、0 model token、0 evidence write。

- 2026-08-31 — 实现 Issue #228 OpenH264 单配对只读结果审计
  - 文件: `scripts/forge_opaque_provenance_openh264_result_audit.py`, `backend/tests/test_forge_opaque_provenance_openh264_result_audit.py`
  - 实现: 固定现有 12 个 source evidence SHA-256，验证 reachability、dependency fixture、pair marker 与 parent/baseline/treatment 三条 ledger hash chain；从 ledger 恢复两臂 request/token、R0 companion 和动作预算，并区分 treatment report-time head 与 terminal head。
  - 验证: 真实 evidence 只读 audit 通过，恢复 baseline `4/0/0/0` 与 7 个 R0、treatment `4/1/0/1` 与 3 个 R0；聚焦及 #210/#220/#226 相邻回归 `28 passed`，Ruff、format 和 pycompile 通过。合并后 create-once 写入 `reports/audit-v1.json`，SHA-256 为 `0671efefbea9744e44ee8bd64dc02b2feb827d6eee1696f78e527cb46638c7e2`，原 12 个 source evidence 哈希不变；审计阶段 0 provider、0 credential read、0 Docker、0 formal attempt、0 model token。

- 2026-08-31 — 发布并执行 Issue #226 OpenH264 provenance 单配对 amendment
  - 文件: `scripts/forge_opaque_provenance_openh264_execution_protocol.py`, `scripts/forge_opaque_provenance_openh264_execution_runner.py`, `backend/tests/test_forge_opaque_provenance_openh264_execution.py`, `benchmarks/manifests/cpp-opaque-provenance-openh264-execution.json`, `benchmarks/schemas/forge-opaque-provenance-openh264-execution.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-openh264-execution.md`
  - 发布: PR #227 已 squash 合并为 `main@9873e7a8548a698e03fc4d9f3cf19123ffeb8070`，Issue #226 自动关闭，三项 CI 全绿。
  - 结果: `deepseek-v4-flash` reachability 以 1 request / 17 tokens / 1.369 秒通过；唯一 pair 中 baseline 为 8 requests / 37,271 tokens / 0 submit / `unproven/opaque_wrapper`，treatment 为 6 requests / 20,584 tokens / 1 submit / 1 clean replay / `proven/direct_make`，总计 57,872 tokens。
  - 清理: production 与 dependency fixture cleanup 均通过，compile/replay/prep container、fixture tag 与真实 image ID 后置均为 0；禁止重跑、replacement、backfill、追加 pair、历史池化、p 值和模型排名。

- 2026-08-31 — 完成 Issue #224 OpenH264 独立 Make candidate 与真实 lifecycle 门禁
  - 文件: `scripts/forge_opaque_provenance_openh264_candidate_gate.py`, `backend/tests/test_forge_opaque_provenance_openh264_candidate.py`, `backend/tests/test_forge_opaque_provenance_openh264_candidate_docker.py`, `benchmarks/manifests/cpp-opaque-provenance-openh264-candidate.json`, `benchmarks/schemas/forge-opaque-provenance-openh264-candidate.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-openh264-candidate.md`
  - 选择: result-blind 审计从冻结 source protocol 选定 `openh264@4a2615fac570c6ca1ed4f157b9fdab9466edfd80`；历史真实 ledger/report 匹配均为 0，固定提交无 submodule，根 `Makefile` 与 OSS-Fuzz 都直接构建 `libopenh264.a`。`sql-parser` 因 `.a` 还需 `static=yes`、`lodepng` 因 OSS-Fuzz 绕过 Make 暂不使用。
  - 实现: 新 candidate 复用 R3 action parser、#220 组合 bindings 与 #222 完整 agent construction；OpenH264 policy 精确允许 direct Make、jobs 省略或 `1..2`、独立 stage，并拒绝无界/超限/target drift。Manifest canonical SHA-256 为 `ab29737969549ddf3d309fb2868a0254b8a346842cc1e168d7e475d123f4e0d6`，全部 provider/checkpoint/pair/evidence write 授权关闭。
  - lifecycle: 基础 `autocompiler:gcc13` 缺少 `nasm`，opt-in gate 以固定 URL/SHA-256 的 `nasm 2.16.01-1build1` 小包临时派生 image；parent `unproven/opaque_wrapper`、baseline 同源失败、treatment `proven/direct_make`、candidate verification 与 clean replay 全部通过，真实 Docker 为 `1 passed in 412.14s`，后置 compile/replay/continuation/Issue #224 image orphan 均为 0。
  - 验证: 聚焦 `6 passed`、Make/R3/#220/#222 相邻回归 `88 passed`，Ruff check/format、pycompile、CLI、Schema、diff 与敏感信息扫描通过。全阶段 0 provider、0 credential read、0 formal evidence write、0 model token；未创建 checkpoint 或 behavioral pair。

- 2026-08-30 — 完成 Issue #222 R3 Make 完整 agent construction 零 provider 门禁
  - 文件: `scripts/forge_opaque_provenance_r3_make_agent_construction_gate.py`, `backend/tests/test_forge_opaque_provenance_r3_make_agent_construction_gate.py`
  - 实现: 直接消费 #220 组合 bindings，用项目既有 `BaseChatModel.bind_tools()` fake model 真实构造 `create_agent + ThreadState + InMemorySaver`，接入 R3 adapter、R0 registry、`SerialToolCallMiddleware` 与真实 LLM/tool-error middleware；checkpoint 状态固定为 Human/AI submit/Tool failure 三消息。
  - 结果: 恢复后恰好 1 次 fake model request，ledger 为 1 started / 1 completed / 0 failed / 0 cancelled，2 个工具绑定且 `parallel_tool_calls=false`，最终四消息；动作预算全 0，active experiment 已释放。注入的 pre-model `AttributeError` 正确归为 `pre_model_execution_error/mechanism_invalid`，fake cleanup 证明 parent/baseline/treatment 全部先 deactivate 再 cleanup。
  - 验证: 聚焦 `6 passed`、R1/R3/R0/runtime-parity/LLM middleware 相邻回归 `59 passed`；CLI validate、Ruff check/format、pycompile、diff 与敏感信息扫描通过。临时 ledger 自动删除，全程 0 provider、0 credential read、0 Docker、0 formal evidence write、0 model token、0 checkpoint/pair。
  - 边界: 中文 Issue #222 已创建并回读；本 gate 只关闭真实 agent construction 与首请求可达性，不重跑 #218，也不授权新的 Make checkpoint、replacement、backfill 或模型实验。

- 2026-08-30 — 审计 R3 Make 机制无效终态并实现 Issue #220 执行安全门禁
  - 文件: `scripts/forge_opaque_provenance_r3_make_execution_failure_gate.py`, `backend/tests/test_forge_opaque_provenance_r3_make_execution_failure_gate.py`
  - 终态: #218 唯一 reachability 以 1 request / 17 recorded tokens / 1.475 秒通过；唯一 pair 在模型请求前因 R3 runtime binding 缺少 `RejectionObservationRegistry`、`FrozenActionPolicy` 与 `SerialToolCallMiddleware` 失败，两臂均为 0 request / 0 submit / 0 replay，pair marker 为 `failed/EvidenceError`，不能形成 paired estimand。
  - 根因链: registry 在受保护 `try/finally` 前构造，`AttributeError` 泄漏 active experiment；旧 classifier 把零请求异常误记为 `no_submit`；cleanup 随后向 completed ledger 追加 `before_cleanup` event，被 immutability gate 阻断。三个退出容器与本 capture continuation image 已按精确 identity 人工删除，0 compile/replay orphan。
  - 修复: 新版本化门禁正确组合 R3 action adapter 与 R0 registry/middleware，零请求异常 fail-closed 为 `pre_model_execution_error / mechanism_invalid` 并持久化 error class，cleanup 前机械解除 parent/baseline/treatment experiment context；不修改 #216/#218 冻结组件或 evidence。
  - Evidence: `reports/failure-audit-v1.json` create-once sidecar SHA-256 为 `2cf698346b0a1a319c274e220fca6c2fd798a78cdcf1dbbdb5393298af681010`；8 个输入哈希、3 个冻结组件哈希和三条 ledger hash chain 通过。聚焦/相邻回归 `25 passed`，Ruff check/format 与敏感信息扫描通过。
  - 边界: 中文 Issue #220 已创建并回读；禁止重跑、retry、replacement、backfill、历史池化或模型排名。本修复阶段 0 provider、0 credential read、0 Docker execution、0 model token。

- 2026-08-30 — 发布并执行 Issue #218 R3 Make 单配对 execution amendment
  - 文件: `scripts/forge_opaque_provenance_r3_make_execution_protocol.py`, `scripts/forge_opaque_provenance_r3_make_execution_runner.py`, `backend/tests/test_forge_opaque_provenance_r3_make_execution.py`, `benchmarks/manifests/cpp-opaque-provenance-r3-make-execution.json`, `benchmarks/schemas/forge-opaque-provenance-r3-make-execution.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-r3-make-execution.md`
  - 协议: 授权 DeepSeek `deepseek-v4-flash` 一次 reachability 与成功后的一个 baseline→treatment pair；300 秒、0 retry、每臂最多 8 requests/8 turns/24 graph steps/120,000 recorded tokens，阶段上限 245,000，禁止 replacement/backfill/extension。
  - Runner: 从冻结 #208 runner 做版本化机械派生，只替换 protocol、R3 action/R0 adapter、输出目录、marker/ledger/checkpoint/report identity，并同时记录 R3 experiment case ID 与底层 P2 reference case ID；差异归一化后与父 runner 字节相等。
  - 验证: canonical manifest SHA-256 为 `e2335b9e180ff539752dbb6b9d049da561980b0af7a64a193b49ab423913e86f`；聚焦 `8 passed`、Make/R0/R3 相邻 `117 passed, 3 skipped`，Ruff check/format、pycompile、CLI、Schema、diff、冻结哈希与敏感信息扫描通过。
  - 发布: 中文 PR #219 三项 CI 全绿后 squash 合并为 `main@7ab7791f1445070e455cded76c080ccf2b972cd6`。真实 preflight 确认 Ubuntu-native Docker、Wi-Fi、发布身份、空 evidence、0 orphan 与凭据仅存在性后运行唯一 reachability/pair；pair 的机制无效终态由 Issue #220 跟踪，禁止直接重跑。

- 2026-08-30 — 完成 Issue #216 R3 Make 单配对未执行候选与零 provider runtime 门禁
  - 文件: `scripts/forge_opaque_provenance_r3_make_candidate_protocol.py`, `scripts/forge_opaque_provenance_r3_make_candidate_runner.py`, `backend/tests/test_forge_opaque_provenance_r3_make_candidate.py`, `benchmarks/manifests/cpp-opaque-provenance-r3-make-candidate.json`, `benchmarks/schemas/forge-opaque-provenance-r3-make-candidate.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-r3-make-candidate.md`
  - 实现: 从冻结 #208 R2 identity 派生全新 R3 candidate，保持 hoextdown case、九字段 repair packet、baseline→treatment、state matching 与 245,000 token ceiling，但关闭 checkpoint/provider/credential/Docker/pair/evidence 等全部执行授权；repair packet 仍是唯一 treatment exposure。
  - Runtime: 同一 adapter 接受 jobs 省略、`-j1` 与 `--jobs=2`，拒绝无界、0 和超过 2 并保留独立 R0 分类；只提供 validate/plan/只读 Git preflight，三个 execute 入口均 fail-closed。
  - 验证: canonical manifest SHA-256 为 `e45c9a5cfbba70d30ee2c82a68631a3430ea3e66748d808888660cae5c105d7b`，evidence identity 为 `17bf1a758d953f4e0c579039c97c8a3e669caf92ca720f93b3edfe29116c9890`；聚焦 `6 passed`、Make/R0/R3 相邻 `109 passed, 3 skipped`，Ruff check/format、py_compile、CLI 与敏感信息扫描通过。
  - 边界: 0 provider、0 credential read、0 Docker、0 checkpoint、0 formal attempt、0 model token、0 evidence write；中文 Issue #216 / PR #217 已合并为 `main@4190ad433bf015e93b68fdefc4eb8de8b11c25a2`。合并后 release preflight 通过：工作区干净、9 个父组件哈希一致、evidence 0 条且 checkpoint 为 `not_created`。

- 2026-08-30 — 完成 Issue #214 R3 Make jobs 真实 lifecycle 本地门禁
  - 文件: `scripts/forge_opaque_provenance_r3_make_lifecycle_gate.py`, `backend/tests/test_forge_opaque_provenance_r3_make_lifecycle_gate.py`, `backend/tests/test_forge_opaque_provenance_r3_make_lifecycle_gate_docker.py`, `benchmarks/preregistrations/cpp-opaque-provenance-r3-make-lifecycle-zero-provider-gate.md`
  - 实现: 新版本 adapter 复用并固定 #204 Docker orchestration 哈希，分别暴露 `make libhoedown.a` 与 `make -j1 libhoedown.a`；不修改 #202/#204/#208/#210/#212 或冻结 evidence。
  - 结论: 两个 profile 均在 Ubuntu WSL2 原生 Docker production Compile Session 中把 Make P2 从 `unproven/opaque_wrapper` 转为 `proven/direct_make`，且 candidate verification、唯一 clean replay、R0 分类与 cleanup 全部通过；后置 compile/replay/capture orphan 均为 0。
  - 验证: 真实 Docker `2 passed in 156.30s`，相邻回归 `86 passed`，静态聚焦 `4 passed`，Ruff check/format、`py_compile`、`git diff --check` 与敏感信息扫描通过。
  - 边界: 0 provider、0 credential read、0 formal physical attempt、0 model token、0正式 evidence write；本地 SQLite checkpointer 仅用于 #204 双臂同源恢复。中文 Issue #214 / PR #215 已合并为 `main@e58ef0f0e7d5968667dc0c0ce586834251daeac1`。

- 2026-08-30 — 完成 Issue #212 R3 Make 构造对齐零 provider 门禁
  - 文件: `scripts/forge_opaque_provenance_r3_make_construct_alignment_gate.py`, `backend/tests/test_forge_opaque_provenance_r3_make_construct_alignment_gate.py`, `benchmarks/preregistrations/cpp-opaque-provenance-r3-make-construct-alignment-gate.md`
  - 发布: 中文 Issue #212 / PR #213 已创建并回读；提交 `6e0ff544`，CI backend tests（3 分 58 秒）、backend lint（14 秒）与 frontend lint（1 分 37 秒）全绿。
  - 结论: #202 P2 不要求固定 jobs；#208 runtime 的 jobs=`2` 与未公开 stage 约束构成 intervention under-specification 风险。新 experiment-only gate 把 jobs 归为公开的有界资源策略，允许省略或 `1..2`，并让双臂共享 direct Make、directory、target、jobs 与 stage source/destination 契约。
  - 完整性: Repair packet 保持 #208 九字段内容不变且仍是唯一 treatment exposure；8 个冻结组件与 #210 真实 evidence 只读 audit 均无漂移。聚焦 `16 passed`、相邻 `73 passed`、完整有效集合 `2408 passed, 47 skipped, 1 deselected`。
  - 边界: 0 provider、0 credential read、0 Docker、0 checkpoint、0 formal attempt、0 model token、0 evidence write；不修改或重跑 #208/#210。下一阶段才另建真实 Docker lifecycle identity 候选，本 Issue 不授权模型实验。

- 2026-08-30 — 完成 Issue #210 R2 Make 结果审计 sidecar
  - 文件: `scripts/forge_opaque_provenance_r2_make_result_audit.py`, `backend/tests/test_forge_opaque_provenance_r2_make_result_audit.py`
  - 发布: 中文 Issue #210 / PR #211 三项 CI 全绿后 squash 合并为 `main@62a76d2f4f293730652f4722530390c026c19516`。
  - 审计: 从 hash-chain 完整的 parent/baseline/treatment ledger 恢复 baseline action 全 0、treatment inspection=4 与 R0 5/5 companion；paired primary estimand 固定为 `not_estimable / baseline_endpoint_censored`，treatment 为 `observed_no_conversion`。
  - Sidecar: 只 create-once 写入 `reports/audit-v1.json`，SHA-256 为 `35fb5c0c045dcd4fa61913e5089066f1ce1716ef2de50797908b6bad12824cf0`；evidence 从 9 个文件增为恰好 10 个，原 canary、marker 和 ledger 哈希全部不变。
  - 边界: 禁止池化、p 值、模型排名、重跑、replacement 或 backfill；后续审计只读，不再修改 #208 evidence。

- 2026-08-30 — 完成 Issue #208 R2 Make runtime-parity 一次性执行
  - 文件: `scripts/forge_opaque_provenance_make_runtime_parity_gate.py`, `scripts/forge_opaque_provenance_make_rejection_observability_gate.py`, `scripts/forge_opaque_provenance_r2_make_execution_protocol.py`, `scripts/forge_opaque_provenance_r2_make_execution_runner.py`, `benchmarks/manifests/cpp-opaque-provenance-r2-make-execution.json`
  - 发布: 中文 Issue #208 / PR #209 已完成，三项 CI 全绿后 squash 合并为 `main@00726aef99e331a1d2719cb26986fa15e90fe547`；manifest canonical SHA-256 为 `113192d509b3c15762f8055cb32fc9364a4a4be6bede1eeed838e540a025224e`。
  - Reachability: Wi-Fi、DeepSeek `deepseek-v4-flash`，1 request / 17 tokens / 1.481 秒通过，实际模型匹配，0 retry、无 fallback。
  - Pair: baseline 首次请求在 300 秒后 endpoint-censored，0 tokens/submit/replay、P2 unproven；treatment 8 requests / 38,780 tokens 后达到 graph-step limit，0 submit/replay、P2 仍 `unproven/opaque_wrapper`。总计 38,797 tokens。
  - 完整性: pair marker passed、结构上双臂完整、cleanup 成功，0 compile/replay orphan；parent/baseline/treatment ledger 为 7/7/44 events 且 hash chain 通过。Treatment 有 5 个 classified rejection 与 5 个 R0 companion。
  - 边界: baseline censoring 使 paired primary estimand 不可估计；treatment 是有效的 no-conversion 描述结果。禁止 retry、replacement、backfill、历史池化、p 值或模型排名。原 report 汇总 null 缺口由 Issue #210 只读 sidecar 跟踪。

- 2026-08-30 — 完成 Issue #204 R2 Make provenance 真实 lifecycle 零 provider 门禁
  - 文件: `scripts/forge_opaque_provenance_make_lifecycle_gate.py`, `backend/tests/test_forge_opaque_provenance_make_lifecycle_gate.py`, `backend/tests/test_forge_opaque_provenance_make_lifecycle_gate_docker.py`, `benchmarks/preregistrations/cpp-opaque-provenance-make-lifecycle-zero-provider-gate.md`
  - 发布: 中文 Issue #204 / PR #205 已完成，三项 CI 全绿后 squash 合并为 `main@b8092e6f58830690359b137b32031d3cc96361dc`；合并后静态 gate 通过，未重复真实 Docker gate。
  - 真实门禁: Ubuntu-native Docker `1 passed in 77.16s`。Parent 真实生成 `libhoedown.a` 且只触发 `build_system_unproven`，post-build fence 释放；baseline 保持 0 replay，treatment append direct Make + stage 后转为 `proven/direct_make`，candidate 与 clean replay 通过。
  - 完整性: 双臂 continuation image、workspace/artifact、parent history 与 budget canonical 同源，repair packet 是唯一 exposure；cleanup 后 parent/双臂/replay/checkpoint 为 0 orphan。固定 0 provider、0 credential read、0 formal attempt、0 model token、0正式 evidence write。
  - 下一步: 先冻结单 pair 未执行候选，不直接调用 provider；真实 reachability/pair 必须使用独立 execution amendment。

- 2026-08-30 — 完成 Issue #202 R2 Make provenance reference gate
  - 文件: `scripts/forge_opaque_provenance_make_reference_gate.py`, `backend/tests/test_forge_opaque_provenance_make_reference_gate.py`, `benchmarks/preregistrations/cpp-opaque-provenance-make-reference-gate.md`
  - 发布: 中文 Issue #202 / PR #203 已完成，三项 CI 全绿后 squash 合并为 `main@9b5448ed665ee5fbf614ab25f2fcb22f847c4bb4`；合并后干净主干静态 gate 通过。
  - 实现: 从 result-blind formal v1 source protocol 冻结 `hoextdown@1ef9a719`、Make target/artifact `libhoedown.a`；direct `make/gmake` 只在 effective directory、单 target、允许的 jobs 参数和 artifact producer identity 全部一致时转为 `proven/direct_make`。
  - Fail closed: opaque wrapper、变量赋值、额外 target、未知选项、失败 producer 与 run/artifact identity drift 均拒绝；冻结 CMake evaluator 保持逐字不变。
  - 边界: 聚焦及相邻 CMake lifecycle 静态回归 `69 passed`；固定 0 provider、0 credential read、0 Docker、0 checkpoint、0 formal attempt、0 model token、0 evidence write。下一阶段单独验证真实 Make fault purity、candidate/replay 与 cleanup。

- 2026-08-30 — 完成 Issue #200 R1 yyjson 独立 checkpoint 单配对实验
  - 文件: `scripts/forge_opaque_provenance_r1_execution_protocol.py`, `scripts/forge_opaque_provenance_r1_execution_runner.py`, `backend/tests/test_forge_opaque_provenance_r1_execution.py`, `benchmarks/manifests/cpp-opaque-provenance-r1-execution.json`, `benchmarks/schemas/forge-opaque-provenance-r1-execution.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-r1-execution.md`
  - 发布: 中文 Issue #200 / PR #201 已完成，三项 CI 全绿后 squash 合并为 `main@201b00780b2c85751bacc477c6ca1c31a2dec809`；manifest canonical SHA-256 为 `bc4149b8f14c5f29ec56d7d70568200d72cfe8a40a56dd49c80ef9ca092dc079`。
  - 结果: 唯一 DeepSeek reachability 以 17 tokens、1.582 秒通过；baseline 为 8 requests / 30,753 tokens / 0 submit / P2 unproven，treatment 为 6 requests / 19,555 tokens / 1 submit，candidate 与 clean replay 通过并转为 `proven/direct_cmake`。
  - 完整性: 总计 50,325 recorded tokens；R0 companion baseline 7/7、treatment 3/3，cleanup 成功，0 container/image orphan，evidence hash chain 和敏感值扫描通过；结果已回帖 Issue #200。
  - 解释边界: 与 #190 CMake pair 方向一致但不能池化、估计 treatment effect 或排名模型；下一步优先验证跨构建系统的 Make provenance reference criterion。

- 2026-08-30 — 完成 Issue #198 R1 yyjson 独立 checkpoint 真实 Docker 零 provider 门禁
  - 文件: `scripts/forge_opaque_provenance_r1_checkpoint_gate.py`, `backend/tests/test_forge_opaque_provenance_r1_checkpoint_gate.py`, `backend/tests/test_forge_opaque_provenance_r1_checkpoint_gate_docker.py`, `benchmarks/preregistrations/cpp-opaque-provenance-r1-checkpoint-zero-provider-gate.md`
  - 实现: 新 adapter 逐字段继承 #196 yyjson identity，使用可 replay 但不证明 CMake identity 的 opaque `sh -c` parent；静态合同同时冻结 repair packet、P2 append-only future treatment 和 #194 R0 companion observability。
  - 真实门禁: Ubuntu-native Docker gate `1 passed in 64.56s`；真实 `libyyjson.a` static archive 只因 `build_system_unproven / opaque_wrapper` 失败，bound submit 后 post-build fence 三字段释放，candidate failed、replay not_run；message/environment/budget 双臂 canonical 同源，repair packet 是唯一 treatment exposure。
  - Cleanup: parent/双臂 Compile Session、checkpoint helper、continuation image 和 snapshot 全部清理；capture label、`deerflow-compile-*`、`deerflow-replay-*` 与 continuation image 均为 0 orphan，#196 candidate evidence 目录仍不存在。
  - 验证: 静态聚焦 `11 passed`，R1/R0/runtime-parity/real-lifecycle 相邻回归 `70 passed`；Ruff、format、语法和 diff 通过。固定 0 provider、0 formal attempt、0 model token、0 credential read、0 candidate evidence write。
  - 踩坑: 首次 gate 的 parent policy 同时要求依赖与 CMake 参数可观察，opaque wrapper 因而额外产生 `dependency_setup_not_observed` 和 configuration 次级分类；cleanup 正常闭合。修复将 ExperimentPolicy 收敛为只隔离 provenance fault，source 参数仍由 candidate 与真实 parent command 冻结，replacement gate 通过。
  - 下一步: 中文提交、WSL helper 推送、中文 PR/CI/合并；合并后从干净主干重跑静态 gate，不重复真实 Docker gate。随后才能设计一次 reachability + 单 pair execution amendment。

- 2026-08-30 — 冻结 Issue #196 opaque provenance R1 独立 checkpoint 未授权候选
  - 文件: `scripts/forge_opaque_provenance_r1_candidate_protocol.py`, `scripts/forge_opaque_provenance_r1_candidate_runner.py`, `backend/tests/test_forge_opaque_provenance_r1_candidate.py`, `benchmarks/manifests/cpp-opaque-provenance-r1-checkpoint-candidate.json`, `benchmarks/schemas/forge-opaque-provenance-r1-checkpoint-candidate.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-r1-checkpoint-candidate.md`
  - Case: 从 result-blind `cpp-formal-v1-cases.json` 逐字段冻结 `yyjson@9365ddc7`、CMake target `yyjson` 与 `libyyjson.a` static-library oracle；repository、commit、target 和 staged artifact 均不同于 #190 `cppitertools` exploratory pair。
  - 机制: 保持原 repair packet Schema、4/2/2/2 原子动作预算、300 秒/0 retry、state-matched 双臂以及 candidate/replay/cleanup；未来 classified rejection 必须记录 #194 `agent.tool_rejection_observed` companion event。
  - 边界: checkpoint/evidence 固定为 `not_created`，只开放 `validate/plan/preflight`；provider、credential、model、Docker、checkpoint/pair execute 与 evidence write 机械关闭，新增 evidence 目录未创建。
  - 验证: manifest canonical SHA-256 为 `b89e63c4362befcdc409c60fe0334c1e9e4f62a26e369d55b676f23c1ffd202b`，evidence identity 为 `d4b5f051bde5c66e5a1b4c67da72c91443d15c614b209941f71d7a02c4f57077`；聚焦 `19 passed`，路线 P/R0/formal source 相邻回归 `156 passed, 1 deselected`，Ruff、format、语法、确定性再生成、diff 与敏感信息审计通过。
  - 下一步: 中文提交并通过 WSL helper 推送，创建中文 PR、等待三项 CI 后合并；合并后只运行一次干净主干的纯快照 preflight，真实 checkpoint 或 provider 请求必须另建 execution amendment。

- 2026-08-30 — 实现 Issue #194 runtime-parity 拒绝原因零 provider 可观测性门禁
  - 文件: `backend/packages/harness/deerflow/compile/evidence.py`, `backend/packages/harness/deerflow/agents/middlewares/llm_error_handling_middleware.py`, `scripts/forge_opaque_provenance_rejection_observability_gate.py`, `backend/tests/test_experiment_evidence.py`, `backend/tests/test_llm_error_handling_middleware.py`, `backend/tests/test_forge_opaque_provenance_rejection_observability_gate.py`, `benchmarks/preregistrations/cpp-opaque-provenance-rejection-observability-gate.md`
  - 动机: #192 只能观察 exception class，无法从 #190 冻结 evidence 逐条区分 runtime-parity 拒绝；R0 在不记录原始命令、错误文本或模型正文的前提下补齐下一轮 trajectory 所需的有界字段。
  - 实现: 历史 `agent.tool_failed` 严格保留七字段 Schema；#194 版本化 registry 仅在稳定拒绝分类与唯一 tool-call origin 同时存在时追加 `agent.tool_rejection_observed` companion event，原子包含 `failure_id`、`rejection_classification`、`action_kind`、`model_request_id`、`tool_ordinal`、`command_sha256`。未知或重复 ID 只保留旧事件，模型正文与参数不持久化。
  - 版本边界: #186 runtime-parity gate 以及共享 `evidence.py`/LLM middleware 均被历史 manifest 按字节冻结，不能原地增加异常属性或 Schema；#194 改为独立 `ObservableRuntimeParityToolAdapter + RejectionObservationRegistry`，并恢复所有冻结共享文件逐字零差异。
  - 验证: 聚焦与路线 P 相邻非 Docker 回归 `122 passed, 1 deselected`；父/baseline/treatment 历史 ledger 分别 7/42/25 events，均通过当前 `ExperimentLedger.open()` 且读取前后 SHA-256 不变。首轮 CI 暴露 10 个共享 `evidence.py` blob drift 后改为 companion 方案；修复后需重跑完整 CI。CLI 固定 0 provider、0 formal attempt、0 model token、0 Docker、0 credential read、0 frozen evidence write。
  - 下一步: 完成中文提交、WSL helper 推送、中文 PR/CI/合并；合并后从干净主干重跑 R0，再进入独立 R1 checkpoint 的未授权候选协议，不直接调用 provider。

- 2026-08-30 — 完成 Issue #192 runtime-parity 单 pair trajectory 只读分析
  - 范围: 只读核对 #190 冻结 ledger、双臂 Compile Session、message checkpoint 与 canary report；0 provider、0 Docker、0 evidence write，未读取 credential，也未修改 production、gate、runner 或 manifest。
  - 同源性: 双臂共享同一 neutral checkpoint、HumanMessage 与失败 submit payload；treatment 唯一额外 exposure 是白名单 repair packet，给出 CMake/build-dir/target/proof status 和抽象 repair goal，不提供完整命令。
  - Trajectory: baseline 8 requests、4 个成功 inspection、8 个 tool failure，最终 graph-step limit；treatment 首次 tool call 被拒后，用 1 inspection + 1 direct CMake build 触发 automatic submit，candidate/replay/P2 conversion 通过。
  - 效率: baseline 输入/输出/总 tokens 为 36,826/1,776/38,602，模型请求累计延迟 16.743293 秒；treatment 为 6,926/313/7,239 和 3.246708 秒，相当于 baseline 的 18.75% tokens、37.5% 请求和 19.39% 模型延迟。
  - 可识别边界: baseline ledger 精确记录 7 个 `RuntimeParityGateError` 和 1 个 `EvidenceError`，但失败事件没有保存 bounded rejection classification、命令摘要或模型请求内 tool ordinal；因此不能从冻结 evidence 把每次拒绝可靠拆成 inspection budget exhausted、compound shell 与非法 command role，也不能事后猜测。
  - 额外发现: 虽然 model binding 固定 `parallel_tool_calls=false`，baseline 的单次模型响应仍出现多个 tool attempts；现有 ledger 只能证明响应多调用，不能证明实际并发。原子 action claim 阻止了预算超额，但下一轮必须显式记录 request/tool ordinal。
  - 决策: 有条件进入 replication。先做 0-provider observability gate；通过后只执行 1 个新 independent-checkpoint canary，再预注册最多 6 个独立 CMake checkpoint pair。#190 不重跑、不进入 confirmatory pool；主要 outcome 仍是 paired P2 conversion + candidate/replay，tokens/actions 仅为次要指标。
  - GitHub: 中文 Issue #192 已创建并回读。
  - 文件: `.claude/memory/project.md`

- 2026-08-30 — 实现 Issue #190 runtime-parity 一次性 execution amendment
  - GitHub: 中文 Issue #190 / PR #191 已完成；三项 CI 全绿后 squash 合并为 `main@b0f57c06`，Issue 自动关闭，终态已用中文回帖。
  - 授权: 唯一 DeepSeek reachability 通过后才执行一个新 `baseline -> treatment` pair；阶段机械上限 245,000 recorded tokens，禁止 retry、replacement、backfill 和追加 pair。
  - 实现: 新 execution manifest/Schema/preregistration/runner 复用 #184 生命周期；独立进程内把 controlled-parent submit 接到 production `_submit_with_post_build_phase`，把 continuation 接到 #186 `RuntimeParityToolAdapter + SerialToolCallMiddleware`，退出时恢复全部模块引用。
  - 边界: #188 候选和 #184 evidence 不修改；新报告记录每臂 4/2/2/2 原子动作预算、P2、candidate/replay、cleanup 与 `historical_pair_replacement=false`，AK 仅允许从既有 env 读取且不得落盘。
  - 验证: final manifest canonical SHA-256 为 `3710bd3ace9fdc57d52b3018542c01871703c9965e48ede0be436d178ae784aa`；聚焦 `8 passed`，路线 P 相邻 `63 passed, 1 deselected`，Ubuntu-native Docker gate `1 passed in 35.73s`，Ruff、format、语法、CLI 与 diff 检查通过；固定 0 provider/attempt/token。
  - 踩坑: 首次 Docker 调用误用通用 `FORGE_RUN_DOCKER_TESTS`，测试仅 skip、未执行容器；读取文件后改用唯一声明的 `FORGE_RUN_OPAQUE_RUNTIME_PARITY_DOCKER=1`，不再调试包装命令。
  - 真实终态: reachability 1.423 秒、17 tokens 通过；pair 总计 45,858 tokens。Baseline 8 requests/38,602 tokens，消耗 4 inspection 后 graph-step limit，0 submit/replay、P2 unproven；treatment 3 requests/7,239 tokens，以 1 inspection + 1 repair build + 1 automatic submit 完成 candidate/replay，P2 转为 `proven/direct_cmake`。
  - Evidence: complete pair 与 cleanup 均通过，0 managed orphan；三条 ledger hash chain 为 42/25/7 events；canary report SHA-256 为 `767349a7c939c8088218fc2b08e95277b1564cc9c17ee3d15ef9fd33b985457b`。禁止重跑或追加。
  - 下一步: 只读分析 baseline/treatment 行为路径、repair packet 的 intervention delivery 与复制价值；单 pair 不估计 treatment effect、不计算 p 值、不排名模型，也不自动扩多 pair。
  - 文件: `scripts/forge_opaque_provenance_runtime_parity_execution_protocol.py`, `scripts/forge_opaque_provenance_runtime_parity_execution_runner.py`, `backend/tests/test_forge_opaque_provenance_runtime_parity_execution.py`, `benchmarks/manifests/cpp-opaque-provenance-runtime-parity-execution.json`, `benchmarks/schemas/forge-opaque-provenance-runtime-parity-execution.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-runtime-parity-execution.md`

- 2026-08-30 — 冻结 Issue #188 runtime-parity provider amendment 候选
  - GitHub: 中文 Issue #188 已创建并回读；分支为 `research/188-opaque-provenance-provider-amendment-candidate`，基线为 `main@ad6e7c11`。
  - 实现: 从 #184 execution identity 派生独立的新 pair/evidence identity；两臂共享 #186 的 4/2/2/2 原子分项预算、冻结 build directory/target 与 `parallel_tool_calls=False`，treatment 唯一 exposure 仍为 repair packet。
  - 历史边界: #184 canary report SHA-256 固定为 `e6ee3e2d...34034da0` 且只读；新 pair 明确不是 retry、replacement、backfill 或 schedule extension，不与 #184 或其他 fault family 池化。
  - 授权边界: 当前仅开放 `validate/plan/preflight`；reachability、provider call、formal attempt、credential 读取、model creation 与 pair execute 均机械关闭，固定 0 provider/attempt/token/evidence write。
  - 验证: canonical manifest SHA-256 为 `27b161720d3ab1208d6792e59df4509a611c3967645787a083b0fb9bdc6bdcb2`，新 evidence identity 为 `ce7e4277bcedab8b203ebe51863877b2d3f958e838ed7dcc960a47f23981c25a`；聚焦 `18 passed`，路线 P 相邻静态回归 `55 passed, 1 deselected`，Ruff、format、语法、CLI 与 diff 检查通过。
  - 下一步: 完成中文提交、WSL helper 推送、中文 PR 与 CI；合并后的干净主干只做一次真实 0-provider preflight。新的 provider amendment 必须另行派生执行 identity，不能在本候选中开放 execute。
  - 文件: `scripts/forge_opaque_provenance_provider_amendment_candidate_protocol.py`, `scripts/forge_opaque_provenance_provider_amendment_candidate_runner.py`, `backend/tests/test_forge_opaque_provenance_provider_amendment_candidate.py`, `benchmarks/manifests/cpp-opaque-provenance-runtime-parity-provider-amendment-candidate.json`, `benchmarks/schemas/forge-opaque-provenance-runtime-parity-provider-amendment-candidate.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-runtime-parity-provider-amendment-candidate.md`

- 2026-08-30 — 完成 Issue #186 opaque provenance runtime-parity 零 provider 门禁
  - GitHub: 中文 Issue #186 / PR #187 已完成；backend unit tests、backend lint、frontend lint 三项 CI 全绿后 squash 合并为 `main@ad6e7c11`，Issue 自动关闭，本地主干与 `origin/main` 已同步。
  - 实现: 新增 experiment-only 原子分项预算、冻结 CMake repair/stage 白名单和 `SerialToolCallMiddleware`；inspection/build/stage/submit 上限为 4/2/2/2，已有 staged artifact 的 repair build 会在执行前同时预留 automatic submit。
  - 真实证据: Ubuntu-native Docker gate `1 passed in 36.80s`；真实 bound submit 失败后 fence 三字段释放，bound repair build 自动 submit，candidate/clean replay passed，dynamic P2 转为 `proven/direct_cmake`，0 provider/attempt/token，0 residual container。
  - 验证: 静态 `8 passed`，编译核心相邻 `159 passed`，路线 P `84 passed, 1 deselected`；Ruff、format、语法、CLI、diff 与敏感信息检查通过。旧 #182 preflight 测试因真实 #184 evidence 已非空而失效，不删除 evidence规避。
  - 踩坑: 首次 Docker 测试自身使用 `&&` 被预注册 compound-shell 门禁正确拒绝；第二次仅误读不存在的 `VerificationResult.passed`。均只修测试，最终真实 gate 通过。
  - 下一步: 只设计独立的一次性 provider amendment 候选，复用 #186 已验证的 runtime-parity 机制并冻结新的 evidence identity、执行上限和停止规则；候选审阅前不调用 provider，不重跑、replacement、backfill 或追加 #184 pair。
  - 文件: `scripts/forge_opaque_provenance_runtime_parity_gate.py`, `backend/tests/test_forge_opaque_provenance_runtime_parity_gate.py`, `backend/tests/test_forge_opaque_provenance_runtime_parity_gate_docker.py`, `benchmarks/preregistrations/cpp-opaque-provenance-runtime-parity-zero-provider-gate.md`

- 2026-08-30 — 完成 #184 post-build command budget 充分性只读审计
  - 范围: 只读核对 `bound_compile_tools.py`、#178 真实 Docker gate、#184 runner/ledger 与相邻测试；0 provider、0 Docker、0 formal attempt、0 model token，未读取 credential，未改 production、协议、manifest 或冻结 evidence。
  - 根因: 正常 `submit_build_result` 失败会经 `_submit_with_post_build_phase` 释放 post-build fence；#178/#184 controlled parent 却直接调用 `submit_build_result_impl`，把仍保留 `post_build_supporting_command_id` 与 `post_build_commands_remaining=2` 的非正常 compiler-facing 状态复制给双臂。Fence 又无条件禁止 `build`，所以 treatment 的 direct CMake repair 从 checkpoint 起即不可执行；单纯把 2 调大不能修复。
  - 门禁缺口: #178 treatment 通过 `_record_command` 直接调用 runtime，绕过真实 `run_container_bash` policy，因此只证明 Docker candidate/replay lifecycle 可闭合，未证明 Agent repair action 可达。#184 同一模型回合的并行 tool calls 还暴露 admission check 与 budget consume 分离的竞态风险。
  - 解释: baseline 保持 `endpoint_censored`；treatment 应记为 measurement-policy censoring / intervention-delivery failure，不能记作 repair packet 无效或严格资源约束下的模型失败。本 pair 不提供 treatment-effect 证据。
  - 下一步: 先做独立 0-provider runtime-parity amendment 候选：失败 submit 后 fence 必须与真实 wrapper 一致地释放；按 inspection/build/stage/submit 分项计量，允许冻结 build-dir/target 上的 bounded repair build，并关闭并行 tool calls。候选通过确定性正负例前不调用 provider、不追加 pair。
  - 验证: 当前语义聚焦测试 `3 passed`；现有 `langchain-deepseek` 已原生支持 `parallel_tool_calls=False`，无需自实现 provider 协议。

- 2026-08-30 — 完成 opaque provenance 最小 provider canary 并冻结负结果
  - GitHub: Issue #184 / PR #185 已以 `main@6440838a` 完成，三项 CI 全绿；真实执行结果已用中文回帖 #184。
  - 执行: DeepSeek `deepseek-v4-flash` reachability 以 1.882 秒、17 tokens 通过；唯一 `baseline -> treatment` pair 使用 37,225 tokens，完整双臂与 cleanup 终态通过。
  - 结果: Baseline 第 2 次请求 300 秒超时并归为 endpoint censor；treatment 8 次请求后达到 graph-step limit。两臂均 0 submit、0 replay、P2 `unproven/opaque_wrapper`，不估计 treatment effect。
  - 新发现: Treatment 前两条环境检查耗尽 `post_build_commands=2`；后续诊断与两次 direct CMake build 均为 exit 126、`policy_rejected`。当前应先审计恢复预算充分性，不能把未 conversion 直接解释为 repair packet 无效。
  - Evidence: 三条 JSONL hash chain 有效，packet 是唯一 exposure，coordinator 为 `cleaned`，managed/checkpoint container/image 为 0；`reports/canary.json` SHA-256 为 `e6ee3e2db68c191e7c4e278071ea14a32e6ef362d82194d07697b0ea24034da0`。
  - 下一步: 只读、0-provider 审计 post-build command budget 与 graph/request/tool 预算关系；冻结 evidence，禁止 retry、replacement、backfill 或追加 pair。
  - 文件: `scripts/forge_opaque_provenance_minimal_canary_execution_protocol.py`, `scripts/forge_opaque_provenance_minimal_canary_execution_runner.py`, `backend/tests/test_forge_opaque_provenance_minimal_canary_execution.py`, `benchmarks/manifests/cpp-opaque-provenance-minimal-canary-execution.json`, `benchmarks/schemas/forge-opaque-provenance-minimal-canary-execution.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-minimal-canary-execution.md`

- 2026-08-30 — 建立 opaque provenance 最小 canary 授权候选与零 provider 接线门禁
  - 文件: `scripts/forge_opaque_provenance_minimal_canary_authorized_protocol.py`, `scripts/forge_opaque_provenance_minimal_canary_authorized_runner.py`, `benchmarks/manifests/cpp-opaque-provenance-minimal-canary-authorized.json`, `benchmarks/schemas/forge-opaque-provenance-minimal-canary-authorized.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-minimal-canary-authorized.md`, `backend/tests/test_forge_opaque_provenance_minimal_canary_authorized.py`
  - 范围: Issue #182 从 #180 parent identity 派生独立授权候选，冻结 evidence 目录、preflight/marker/ledger/report 路径、单次 reachability/pair 顺序和 runtime adapter 文件哈希；只允许 validate、plan 与只读 preflight。
  - 边界: reachability/provider/formal/canary/token 授权均关闭，`execute_reachability` / `execute_canary` 机械拒绝；无 credential 读取、model 创建或 evidence 写入，不修改 production Compiler/Oracle、`operations.py` 或历史 evidence。
  - 验证: manifest canonical SHA-256 为 `00ce7eaadda3e89b63d093f4e360473fe372850dd39290d69e1a4a7e675e7771`，evidence identity SHA-256 为 `f83fb4a3d228c82839df68905ee603c79095c919fe0cc8ab0c52ce4debaeb538`；聚焦与路线 P 相邻静态回归 `69 passed`，Ruff check/format、Python 语法、Schema、CLI 和 `git diff --check` 通过。
  - 下一步: 合并后从干净主干运行真实 0-provider preflight；通过后只形成一次真实 reachability + 单 pair canary 的授权决策包，不自动调用 provider或扩大 pilot。

- 2026-08-30 — 冻结 opaque build provenance 最小 provider canary 候选协议
  - 文件: `scripts/forge_opaque_provenance_minimal_canary_protocol.py`, `benchmarks/manifests/cpp-opaque-provenance-minimal-canary.json`, `benchmarks/schemas/forge-opaque-provenance-minimal-canary.schema.json`, `benchmarks/preregistrations/cpp-opaque-provenance-minimal-canary.md`, `backend/tests/test_forge_opaque_provenance_minimal_canary.py`
  - 范围: Issue #180 固定单个 `cppitertools` checkpoint、一个 `baseline -> treatment` pair，以及 DeepSeek `deepseek-v4-flash`、300 秒 timeout、0 retry、禁止 fallback 的未来运行身份；每臂 8 requests / 8 turns / 24 graph steps / 120,000 recorded tokens，阶段机械上限 245,000。
  - 边界: 当前只支持 `generate`、`validate`、`show-plan`，所有 reachability/provider/formal/canary 授权均为 false；无 model 创建、credential 读取或 execute path。单 pair 只验证机制接线，不估计 treatment effect、不计算 p 值、不排名模型。
  - 验证: manifest canonical SHA-256 为 `ad5a1ac989c4072ec097a3b0949d5e4393475d6df0896e108dbc313690dd3ee7`；本阶段聚焦与前三层相邻静态回归 `53 passed`，Ruff check/format、Python 语法、协议 CLI 和 `git diff --check` 通过。固定 0 provider、0 formal attempt、0 model token，未读取 AK、未启动 Docker。
  - 下一步: 合并后从干净主干执行 0-provider preflight，核对 `main == origin/main`、Ubuntu-native Docker、网络介质、候选 evidence 空目录与 0 managed orphan；真实 reachability 和 canary 仍需独立授权。

- 2026-08-30 — 闭合 opaque build provenance 真实 Docker 生命周期门禁
  - 文件: `scripts/forge_opaque_build_provenance_real_docker_gate.py`, `backend/tests/test_forge_opaque_build_provenance_real_docker_gate.py`, `backend/tests/test_forge_opaque_build_provenance_real_docker_gate_docker.py`, `benchmarks/preregistrations/cpp-opaque-build-provenance-real-docker-zero-provider-gate.md`
  - 动机: Issue #178 为 #174 P2 reference criterion 与 #176 合成 lifecycle adapter 补充真实 production candidate verifier、独立 clean replay 和 cleanup 证据；不修改 production Compiler/Oracle、`operations.py` 或历史 evidence。
  - 结果: 自包含 opaque `sh -c` parent 在真实 CMake/Ninja 项目中只触发 `build_system_unproven`，P2 为 `unproven/opaque_wrapper`；同源 baseline 保持 unproven、0 replay，treatment 仅接收白名单 packet并 append direct `cmake --build` 后转为 P2 `proven/direct_cmake`，production candidate 与 clean replay 均 passed，最终 container/image 0 orphan。
  - 验证: Ubuntu-native provider gate 确认为 `/var/run/docker.sock`；真实 opt-in gate `1 passed in 74.34s`，相邻静态回归 `47 passed`，Ruff check/format、Python 语法和 `git diff --check` 通过。固定 0 provider call、0 formal physical attempt、0 model token，未读取 AK。

- 2026-08-29 — 接入 opaque build provenance 零 provider 生命周期契约
  - 文件: `scripts/forge_opaque_build_provenance_lifecycle_gate.py`, `backend/tests/test_forge_opaque_build_provenance_lifecycle_gate.py`, `benchmarks/preregistrations/cpp-opaque-build-provenance-lifecycle-zero-provider-gate.md`
  - 动机: Issue #176 把 #174 的 P2 reference criterion 接到同源 failure checkpoint 双臂边界，先验证 treatment exposure、post-checkpoint conversion 与终态观察顺序，不直接进入 provider 或 Docker 实验。
  - 结果: baseline/treatment 共用 checkpoint `892cecacebba9410d1fa64dcf24d338efcf7e87b12005db85353946b943b8a40` 和 parent history `ed9c0bad711097c6d28d3b534b78604da92e1b6fcdec6dbfd3383508d7ec016f`；baseline 保持 unproven，treatment 只在 parent ledger 尾部追加 trusted direct-CMake invocation 后转为 P2 proven。Candidate/replay/cleanup observer 按顺序 fail closed，并绑定同一 observation subject SHA-256。
  - 验证: 本阶段聚焦测试 `17 passed`，连同 #174 P2 gate 的相邻回归为 `38 passed`；Ruff check/format、Python 语法与 CLI validate 通过。固定 0 provider、0 formal attempt、0 model token、`docker_executed=false`；observer 为 deterministic contract callback，不构成真实 candidate/clean replay 证据。

- 2026-08-29 — 建立 opaque build provenance P2 零 provider 契约门禁
  - 文件: `scripts/forge_opaque_build_provenance_gate.py`, `backend/tests/test_forge_opaque_build_provenance_gate.py`, `benchmarks/preregistrations/cpp-opaque-build-provenance-zero-provider-gate.md`
  - 动机: Issue #174 按路线 P 把 `build_system_unproven` 收敛为独立 provenance compliance stratum，避免把合法 native build 的 parser 假阴性表述为普通编译失败。
  - 结果: 版本化 P2 evaluator 接受 direct CMake、可信 configure + native Ninja 与透明 wrapper；缺 generator link、opaque wrapper 和 build-dir 不一致保持 unproven，source/image/attempt/artifact/ledger 漂移 fail closed。受控 fault 前后 command-history SHA-256 相同且 `replay_attempts=0`。
  - 验证: 聚焦测试 `21 passed`，Ruff check/format、Python 语法与 CLI validate 通过；固定输出 0 provider call、0 formal physical attempt、0 model token，不启动 Docker且不修改 production Compiler/Oracle/历史 evidence。

- 2026-08-29 — 实现多 checkpoint behavioral pilot v3 授权采集 runner
  - 文件: `scripts/forge_multi_checkpoint_behavioral_pilot_v3_authorized_protocol.py`, `scripts/forge_multi_checkpoint_behavioral_pilot_v3_authorized_runner.py`, `backend/tests/test_forge_multi_checkpoint_behavioral_pilot_v3_authorized.py`, `backend/tests/test_forge_multi_checkpoint_behavioral_pilot_v3_authorized_docker.py`, `benchmarks/manifests/cpp-verifier-multi-checkpoint-behavioral-pilot-v3-authorized.json`, `benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3-authorized.schema.json`, `benchmarks/preregistrations/cpp-verifier-multi-checkpoint-behavioral-pilot-v3-authorized.md`
  - 动机: Issue #172 在实验负责人确认 `wifi` 与 Ubuntu `docker.service` active 后，授权一次 DeepSeek canary 和 #170 冻结的 6 pair / 12 arm，maximum 1,440,000 recorded tokens。
  - 实现: 新 identity 冻结一次性 canary、空 evidence/clean main/Compose-DooD/0 orphan preflight 和 fail-closed batch；通用 case runtime 复用 #168 parent/checkpoint 生命周期与 behavioral v2 三层终态、candidate verifier、clean replay 和单事件循环语义；报告逐 case 四格、请求、tokens、failure transitions 与 case 等权 macro-average。
  - 验证: canonical manifest SHA-256 为 `933891035aa6cf4ddaa842bdb60ff97343099484a1cb1b448b511d1d16081a8e`；未授权/授权相邻回归 `14 passed`，Ruff check/format 通过；Janet/Make fake-model 真实 Docker gate `1 passed in 171.56s`，结束后 0 managed container / 0 checkpoint image。
  - 边界: 当前仍为 0 provider、0 formal physical attempt、0 model token，未读取 AK；下一步完成中文提交、WSL 推送、PR/CI/合并后，才在干净主干执行零请求 preflight 与唯一 canary。

- 2026-08-29 — 冻结多 checkpoint behavioral pilot v3 未授权协议
  - 文件: `scripts/forge_multi_checkpoint_behavioral_pilot_v3_protocol.py`, `scripts/forge_multi_checkpoint_behavioral_pilot_v3_runner.py`, `backend/tests/test_forge_multi_checkpoint_behavioral_pilot_v3.py`, `benchmarks/manifests/cpp-verifier-multi-checkpoint-behavioral-pilot-v3.json`, `benchmarks/schemas/forge-multi-checkpoint-behavioral-pilot-v3.schema.json`, `benchmarks/preregistrations/cpp-verifier-multi-checkpoint-behavioral-pilot-v3.md`
  - 动机: Issue #170 把 #168 已通过零 provider 门禁的 CMake `cppitertools`、Make `janet`、Autotools `libcheck` 冻结为新的跨构建系统描述性 pilot；不修改 behavioral v2、生产 Compiler/Oracle 或历史 evidence。
  - 结果: 固定 `3 cases x 2 pairs = 6 pairs / 12 arms`，每个 case 各一个 baseline-first 与 treatment-first；单臂/单对/阶段 recorded-token 上限为 120,000 / 240,000 / 1,440,000，逐 case 报四格、请求、tokens、失败迁移并以 case 等权 macro-average 汇总。canonical manifest SHA-256 为 `7efa555cb95ace497833c5fb9e9106778d5f856214f9d07a3511bd04298cae5b`。
  - 验证: 定向 pytest `6 passed`；Ruff check/format、协议生成一致性、runner plan、冻结组件和敏感信息扫描通过。
  - 边界: runner 为 `protocol_plan_only` 并机械拒绝 collection；0 provider、0 formal physical attempt、0 model token、未读取 AK、未创建实验 evidence。下一步是中文提交、WSL helper 推送、中文 PR 与 CI；真实采集必须另建授权 identity。

- 2026-08-29 — 完成跨构建系统多 checkpoint 零 provider 门禁
  - 文件: `scripts/forge_multi_checkpoint_zero_provider_gate.py`, `backend/tests/test_forge_multi_checkpoint_zero_provider_gate.py`, `backend/tests/test_forge_multi_checkpoint_zero_provider_docker.py`, `benchmarks/manifests/cpp-verifier-multi-checkpoint-zero-provider-gate.json`, `benchmarks/schemas/forge-multi-checkpoint-zero-provider-gate.schema.json`, `benchmarks/preregistrations/cpp-verifier-multi-checkpoint-zero-provider-gate.md`
  - 动机: behavioral pilot v2 的 6 对全部来自同一 CMake checkpoint；Issue #168 在不修改冻结 runner/evidence 的前提下，补 Make `janet` 与 Autotools `libcheck` 的真实 checkpoint 可恢复性证据。
  - 结果: 静态协议 `7 passed`；Make 新 case 完整通过；Autotools 新 case `1 passed in 249.93s`；既有 CMake Windows-bind anchor `1 passed in 125.98s`。三个构建系统均闭合 parent build、受控缺产物故障、checkpoint、双臂恢复、candidate verifier、clean replay 与 cleanup，最终 0 container/image orphan。
  - 边界: canonical manifest SHA-256 为 `6d953ae758056dca00b9013979e0f03d1c5877b386fc803feaea1131fd17339c`；0 provider、0 formal physical attempt、0 model token，不证明跨 fault-family 泛化或 repair treatment 效应。下一步是完成中文提交/推送/PR/CI，再另行冻结 3 cases x 2 pairs 的描述性 pilot。

- 2026-08-29 — 完成 checkpoint 行为终态 v2 六配对实验
  - 文件: `benchmarks/reports/cpp-verifier-checkpoint-behavioral-pilot-v2.md`, `.compile-sessions/benchmark-evidence-checkpoint-behavioral-pilot-v2/`
  - 动机: 按 Issue #163 选择 A 和 Issue #165 冻结协议，把模型预算内失败保留为 outcome，并避免已观察旧 pair 进入新估计。
  - 结果: PR #166 三项 CI 全绿并合并为 `main@38165724`；真实 6/6 pair、12/12 arms 全部尝试，0 endpoint censoring、6/6 primary-mechanism eligible、231,944 tokens。Baseline 3/6 repair success，treatment 5/6；配对 delta 为 `[0, 1, 0, -1, 1, 1]`，只做描述性机制结论。
  - 完整性: 50 个 evidence 文件、18/18 Session 终态、0 container/image orphan；pilot report SHA-256 为 `932d47bb9a3ce30f68f86aee660c4ae2ca36b343333f4a77d6dab0a60a8049bd`，inventory SHA-256 为 `95014c1169fe6950c14726a16f43fd45454c10604f3b9f38494bff0b106f88d8`。

- 2026-08-19 — 终结 checkpoint primary canary amendment
  - 文件: `.compile-sessions/benchmark-evidence-checkpoint-primary-canary-amendment/`（Git 忽略的 append-only 本地 evidence）
  - 动机: 按 Issue #155 冻结授权执行唯一 reachability 与 controlled pair，并在失败后保留终态、审计 cleanup 和历史 endpoint timeout。
  - 结果: reachability 通过；baseline 首请求 300.165 秒 timeout，pair marker 失败，treatment/6-pair pilot 未启动，recorded tokens 为 17，最终 0 orphan；中文 Issue #157 已建立下一决策入口并公开更正后验 SQLite sidecar。

- 2026-08-19 — 合并 checkpoint primary canary amendment 候选
  - 文件: `scripts/forge_checkpoint_primary_canary_amendment.py`, `backend/tests/test_forge_checkpoint_primary_canary_amendment.py`, `benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-amendment-candidate.json`, `benchmarks/preregistrations/cpp-verifier-checkpoint-primary-canary-amendment.md`
  - 动机: 旧 reachability 绑定旧 manifest/revision，Windows bind parity 修复后必须用独立 identity、目录和 marker 再申请一次受控机制 canary。
  - 结果: 中文 PR #154 三项 CI 全绿后 squash 合并为 `main@9feb832d`，Issue #153 自动关闭；本地 `main` 与 `origin/main` 同步一致，远端研究分支保留。

- 2026-08-19 — 合并 Windows bind checkpoint 构建目录修复
  - 文件: `scripts/forge_checkpoint_windows_build_layout.py`, `backend/tests/test_forge_checkpoint_windows_build_layout.py`, `backend/tests/test_forge_checkpoint_windows_bind_parity_docker.py`
  - 动机: tracked `BUILD` 与 CMake 小写 `build` 在 Windows bind 上冲突，使 Issue #149 pair 在 arm/provider 前环境删失。
  - 结果: 中文 PR #152 三项 CI 全绿后 squash 合并为 `main@c7217e20`，Issue #151 自动关闭；本地主干与 `origin/main` 同步一致。

- 2026-08-19 — 终结 Issue #149 primary mechanism canary
  - 文件: `scripts/forge_checkpoint_primary_canary.py`, `benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-authorized.json`
  - 动机: 唯一 reachability 已通过；唯一 controlled pair 在 parent configure、任何 arm/provider 请求之前因 Windows bind 上 `BUILD`/`build` 冲突失败关闭。原 marker、ledger、report 与 workflow evidence 保持不变，不重试、replacement 或 backfill。

- 2026-08-18 — 冻结并合并 controlled fault v1 零 provider gate
  - 文件: `scripts/forge_controlled_fault_v1_gate.py`, `backend/tests/test_forge_controlled_fault_v1_gate.py`, `backend/tests/test_forge_controlled_fault_v1_docker.py`, `benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-candidate.json`
  - 动机: 在任何 provider canary 前证明真实 verifier failure 可重复、checkpoint 两臂同源、恢复后 candidate/clean replay 可通过且 cleanup 无 orphan。
  - 结果: PR #148 squash 合并为 `main@fd89d1e6`，三项 CI 通过；Issue #147 自动关闭。

- 2026-08-15 — 证明 failure checkpoint 的 rootfs 与 bind-mount 同源双臂恢复
  - 文件: `scripts/forge_environment_checkpoint_prototype.py`, `backend/tests/test_forge_environment_checkpoint_prototype.py`, `benchmarks/preregistrations/cpp-verifier-environment-checkpoint-prototype.md`
  - 动机: 消息 checkpoint 已通过，但真实 mechanism arm 还必须从同一 rootfs 与 bind snapshot 恢复，且不能共享可写状态。
  - 结果: Issue #137 原型在同一显式 pause 窗口完成 rootfs commit 与只读 bind tar；两臂初始 canonical state 相同，rootfs/workspace/artifacts 交叉污染为 0，父 snapshot 不变。
  - 证据: checkpoint manifest SHA-256 为 `e5c5a8c024339775f469fa889c441f028f099561fe3638ae54da5d02d9bf2375`，initial state SHA-256 为 `5c05c6ca919a0d39f23945ad4b72293153901733cc010a9720f54316b9700a47`；真实 Docker `1 passed in 28.38s`，相邻回归 `18 passed, 1 skipped`，Ruff 通过，cleanup 后 0 prototype container/image/temp。
  - 边界: 0 provider、0 formal physical attempt、0 model token；budget reconstruction 继续作为下一独立 gate。

- 2026-08-14 — 完成 verifier-driven repair 运行时与未授权证据门禁
  - GitHub: 中文 Issue #125 已创建并回读；实现分支为 `research/issue-125-verifier-repair-runtime`，基线为 `main@97f252b4`。
  - 实现: 新增版本化 submit feedback adapter、严格白名单 `repair_packet`、独立 hash-chain sidecar、treatment fidelity gate、硬拒绝 canary/attempt/batch 的未授权 runner，以及只做配对描述性统计的 analyzer。
  - 修复: 失败 submit 缺少对应 `submit.completed` 时明确记为 `failed/evidence_missing`；baseline 原始/返回 SHA-256 不一致时拒绝；sidecar 事件 payload 严格校验；动态 failed-check 名称只保留安全标识，合法 artifact 名不再被宽泛敏感词扫描误拒绝。
  - 指标: analyzer 已覆盖 actionable verifier failures、repair conversions、false acceptance、submit/replay 次数、failure transitions、token、请求数和墙钟差值；仍禁止 p-value 和模型排名。
  - 验证: 聚焦测试 `17 passed`，Ruff check/format、`py_compile`、Schema、protocol/runner validate、确定性再生成、共享 compile blob、diff 与敏感信息扫描通过；canonical manifest SHA-256 为 `880af0175795e474d470fd483544296fc68cdb0e5e968cebd32d73ef183ab045`。
  - 边界: 未启动 Docker、未调用模型、未创建实验 evidence；12 slots、provider canary、physical attempt、batch 和 maximum 2,400,000 recorded tokens 仍未授权。
  - 文件: `scripts/forge_verifier_repair_runtime.py`, `scripts/forge_verifier_repair_pilot_protocol.py`, `scripts/forge_verifier_repair_pilot_runner.py`, `scripts/forge_verifier_repair_pilot_analyzer.py`, `backend/tests/test_forge_verifier_repair_pilot.py`, `benchmarks/manifests/cpp-verifier-repair-pilot-runtime-candidate.json`, `benchmarks/schemas/forge-verifier-repair-packet-v1.schema.json`, `benchmarks/schemas/forge-verifier-repair-pilot-runtime-v1.schema.json`

- 2026-08-14 — 完成 verifier-driven repair 配对 pilot 未授权决策包
  - GitHub: Issue #123 与 PR #124 使用中文创建并回读；核心设计提交为 `f5798c5e`。
  - 证据: formal v4 中一个槽在 `candidate_verification_failed -> build_system_unproven` 后自然修复并通过，另一个 `recipe_execution_failed` 槽被后续 endpoint timeout 混杂；这些轨迹只支持 treatment 设计，不能估计效果。
  - Treatment: baseline 已返回状态、追踪 ID、候选 artifact 元数据与首条错误 message，但没有标准化 failure classification、failed checks、build-system identity 或 artifact diff；treatment 只增加确定性结构化 `repair_packet`，不增加模型请求、Compiler invocation、turn、timeout 或 token 预算，也不改变 Oracle/clean replay/delivery。
  - Pilot: 从冻结 case protocol 按 prior-exposure 规则选择 `liblouis`、`openthread`、`mupdf`，覆盖 Autotools/CMake/Make；双 provider、双 arm、一次重复，共 12 槽/6 pair，expected 800,000、maximum 2,400,000 recorded tokens。
  - 边界与验证: `collection_authorized=false`、`runtime_implementation_authorized=false`；12 个唯一槽、6 个完整 pair、3/3 顺序平衡、case 来源、四份冻结 SHA-256、diff 与敏感信息检查通过。未启动 Docker、未调用模型、未修改 Forge 核心或历史 evidence。
  - 文件: `benchmarks/preregistrations/cpp-verifier-driven-repair-pilot-v1.json`, `benchmarks/preregistrations/cpp-verifier-driven-repair-pilot-v1.md`

- 2026-08-14 — 完成 formal 300 秒模型请求超时校准并固化确定性结果
  - GitHub: Issue #119 / PR #120 已将 `formal-collection-4.6.0-timeout-canary-amendment` squash 合并为 `main@2c4981e4`，三项 CI 全绿；Issue #121 跟踪本结果报告并由当前提交收口。
  - 采集: Ubuntu 原生 Docker gate、runtime preflight 13/13 和 formal non-model preflight 通过；唯一新 canary 中 RichLab `gpt-5.5` 为 17.874 秒，DeepSeek `deepseek-v4-flash` 为 0.685 秒。
  - 结果: `cppitertools` 两个授权槽均 passed，2/2 Oracle、clean replay、finalization 和 cleanup 成功；23/23 模型请求闭合，记录 142,502/500,000 tokens，0 failed、0 cancelled、0 orphan。
  - 解释: RichLab 9 次请求最大 33.8912 秒，DeepSeek 14 次请求最大 5.896452 秒，超过 120 秒和 300 秒均为 0。该批证明 300 秒配置路径可完整运行，但没有观测到延长截止点挽救慢请求，不能据此宣称 300 秒优于 120 秒，也不能凭单项目各一次 attempt 排名模型。
  - 文件: `scripts/forge_formal_timeout_calibration_result.py`, `backend/tests/test_forge_formal_timeout_calibration_result.py`, `benchmarks/reports/cpp-formal-timeout-canary-amendment.json`, `benchmarks/reports/cpp-formal-timeout-canary-amendment.md`

- 2026-08-12 — 固定 Ubuntu 原生 Docker 门禁并形成 formal v4 首批授权决策包
  - GitHub: Issue #109 记录双 daemon 混淆风险、门禁目标和 0 模型/0 ledger 边界；实现分支为 `research/formal-v4-ubuntu-daemon-gate`。
  - 环境门禁: 新增 `scripts/require-ubuntu-native-docker.sh`，要求 WSL2 `Ubuntu`、active `docker.service`、`dockerd` MainPID、`default` context、`/var/run/docker.sock` 和 Ubuntu daemon OS；失败时停止并请求用户介入，不启动 Docker Desktop 或切换 daemon。`docker.sh`、`wsl-check.sh` 与 `AGENTS.md` 已统一调用该门禁。
  - 协议: 新增未授权 `formal-collection-4.2.0-ubuntu-candidate`，canonical SHA-256 为 `77e80eb39b01eeba73d1fdd07e2b8da658032fcc124cacbf45ae2d06f6831601`；冻结 `daemon_provider=ubuntu-native` 和 socket source gate，父级 v4 runtime candidate 保持逐字不变。
  - 决策包: 结果盲态选择冻结 schedule 的第一个项目 `cppitertools`，完整 block 使用原 slot identity `1, 2, 73, 74, 153, 154`，覆盖双 condition × 三次重复；建议 980,000 recorded-token 上限，但 `collection_authorized=false`，provider canary、ledger、模型与 batch 仍全部禁止。
  - 验证: 门禁/新协议聚焦 `23 passed`，formal v1-v4 与 Docker 扩大回归 `138 passed`；Ruff、shell 语法、Schema、确定性再生成和父协议校验通过。真实 Ubuntu 宿主门禁通过，Compose/DooD preflight 13/13 通过，0 JSON/JSONL、0 compile/replay orphan。
  - 文件: `scripts/require-ubuntu-native-docker.sh`, `scripts/docker.sh`, `scripts/wsl-check.sh`, `scripts/forge_formal_collection_v4_ubuntu_protocol.py`, `scripts/forge_formal_collection_v4_ubuntu_runner.py`, `benchmarks/manifests/cpp-formal-v4-ubuntu-candidate.json`, `benchmarks/preregistrations/cpp-formal-v4-ubuntu-gate-and-initial-block.md`

- 2026-08-12 — 接通并合并 formal v4 physical-attempt 生命周期预算
  - GitHub: Issue #105 / PR #106 已 squash 合并为 `main@484f6999`，Issue 自动关闭；backend unit tests、backend lint 与 frontend lint 三项 CI 全绿。
  - 实现: experiment evidence 保存单调时钟与原子 claim；provider、Compiler、submit/clean replay、finalize、cleanup 使用同一预算上下文，runner 在 1,680 秒工作 deadline 主动取消 agent stream，并在强制收口后记录最终 overrun 快照。
  - 协议: 未授权 `formal-collection-4.1.0-runtime-candidate` canonical SHA-256 为 `d1c211e638ee2fd71c5c2f9e70f250306a131f9ae8759c9bd064e48a96252473`；冻结的 v4 父协议保持不变，v3 7-slot 继续作为独立描述性 stratum。
  - 容器修复: runtime adapter 在 Compose 的 `/app/scripts` 与 `/repo` 分离布局中先从 `/repo/scripts` 建立协议链，再导入父 runner；未授权 provider canary 现在明确拒绝，不再被父 manifest 的 `/app` 错误根路径掩盖。
  - 验证: 最终候选 `12 passed`、扩大回归 `227 passed`、真实 Docker 生命周期 `1 passed`；Compose/DooD preflight 11/11 通过，可用内存约 4.57 GiB、daemon 延迟约 0.031 秒，canary 退出码 2 且 0 evidence。Ruff、Schema、冻结父文件、diff 与敏感信息检查通过。
  - 边界: 本阶段没有调用模型、消耗 AK、创建 v4 ledger 或启动正式采集。下一阶段须另行确认完整 project block、slot 数、recorded-token 上限和停止条件，再派生 authorized v4 identity。
  - 文件: `backend/packages/harness/deerflow/compile/evidence.py`, `backend/packages/harness/deerflow/compile/operations.py`, `backend/packages/harness/deerflow/tools/builtins/task_tool.py`, `backend/packages/harness/deerflow/agents/middlewares/llm_error_handling_middleware.py`, `scripts/forge_formal_collection_v2_runner.py`, `scripts/forge_formal_collection_v4_runtime_protocol.py`, `scripts/forge_formal_collection_v4_runtime_runner.py`, `benchmarks/manifests/cpp-formal-v4-runtime-candidate.json`

- 2026-08-11 — 冻结未授权 formal v4 attempt 级预算与宿主资源门禁
  - GitHub: Issue #103 / PR #104 记录 formal v3 长尾根因、v4 设计目标和禁止模型采集边界；候选协议 canonical SHA-256 为 `bb151473b276c48b9faf287a9dcbdddd96145abf3acc605f952275cf3d3f6720`。
  - 协议: v4 保持 C/C++、180-slot schedule、双 provider、Compose/DooD、Compile Session、clean replay 与 artifact oracle 不变，并重新锁定 `collection_authorized=false`；v1-v3 manifest、Schema、runner、报告和历史 evidence 未修改。
  - 预算: 每个 physical attempt 总墙钟 1,800 秒，其中 120 秒保留给收口；最多 2 次 Compiler 调用和 48 次模型请求。provider、Compiler 与 submit/replay 在达到工作/调用边界后硬拒绝新工作，finalize/cleanup 即使超限仍必须执行并记录 overrun。
  - 资源: 新 attempt 前要求 WSL2 Linux 可见 `MemAvailable >= 2 GiB`，`docker info` 在 10 秒内成功且 daemon 延迟不高于 5 秒；preflight 不记录 IP、SSID、代理、凭据、server version 或其他宿主标识。
  - 分析: v3 的 7 个 slot 保留为独立描述性 protocol stratum，不与 v4 primary estimand 池化；v4 primary 只纳入同协议完整 project block，不完整 block 从 paired primary estimate 排除但保留在端到端描述性失败分母。
  - 文件: `scripts/forge_formal_collection_v4_protocol.py`, `scripts/forge_formal_collection_v4_runner.py`, `benchmarks/manifests/cpp-formal-v4-collection.json`, `benchmarks/schemas/forge-cpp-formal-collection-v4.schema.json`, `benchmarks/preregistrations/cpp-formal-v4-amendment.md`, `backend/tests/test_forge_formal_collection_v4_protocol.py`, `benchmarks/README.md`
  - 验证: 聚焦 v4 `18 passed`，v3/v4 扩大回归 `54 passed`；真实 Compose/DooD 非模型 preflight 11/11 checks 通过，可用内存约 5.64 GB、daemon 响应约 0.032 秒；真实 `provider-canary` 入口以退出码 2 拒绝且 0 evidence 文件。Ruff、格式、Schema、确定性再生成、`py_compile`、diff 和敏感信息扫描通过。

- 2026-08-11 — 审计 formal v3 首批预算边界结果并停止后续 slot
  - GitHub: Issue #97 的双 provider canary 阻塞已在成功 canary 后解除并关闭；Issue #99 / PR #100 已完成描述性报告并 squash 合并为 `main@3ee28e8d`，三项 CI 全绿。
  - 采集: authorized preflight 为 `ready=true`，RichLab `gpt-5.5` 与 DeepSeek `deepseek-v4-flash` canary 分别约 4.404 秒和 1.034 秒通过；7/10 个授权 slot 执行后以 `recorded_token_boundary_reached` 停止，slot 8-10 未创建。
  - 结果: 记录 1,700,577 / 1,633,165 tokens，越界 67,412；4/7 oracle passed，195/195 请求闭合（194 completed、0 failed、1 cancelled），7/7 ledger、finalization 与 cleanup 有效，0 compile/replay orphan。
  - 边界: token 检查发生在完成当前 slot 后、创建下一 slot 前；当前授权已经耗尽，不得 retry、replacement、backfill 或继续 slot 8-10。7 个单次且 provider/case 不平衡的 slot 只支持描述性结论，不支持总体模型排名或显著性结论。
  - 新发现: 900 秒是每次 Compiler 调用的 wall-clock 预算，不是整个 physical attempt 的预算；7 个 slot 共调用 Compiler 14 次，PowerDNS 单槽 4 次调用并持续约 3,240.758 秒。
  - 文件: `scripts/forge_formal_collection_v3_report.py`, `backend/tests/test_forge_formal_collection_v3_report.py`, `benchmarks/reports/cpp-formal-v3-initial-batch.json`, `benchmarks/reports/cpp-formal-v3-initial-batch.md`, `benchmarks/README.md`
  - 验证: 报告聚焦测试 `28 passed`，Ruff、`py_compile`、敏感信息扫描及 7 份 ledger 独立复算通过；没有修改历史 ledger，也没有发起额外模型请求。

- 2026-08-11 — 授权 formal v3 首批十槽并迁移 RichLab 端点
  - GitHub: Issue #95 / PR #96 已 squash 合并为 `main@4a9771c8`，Issue 自动关闭；后端单测、后端 lint 和前端 lint 全绿。
  - 协议: 新增 `formal-collection-3.1.0` 独立 manifest/Schema/protocol/runner，canonical SHA-256 为 `87968a3a1dc858c5eb2881e32711da0e2912b90a50437d9534babc37bef67cb5`；未授权 v3 与历史 evidence 保持不变。
  - 门禁: CLI 默认 authorized manifest，固定 `mobile_hotspot`、首批 10 slot、1,633,165 recorded-token 停止边界、唯一 evidence 目录、首条 ledger 前双 canary、DooD mount-source gate，以及禁止 retry/fallback/replacement/backfill。
  - 本地接入: `.env` 中的 `OpenAI_AK` 已通过安全脚本替换；Gateway/LangGraph 强制重建后仅验证凭据存在性和 3 个 RichLab model 配置指向新地址，未输出或提交密钥。
  - 验证: 聚焦回归 `66 passed`，敏感信息扫描通过；分支和合并后 LangGraph Compose/DooD preflight 均 `ready=true`，`evidence_mount_source_matches_host_workspace=true`。

- 2026-07-30 — 固定 GitHub 写入与 WSL Git 网络通道
  - 文件: `AGENTS.md`, `scripts/push-via-wsl.ps1`, `.claude/memory/project.md`
  - 动机: GitHub App 对仓库写操作稳定返回 403；Windows Git 未使用当前可用代理，直连 `github.com:443` 超时，而 `api.github.com` 与带代理环境的 WSL Git 正常。
  - 实现: GitHub Issue/PR/评论等写操作直接使用已认证 Windows `gh`；push 统一通过 WSL Git 与 Windows `gh auth git-credential`，包含 URL/分支/remote 校验、有界超时和重试，不输出 token、代理值或认证头。
  - 验证: Issue #93 已用 Windows `gh` 创建并回读；PowerShell 语法、WSL dry-run、三类错误参数拒绝和真实测试分支 push 均通过。

- 2026-07-30 — 冻结未授权 formal v3 与 DooD evidence source 门禁
  - GitHub: Issue #90 / PR #91 已 squash 合并为 `main@96445f68`，Issue 自动关闭；PR 与主干 Unit Tests、后端 lint、前端 format/lint/typecheck/build 全绿。
  - 协议: v3 继承 v2 authorized 的双 provider、30 个 C/C++ exact-commit case、180-slot schedule、三次重复、Compose/DooD、Compile Session、clean replay 与零 fallback；canonical SHA-256 为 `9777816f157078ae555969c6c77ca8734ca4e1417235f57c98a628c384031b5d`。
  - 边界: v2 十槽登记为 `excluded_infrastructure_launch`，剩余 token ceiling 为 29,172,532；v3 保持 `collection_authorized=false`、`formal_comparison_enabled=false`，四类外部动作在 provider/ledger 前拒绝，当前 ledger/canary 为 0。
  - 门禁与验证: `/workspace/.compile-sessions` 的唯一可写 bind source 必须等于 `DEER_FLOW_HOST_WORKSPACE_ROOT/.compile-sessions`；真实 runtime/formal preflight 均 `ready=true`，formal 兼容组 `66 passed`、后端全量 `1843 passed, 29 skipped`、Ruff/Schema/Compose/v2 十 ledger 只读审计通过。

- 2026-07-30 — 修复 v2 十槽的 DooD evidence 路径分离并冻结失败证据
  - GitHub: Issue #86 / PR #87 已授权并执行 v2 前十槽；Issue #88 / PR #89 已将路径修复 squash 合并为 `main@45787399`，两项 Issue 均关闭。
  - 根因: 错误启动的 LangGraph 将宿主 `/.compile-sessions` 挂到 `/workspace/.compile-sessions`，Compile Session 子容器却使用宿主仓库下的 `.compile-sessions`；构建 marker 因扫描错误目录而十槽全部得到空 capability。
  - 修复: 构建系统 marker 改为在 Compile Session 容器的 `/workspace/repo` 内探测；marker probe 失败/非法结果显式报错；Compose 缺失或空 `DEER_FLOW_ROOT` 时拒绝解析，冻结历史 component 改从声明的 Git baseline blob 审计。
  - 审计: v2 canonical SHA-256 为 `f7888bbbf1d5f2b404d5769f73442308a7234559bb5c6bcec3533f39fc69e923`；10/10 ledger hash chain、finalization 与 cleanup 有效，32/32 模型请求闭合、143,286 tokens、697.972 秒、0/10 oracle pass、0 residual container。十槽均排除为 infrastructure launch，不 retry、replacement、backfill 或第 11 槽。
  - 验证: Forge `314 passed`、后端主体 `1823 passed, 29 skipped`、config-upgrade `4 passed`、聚焦回归 `159 passed`、真实 CMake exact-commit + submit + clean replay `1 passed in 37.77s`，PR/主干 Unit Tests 与 Lint Check 全绿。

- 2026-07-30 — 修复正式采集批处理生命周期并冻结未授权 v2 候选
  - GitHub: Issue #84 / PR #85 已 squash 合并为 `main@85ae003d`。
  - 修复: v2 批次共享一个 `asyncio.Runner`，冻结 `prepare → clone → identify → compiler → finalize` 顺序，并在 runner 局部关闭和恢复全局 Memory；共享 v1 运行时与既有 ledger 未修改。
  - 证据: v2 候选 canonical SHA-256 为 `843cc7386d05af0bb0285852fc128a0693302253aabe2a300bad3efcf41330d3`；合并后真实 Compose/DooD preflight 为 `launch_ready=true`、`ready=true`，候选保持 `collection_authorized=false` 且 ledger 为 0。

- 2026-07-30 — 完成正式采集 v1 授权、canary 与首批 10-slot
  - GitHub: Issue #82 / PR #83 已 squash 合并为 `main@4afd63a1`；Issue #82 已按完成关闭，失败根因转 Issue #84。
  - 结果: runtime preflight 7/7 与 RichLab `gpt-5.5`、DeepSeek `deepseek-v4-flash` 双 provider canary 通过；首批 10 个冻结 slot 按边界执行后 0/10 成功，其中 6 个首次模型请求 `connection_error`、4 个 `build_system_mismatch`，总记录 81,152 token、219.662 秒。
  - 证据: 10/10 ledger hash chain、当前 gate 重算、终态、session finalization 与 orphan cleanup 有效；replacement 全空，孤儿编译容器为 0。失败记录不重试、不替换、不回填，并从候选 v2 主分析中排除。

- 2026-07-29 — 冻结正式实验逐项目构建路径与 artifact oracle
  - GitHub: Issue #78 / PR #79 已 squash 合并为 `main@09012ff6`。
  - 结果: 30/30 case 与预注册 identity/分层一致，冻结 30 个精确 artifact oracle 与 77 条 exact-commit/OSS-Fuzz 证据；本地新增 `18 passed`、协议/evidence `261 passed`、后端全量 `1798 passed, 28 skipped`，前端与主干 CI 全绿。
  - 边界: 没有模型请求、formal ledger、replacement、backfill 或 v1-v8 改写。

- 2026-07-29 — 预注册 C/C++ 正式分层实验 v1
  - GitHub: Issue #76 / PR #77；本阶段只冻结研究设计，不调用模型、不创建 formal ledger，也不授权 v9/正式采集。
  - 样本框: 从 OSS-Fuzz `08682bfc` 的 1,369 份 metadata 中得到 577 个 C/C++、473 个 GitHub 上游和 182 个静态合格候选；固定 seed 为 CMake/Make/Autotools 各选 10 个，每种 3 small + 4 medium + 3 large，30/30 exact commit 均由 GitHub Git object API 核验可达。
  - 设计: RichLab `gpt-5.5` 与 DeepSeek `deepseek-v4-flash` 各 3 次重复，共 180 个唯一串行 slot；schedule SHA-256 为 `9cfca53bb8c7ab8f07eb5c9a852383eb1877dc377cf56bb834b8eee3587fa469`，JSON 明确 `collection_authorized=false`。
  - 统计: primary 为项目等权的 end-to-end oracle-pass 比例差，使用 30 个 project block 的 exact sign-flip 动态规划与项目 cluster bootstrap；endpoint failure 保留在端到端 estimand 并单列可靠性，不能把 endpoint-free 子集解释为纯模型能力。
  - 网络与预算: 新协议只允许无敏感标识的 access-medium/relay/canary/topology 元数据。按 v8 外推约 2,351.8 万 tokens、25.0 串行小时；1.25 contingency 约 2,939.7 万 tokens、31.3 小时，正式采集必须另建 Issue 并取得用户明确授权。
  - 静态排除: `esp-v2` 的根 Makefile 主 target 实际编译 Go 服务，在任何模型请求前按预注册规则由同层下一哈希候选 `fio` 替换；合并后若再发现静态不兼容必须公开 amendment，正式 ledger 创建后禁止 replacement/backfill。
  - 证据: 预注册/报告 `23 passed`、协议/evidence `278 passed`、后端全量 `1765 passed, 29 skipped`；Ruff、format、内存语法编译、敏感信息扫描、diff 与 0 orphan 通过。
  - 下一入口: 完成 30 个项目的文档级构建路径审计、case-specific 参数/artifact oracle 与正式 manifest/Schema/runner/image/prompt 版本冻结；仍不采集，直到预算与运行 Issue 再获明确确认。

- 2026-07-29 — 生成 C/C++ pilot v8 描述性分析报告
  - 实现: 新增确定性只读分析器、8 个证据拒绝/历史兼容/确定性回归，以及机器可读 JSON 和中文 Markdown 报告；10 条 v8 collection ledger 与 5 条历史 baseline ledger 分开审计，未调用模型、未改写或补跑冻结证据。
  - 结果: v8 仍为 6/10 oracle passed；10/10 hash chain、当前离线 gate 与 cleanup 有效，0 orphan。冻结终态原始 gate 为 9/10，Issue #69 修复后当前重算为 10/10，两种 provenance 同时保留。
  - 描述性口径: RichLab `gpt-5.5` 为 2/5、806,682 tokens、3,642.391 秒；DeepSeek `deepseek-v4-flash` 为 4/5、499,850 tokens、1,365.731 秒。五个自选 case 每 condition 一次且 `formal_comparison_enabled=false`，不得宣称总体模型优劣或显著性。
  - 网络边界: v8 启动前 `network_present`/`endpoint_reachable` 均为 10/10，但 1 个 attempt 出现 endpoint timeout；历史 ledger 没有接入介质元数据，无法区分 Wi-Fi/手机热点、Windows/WSL/Docker、relay、互联网路由与提供商端，归因必须保持 `indeterminate`。
  - 证据: 报告独立复算 JSON/Markdown SHA-256 分别逐字一致；协议/evidence `263 passed`，后端全量 `1750 passed, 29 skipped`，Ruff、format、内存语法编译、diff 和敏感信息检查通过。
  - 下一入口: 预注册约 30 个分层 C/C++ 项目、每 condition 至少 3 次的正式实验，并前置固定删失/重试规则、失败层级、统计方法和不含敏感标识的网络分类元数据。

- 2026-07-29 — 修复 candidate-only 与 clean-replay 离线 gate 重算
  - 根因: `recompute_gates()` 把 submit checks 中的 `clean_replay` 也计入 `candidate_only`，使候选构建已通过但干净重放 SHA-256 mismatch 的 submit 被离线错误重算为 candidate failure。
  - 修复: candidate-only 只聚合候选产物检查，clean replay 继续由独立 replay 事件与 gate 复核；新增 candidate-pass/replay-fail 与真实 candidate-check-fail 两个回归。
  - 冻结边界: 不改写、回填、retry 或 replacement 任一 v8 ledger，也不创建实验 slot；旧 v8 current-tree gate 继续拒绝合法 runner 漂移，并从 `c7977ab7` 读取历史协议 blob 复核原 SHA-256。
  - 证据: 聚焦协议/evidence `255 passed`，后端全量 `1742 passed, 29 skipped`，Ruff/format/内存语法编译通过；10 条 v8 collection ledger 的 hash chain、gate 重算、终态和清理均为 10/10 有效，同目录 5 条历史 baseline ledger 也通过当前只读审计，0 遗留编译容器；v8 冻结 oracle 结果仍为 6/10 passed。
  - 下一入口: 基于冻结 v8 形成描述性研究报告，明确小样本边界与失败分层，再预注册扩大后的正式分层实验。

- 2026-07-29 — 完成双提供商 C/C++ pilot v8 十槽采集
  - GitHub: Issue #68 已完成审计并关闭；10 个 slot 严格按 manifest 交错顺序串行执行，无 retry、fallback、replacement 或 backfill。离线 gate 缺陷转入 Issue #69。
  - 证据: 10/10 ledger hash chain、顺序与终态有效，10/10 session finalize/orphan reconciliation 成功，0 orphan、0 compile/replay 残留容器；191 次模型请求启动、190 次闭合，总计 1,306,532 tokens，实际模型身份始终匹配 condition。
  - 结果: 总体 6/10 passed。RichLab `gpt-5.5` 为 2/5、806,682 tokens；DeepSeek `deepseek-v4-flash` 为 4/5、499,850 tokens。最后一个 DeepSeek slot 的唯一未闭合请求为 timeout，按 `max_retries=0` 原样终结。
  - 失败分层: RichLab `hiredis` 为产物路径 mismatch，`libcheck` 为 post-build reserve/oracle mismatch，`sysstat` 没有满足冻结的 SHA mismatch 负向预期且暴露两处 gate mismatch；DeepSeek 仅 `sysstat` 在 submit 前 endpoint timeout。
  - 解释边界: 这是 5 个自选 calibration case、每 condition 一次，且 `formal_comparison_enabled=false`；不得据 2/5 与 4/5 宣称模型总体优劣或统计显著性。

- 2026-07-29 — 双提供商 C/C++ pilot v8 协议进入主干
  - GitHub: Issue #65 已关闭，PR #66 已 squash 合并为 `main@c7977ab7`；协议分支已删除，主干 Unit Tests 与 Lint Check 全绿。
  - 设计: 保留 v7 的 5 个 exact-commit C/C++ case、镜像、Compose/DooD、Compile Session、clean replay 与 compiler 预算；RichLab `gpt-5.5` 和 DeepSeek `deepseek-v4-flash` 分为两个 condition，共 10 个不可替换、严格串行的交错 slot。
  - 实现: 独立 v8 manifest/Schema/validator；runner 预检两套 credential-env、endpoint 和实际 model config，乱序、前槽未完成、replacement 与损坏 ledger 均在新 ledger 前拒绝。Compose backend dev 镜像补齐 Git，只信任固定只读 `/repo`，Dockerfile 纳入 v8 协议哈希。
  - 证据: 后端全量 `1739 passed, 29 skipped`，Ruff、Schema、Compose、前端 lint/typecheck/build 和真实 WSL2 Compose gate 通过；最终 preflight `ready=true`，0 v8 ledger、0 compile/replay/physical-attempt 容器，未调用模型。
  - 下一入口: v8 采集必须新建独立 Issue 并由用户明确启动；不得把协议合并视为采集授权，也不得 retry、fallback、replacement、补跑或跨提供商池化。

- 2026-07-29 — 双提供商非 pilot 端到端 canary 完成
  - Issue #63 已关闭；入口 PR #64 squash 合并为 `main@54fdf418`。两条件严格各执行 1 次，无 retry/replacement/fallback，两个本地 append-only ledger 的 hash chain 均有效且最终 0 compile/replay orphan。
  - RichLab `gpt-5.5`：95 秒，9/9 模型请求闭合，23,642 tokens，5 个编译链工具调用；唯一 Session 为 completed，固定 commit/CMake、1 个 executable、submit、clean replay、finalize 全部通过。
  - DeepSeek `deepseek-v4-flash`：60 秒，11/11 模型请求闭合，36,503 tokens，7 个工具调用（5 个编译链）；唯一 Session 同样通过完整门禁。单 case 只能证明可行性，不能据此宣称 DeepSeek 更优；v8 将两者分层校准。

- 2026-07-29 — 修复未来 attempt 的 runner 解释器与 evidence 挂载门禁
  - Issue #61 / PR #62 已 squash 合并为 `main@70fe40d6`。新增独立 `runtime-preflight`，验证 LangGraph Compose 身份、可写 Docker socket、后端 venv、必要 runtime import、可写 bind evidence mount 与 output directory 的真实 sentinel 写入/删除；`preflight`/`create-attempt` 要求显式 output directory，launch failure 在 evidence ID 和 ledger 创建前终止。
  - system Python 负例、后端 venv 正例和 mount 外目录负例均按预期返回且 0 ledger/0 sentinel；v1-v7 manifest、Schema、validator、协议哈希和 ledger 未改写，v7 current-tree gate 继续拒绝 post-collection runner 漂移。

- 2026-07-29 — WSL2 Compose 模型出口与多提供商预检进入主干
  - Issue #59 / PR #60 已 squash 合并为 `main@aa200d55`。受限 relay 只绑定私有 Docker bridge，独立 Compose override 保持 v7 冻结基础 Compose 字节不变；本地凭据只进入 Git 忽略 `.env`。
  - RichLab `gpt-5.5`/`gpt-5.4` 与 DeepSeek `deepseek-v4-flash`/`deepseek-v4-pro` 均从 LangGraph 容器通过模型列表、最小对话和强制工具调用；Ready Unit Tests、后端 lint 与前端 lint 全绿。没有重跑、替换或回填 v7。

- 2026-07-28 — C/C++ pilot v7 冻结协议进入主干
  - Issue #56 / PR #57 已 squash 合并为 `main@957fb9e3`。独立 v7 manifest、Schema、validator 和 runner 路由冻结参数前置 gate、四类 compiler 预算与 artifact oracle 差异语义。
  - 预算继续固定为 model turn 36、graph recursion 96、compiler wall clock 900 秒、post-build reserve 120 秒；五个 exact-commit C/C++ case、Compose/DooD、Compile Session、clean replay、0 retries、no fallback 和 Memory/Skills 关闭保持不变。

- 2026-07-27 — artifact oracle 结构化差异进入主干
  - Issue #52 / PR #55 已 squash 合并为 `main@c48a0008`。`run_oracle()` 在不改变既有 pass 判定公式的前提下，输出有界的 artifact identity 与 clean replay type/size/SHA-256/smoke 差异；旧证据缺少逐产物列表时明确 `available=false`。
  - 证据: runner/protocol/evidence `204 passed`、后端全量 `1665 passed, 29 skipped`、真实 Docker 三组 `3 passed`，Ready CI 与主干 Unit/Lint 全绿。没有模型调用、v6 retry/replacement 或 v7 attempt。

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

- 若后续授权 formal v4，必须把 `scripts/forge_formal_collection_v4_runner.py:244` 的 attempt checkpoint 接入真实 provider、Compiler、submit/replay、finalize 和 cleanup 路径，并增加总墙钟取消、Session finalization、orphan reconciliation 的真实 Docker 回归；不能只把 manifest 的授权位改为 `true`。
- 清理与当前源码不一致的后端测试模块引用，例如 `backend/tests/test_aio_sandbox_local_backend.py:1` 和 `backend/tests/test_channels.py:14`。
- 统一 `backend/tests/test_subagent_timeout_config.py:261` 对 `max_turns` 的期望值与当前实现默认值。
- Issue #78 的 30 项目文档级构建路径与 artifact oracle 已实现并通过本地验证；待中文 PR/CI/合并后，再冻结 formal manifest/Schema/runner/image/prompt。任何采集仍须单独 Issue 和用户预算确认。
- 当前 `backend/packages/harness/deerflow/compile/manager.py` 的 lifecycle lock 是进程内锁；部署多个后端进程前，需要改为文件锁/数据库事务或带版本号的 CAS，并增加跨进程竞态测试。

## 已知问题 (Known Issues / Pitfalls)
<!-- 工作中踩过的坑、限制或意外行为。 -->

- 上游仓库已跟踪 parser generator 产物时，空 bootstrap 不保证重放确定性：Git checkout 的 mtime 可能让 Make 在“复用生成文件”和“重新运行 Bison/Flex”之间切换，最终 artifact 路径、类型、大小相同但 build-id/SHA-256 不同。冻结协议应显式运行已审计的 generator 命令，并在 parent wrapper 中用 subshell 隔离 `cd`；不得通过放宽 clean replay SHA-256 verifier 掩盖非确定性。
- 一次性诊断容器若在容器内执行 GitHub fetch，当前网络可能长期阻塞；诊断必须有独立短时限和精确 container ID，超时后按 ID 终止并删除，再核对 compile/replay orphan 为 0。不能把 fetch 阻塞记为 case lifecycle 失败，也不能因此启动 Docker Desktop。
- 真实 Docker gate 不应在测试体内用 `apt-get update` 临时准备单个依赖：本次 OpenH264 gate 在 `mirrors.aliyun.com` 下载完整 index 时耗尽 600 秒，但尚未 clone、build 或进入 lifecycle，不能记为 case 失败。若依赖是单一、架构固定的小包，应在预注册中冻结版本、URL 与 SHA-256，以短 timeout 下载并校验后派生临时 image；parent/arms/replay 共用该 image ID，结束后按 label 和精确 identity 删除。DooD 测试还必须把仓库挂载到与 WSL 宿主相同的 `/mnt/c/...` 绝对路径，并把 `tmp_path` 放在该路径下，不能把测试容器内部 `/tmp` 交给 daemon 当 bind source。

- 版本化 runner 不能把一个候选 runtime 模块同时伪装成 R1 的 `parity` 与 `observability` 接口；静态 adapter 有 `R3ActionPolicy/ObservableRuntimeParityToolAdapter` 不代表它也导出 `FrozenActionPolicy/SerialToolCallMiddleware/RejectionObservationRegistry`。真实执行前必须以零 provider contract test 构造完整 agent 骨架，并把 registry 等可能失败的初始化放入能解除 active experiment 的 `try/finally`；0 model request 的异常必须分类为 mechanism invalid，不能归为 `no_submit`。
- PowerShell 可能误解析传给 WSL Docker CLI 的 Go template（例如 `{{.Server.Version}}`）或混合单双引号的复杂正则，导致只读 gate 在业务逻辑前被拒绝。跨 PowerShell/WSL gate 使用固定 argv 且不传 template；版本检查直接运行 `docker version`，列表检查使用不需要 format 的 `docker ps -aq` / `docker images -q`；敏感扫描拆成简单单引号模式。

- 历史 manifest 会按字节冻结 `scripts/forge_opaque_provenance_runtime_parity_gate.py`、共享 `evidence.py` 和 LLM/tool-error middleware 等父组件；即使行为兼容，原地增加异常元数据、Schema 或仅运行 Ruff 格式化也会让旧协议 current-tree gate 报 runtime drift。新增 instrumentation 必须放入新的版本化 adapter/companion event，并用完整 backend CI 确认所有冻结文件零差异。
- 真实 lifecycle capture 的 evidence Schema 强制要求 `submit_attempt_id`；只记录 classification/failure ID 会在 environment freeze 前 fail closed。新 gate 应直接从同一 `failure.recorded` payload 复制该 ID，并先做 Schema 级静态断言。
- Budget checkpoint 中“请求容量”与“实际请求数”是两个概念：原型要求 `limits.provider_requests >= 1`，零 provider gate 应保持正容量但让 consumed/external counts 为 0，不能把容量 0 误写成零调用证明。
- `sh -c` wrapper 的 role parser 能递归看到 configure/build，但 `_command_contains_arguments` 只看到整段 inner command token；若 policy 冻结非空 CMake 参数，会额外产生 `cmake_arguments_not_observed`。研究 opaque provenance 时应把非 estimand 参数约束显式冻结为空，并从 authoritative `session.verification.checks` 核对 failure 列表，而不能只看 primary classification。

- 冻结 manifest 中的容器路径不能用宿主 `Path` 再 `str()` 序列化；Windows 会生成反斜杠而 WSL/Linux 重算为正斜杠，导致跨环境 identity 漂移。协议使用固定 POSIX 字符串，`Path` 只用于运行时访问。
- PowerShell 调 WSL 的 `docker info --format` 时，含 `|` 的 Go template 可能失去参数引号并被 Bash 当作管道。daemon 摘要统一使用无特殊字符的 `docker info --format json`，再在 PowerShell 侧解析；不要继续调试多层模板引号。

- `ExperimentPolicy.required_system_packages` 非空时，成功命令必须以生产契约角色 `dependency_setup` 记录；自定义 manifest 写成 `dependency` 会让 submit 正确归类为 `dependency_setup_not_observed`，掩盖预期的 verifier failure。环境查询也不能代替缺失依赖安装：`libcheck` 必须实际安装 `texinfo`，否则 parent build 在 `makeinfo` 处退出 127。
- 2026-08-29 门禁期间 Ubuntu `docker.service` 曾收到一次 systemd 正常停止信号并自动恢复，来源未能从 Docker journal 归因；每个重型 Docker gate 前仍应重新执行 `scripts/require-ubuntu-native-docker.sh`，但不得自行重启 daemon 或切换 Docker Desktop。

- Windows bind/DrvFS 目录大小写不敏感；上游若跟踪 `BUILD`，CMake `-B build` 会解析到同一普通文件。checkpoint canary 使用 `.forge-cmake-build`，并必须在真实 Compose `/workspace/.compile-sessions` 挂载上做 parity gate，不能再用 WSL ext4 `tmp_path` 代替。
- Issue #149 runner 和测试的 SHA-256 已冻结在授权 manifest。跨阶段修复必须新增版本化 adapter/test，不能原地修改冻结文件或更新旧 manifest hash；后续 provider 运行还需要独立 amendment identity 与新授权。
- Windows 工作树中的 `backend/.venv` 是 Linux 虚拟环境布局，没有 `Scripts/python.exe`；不要直接把它当 Windows venv，也不要省略 PowerShell 相对可执行路径所需的 `./`。先用 `Get-Command`/`Test-Path` 确认，再固定通过 WSL 调用 `./backend/.venv/bin/python` 和 `ruff`。
- Compose/DooD checkpoint 同时存在服务容器路径 `/workspace/.compile-sessions/...` 与 Docker daemon 可见的 WSL 宿主路径 `$HOST_PROJECT_ROOT/.compile-sessions/...`；snapshot bind 必须显式做相对路径转换，不能把容器路径原样交给 daemon。
- controlled parent 通过脚手架直接执行 build 时不会自动进入 bound tool 的 post-build phase；派生 arm 前必须持久化成功 build 的 `supporting_command_id`、开始时间和剩余命令预算，否则模型恢复 artifact 后无法自动触发 submit/clean replay。

- `CompileDockerRuntime.create_container()` 的 bind source 不会代替测试创建 `session.leadagent_repo_dir`；若目录缺失，容器能创建但首次以 `/workspace/repo` 为 cwd 的 exec 会在 OCI 层失败。真实 Docker fixture 必须在 create 前执行 `Path(session.leadagent_repo_dir).mkdir(parents=True, exist_ok=True)`；这种失败发生在 fault、submit、checkpoint 和 replay 前，不能计入机制门禁结果。
- WSL 冷启动或手动启动 `docker.service` 后，daemon 恢复已有容器可能需要 5-10 秒；启动命令返回后应等待 `systemctl is-active docker.service` 为 `active` 再运行正式 gate，不能把 `activating` 窗口误判为永久失败，也不能切换 Docker Desktop。
- Docker 29 使用 `docker commit --no-pause`，旧的 `--pause=false` 会输出弃用提示并污染严格 SHA 解析。恢复后的 `0640 root:root` 文件由只读 helper tar 观测，不能为了测试方便 `chmod/chown` 被测目录。
- 一次性正式入口必须先用最终完全相同的 `/app/backend/.venv/bin/python` 完成零请求 import、runner `--help` 与挂载内 preflight；双 provider canary 外层等待不得短于 700 秒。manifest 声明 300 秒不等于模型对象已生效，必须在请求前验证模型及底层 client 的有效 timeout/retry；调试级短超时、系统 `python` 和仅核对 endpoint 的 preflight 都不能作为放行依据。
- Windows `docker` CLI 的 `desktop-linux` context 只反映 Docker Desktop daemon，不能据此判断 Forge 状态。Forge 容器实际属于 WSL2 Ubuntu 原生 `dockerd`；所有项目 Docker 命令必须先通过 `scripts/require-ubuntu-native-docker.sh`，并从 `wsl.exe -d Ubuntu` 或该发行版内执行。门禁失败时请求用户恢复服务，不得启动 Docker Desktop 作为回退。
- LangGraph 容器内 `/repo` 是只读挂载。可在容器中使用 Ruff `--check --no-cache`，但不能直接格式化文件；写入格式化必须在可写工作树中使用相同 `backend/ruff.toml`，不要修改挂载权限或重建服务来绕过只读边界。

- Compose 同时把脚本挂到 `/app/scripts`、完整仓库挂到 `/repo`；仅设置 `FORGE_REPO_ROOT=/repo` 不足以修复版本化协议链，因为先导入的父 runner 会把 `/app` 根协议放入 `sys.modules`。runtime adapter 必须先从 `/repo/scripts` 导入协议链，再导入父 runner；preflight 还必须使用 `/app/backend/.venv/bin/python` 和 `/workspace/.compile-sessions` 子目录，否则解释器、runtime import 与 evidence 持久化 gate 会按设计拒绝。
- 历史 formal manifest 应冻结当时的 runner SHA，但共享基础 runner 会由后续版本继续演进；回归测试应直接断言历史 manifest 中的旧 identity 保持不变，并由新版本 manifest 绑定当前 runtime，不能要求工作树中的共享 runner 永远等于最早候选字节。旧协议遇到 current-tree runtime 漂移时拒绝执行是预期 gate。
- 后端 CI 从 `backend/` 运行 `uvx ruff` 并加载 `backend/ruff.toml`（当前行宽 240）。对 `backend/tests/` 显式传 `backend/pyproject.toml` 会使用不同格式规则，可能出现本地 format check 通过但 CI 要求反向格式化；本地复核必须使用 `backend/ruff.toml` 或从 `backend/` 工作目录运行与 CI 相同的命令。
- 修改 `.env` 后仅 `docker compose restart` 不会重新加载环境，必须 recreate Gateway/LangGraph。直接调用开发 Compose 还必须显式提供 `DEER_FLOW_ROOT`；否则在配置插值阶段退出。优先使用 `scripts/docker.sh`，定向 recreate 时传完整 WSL 绝对路径，避免 PowerShell 提前展开 `$repo`。
- formal canary 的 endpoint preflight 失败发生在模型调用和报告创建之前；真实 provider 请求超时则会留下不可变 canary 报告。恢复前必须分别核对 report 数、formal JSONL 数和 orphan 数，不能把“没有报告”误写成模型失败。
- 单次成功或超时不能证明某个 RichLab 模型稳定可用。本次同一路径中 `gpt-5.5` 可在 3.8–5.4 秒完成原始文本/工具请求，也可在 LangChain canary 中 121 秒超时；`gpt-5.4` 同样出现一次 120 秒文本超时后 3 秒工具成功。保持模型身份冻结并按请求级 endpoint failure 记录。
- 新版本 runner adapter 不应修改共享历史 runner 模块。authorized v3 使用私有加载的基础 runner，避免 v2/v3 adapter 在同一 pytest 进程中因导入顺序互相覆盖；历史 adapter 的逆序组合仍可能暴露旧污染，但正常 CI 顺序和 authorized v3 隔离回归已通过。

- GitHub 的 API 与 Git HTTPS 是独立网络通道：`api.github.com` 正常不代表 Windows Git 能访问 `github.com:443`。本机 Windows Git 未使用 WSL 的代理环境，push/ls-remote 会超时或连接重置；仓库 push 应直接运行 `pwsh -NoProfile -File scripts/push-via-wsl.ps1`，不要先重复 Windows `git push`。GitHub App 写权限 403 也属于独立权限边界，Issue/PR/评论等写入直接使用已认证 Windows `gh`。
- DooD preflight 只验证 mount destination、bind 类型和可写性仍不够；错误启动可能把 `/.compile-sessions` 挂到正确的容器 destination。必须同时验证 mount `Source == DEER_FLOW_HOST_WORKSPACE_ROOT/.compile-sessions`，并拒绝缺失、相对路径、根目录和重复 evidence mount。
- 多版本 runner adapter 在同一 Python 进程中共享底层模块；直接覆写 `protocol_formal_collection` 会让测试收集顺序改变旧 schema 的可识别性。新版本应增加 schema dispatch，并只适配新增 policy 字段，不能替换冻结版本的全局协议身份。
- PowerShell 调用 `gh` 时，正文中的 `\n` 不会自动变成换行，可能把字面反斜杠写进 squash/PR body。所有 GitHub 多行正文使用 PowerShell here-string 或 `--body-file`，提交后再读取远端正文确认。
- 在同一 Python 进程中为每个 slot 单独调用 `asyncio.run()` 会关闭事件循环，但 provider 的异步 HTTP 资源可能延迟到下一 slot 才清理；典型现象是首个调用成功、第二个在 3–18 ms 内 `APIConnectionError`。正式串行 batch 必须用一个 `asyncio.Runner` 复用同一事件循环，不能把这种立即失败归因于普通跨境网络超时。
- 正式 policy 即使声明 `memory_enabled=false`，首次模型连接失败时 state 尚无 `compile_session_id`，通用 MemoryMiddleware 仍可能排队并调用默认模型。冻结组件不能原地修改；新版本 runner 应在整个 agent stream 期间显式关闭并最终恢复全局 memory 配置，避免实验外 token 与日志污染。
- 冻结 manifest 的 generator 会对当前 runtime component 重新取 hash；直接修改 v1 绑定的 `operations.py` 等共享文件会让旧 manifest 机械再生成测试失败。跨阶段修复必须放进新的版本化 runner/protocol，旧 runner、manifest、Schema 和 ledger 保持逐字不变。
- `config-upgrade` 集成测试会在每个 case 内调用 `uv run`；仅迁移 `UV_CACHE_DIR` 仍可能因冷同步超过固定 60 秒，复用已同步 `.venv` 时还需设置 `UV_NO_SYNC=1`。本次由权限错误转为冷下载超时后，以该变量单独复核为 `4 passed`。
- 当前 WSL2 仅约 7.7 GiB 内存时，Next.js 16/Turbopack 的无缓存 production build 即使停止全部开发服务、给 Node 4 GiB 上限，仍可能把 WSL 推到约 7 GiB 后被 OOM kill；不要把无错误栈的 `ELIFECYCLE` 直接归因于前端代码，优先用 GitHub CI 或提高 WSL 内存后复核。
- 只读一次性后端测试容器必须把 `PYTHONPATH` 指向 `/repo/backend/packages/harness`，否则会导入镜像内旧源码；`config-upgrade` 还要把 `UV_CACHE_DIR`/`UV_PROJECT_ENVIRONMENT` 指向可写路径。冷缓存首次同步依赖可能超过该测试固定的 60 秒，应在缓存环境单独复核，不能误判为业务回归。
- 手机热点下 `github.com` 网页/Git 通道可能在 8 路并发时 76/76 请求均连接超时，而 `api.github.com` 串行请求仍可稳定核验 77 条证据；网络诊断必须区分主机、通道和并发度，证据 000/timeout 不能直接当作文件 404。
- 后端全量测试从只读 `/repo` 运行时，`config-upgrade` 需要单独挂载有效 `/repo/backend/.venv`，live upload 需要 tmpfs `/repo/backend/.deer-flow`；否则会在业务断言前产生只读文件系统伪失败。
- uWebSockets 同时存在 Windows NMake `Makefile` 和 Linux/macOS `GNUmakefile`；Linux C/C++ 协议不能只凭文件名优先级选择 `Makefile`，且该提交的 `capi`/`all` 分支明确为空操作，必须使用有实际产物的 GNU Make `examples` 路径。
- OSS-Fuzz `project.yaml language` 与根 Makefile 只能建立候选样本框，不能单独证明上游 primary build path；例如 `esp-v2` 声明 C++ 且有 Makefile，但主 build target 编译 Go 服务。正式 protocolization 必须在结果盲态下做文档级 C/C++ 构建路径审计，静态排除/替换要在任何模型请求前公开冻结。
- GitHub GraphQL 同时查询 40 个大型仓库的 root tree 会返回查询复杂度/参数拒绝；降为每批 20 个后 452 个仓库稳定完成。不要把该服务端查询限制误判为本机热点超时。
- 临时 `/tmp` 文件不会自动继承仓库格式器上下文；本仓库实际 formatter 使用 120 字符行宽。格式化拷贝文件时应显式传 `--line-length 120`，再从真实 `/repo` 路径执行 `ruff format --check`。
- 确定性报告不能依赖 Python 字典插入顺序：JSON 使用 `sort_keys=True` 后重新载入会改变嵌套 failure-domain 顺序；Markdown renderer 必须按显式固定域顺序遍历，并用“直接生成 vs JSON 重载复算”的哈希相等回归保护。
- 历史实验没有记录本机接入介质时，当前改用手机热点不能反推旧 timeout 的原因；只能将其归为端到端 endpoint-path failure、归因 `indeterminate`。新协议可记录 `wired/wifi/mobile_hotspot/unknown`、relay 开关、canary 延迟和网络拓扑分类，但不得记录 SSID、IP、运营商账户或凭据，也不得回填冻结 ledger。
- WSL 用户目录中的 `.local` / `.cache/uv` 可能由旧容器以 root 创建，原生 WSL 执行 `uv` 会报 `Permission denied`；不要改写权限掩盖来源，测试可把 `UV_CACHE_DIR`、`UV_PYTHON_INSTALL_DIR` 与 `UV_PROJECT_ENVIRONMENT` 指向用户可写的独立目录。
- Docker Hub 匿名 token 与 Ubuntu archive 在当前网络下可能分别超时或返回 502；本机可从 Canonical 官方 Amazon ECR 拉取同源 Ubuntu 基础镜像并改回本地 `ubuntu:24.04` 标签，apt 构建可显式传可信镜像站，但不得把临时镜像源写进冻结实验协议或伪装成既有 image ID。
- 协作语言约定：后续 GitHub Issue、Pull Request、评论、评审说明和提交说明默认使用中文；分支名、代码标识、命令和必要技术术语继续遵循仓库的 ASCII/既有命名规范。若外部协作明确要求英文，先向用户确认。
- PowerShell -> WSL -> `bash -lc` 的多层命令可能提前展开临时 `$repo` 变量，使 Docker bind mount 退化为 `/frontend/...`；一次性容器优先传完整 WSL 绝对路径，启动失败后先按固定名称清理并确认无残留。
- Docker Desktop 与 WSL 原生 Docker Engine 是两个独立 daemon，镜像、网络和容器不共享；Forge 命令必须始终在同一套 daemon 上执行。
- WSL 的 `127.0.0.1` 代理不能直接传入 Docker build；编译镜像代理必须使用容器可达地址。
- Windows 代理只监听 loopback 时，WSL2 Docker 的 `host.docker.internal` 只到 Docker/WSL 网关，并不会自动进入 Windows loopback。模型请求必须通过仅绑定 Docker bridge 的受限 relay；不要让代理软件监听 `0.0.0.0` 或局域网地址。模型运行时代理使用独立 Compose override，不能改写 v7 冻结的基础 Compose 文件。
- Compose 内运行正式 benchmark runner 必须显式使用 `/app/backend/.venv/bin/python`；容器 system Python 可能足以导入最小 evidence 模块，却缺少完整 `deerflow.client` 运行时。权威 output directory 必须显式位于 `/workspace/.compile-sessions` 的可写 bind mount，不能使用只读 `/repo` 或仅凭目录可写性推断宿主可见。
- Runtime preflight 的 output directory 必须是 `/workspace/.compile-sessions` 的子目录，不能直接使用 mount 根；当前正式 evidence 目录为 `/workspace/.compile-sessions/benchmark-evidence`。
- `candidate_only` 与 `clean_replay` 是正交 gate；离线重算不能对 candidate-only 使用包含 `clean_replay` 的全部 checks。v8 sysstat 已由 Issue #69 固化为回归入口。
- Compiler 的 900 秒 wall-clock 与 ledger 首尾总时长不是同一口径；模型编排、submit/replay、finalize 和 cleanup 可使 physical-attempt 总历时超过 900 秒，报告时必须分开。
- 后端全量 Ruff 当前有 4 个本次改动之外且与 `origin/main` 相同的既有错误：`scripts/check.py` 的 3 个 UP045 与 `scripts/forge_benchmark.py` 的 1 个 I001；本次改动文件的 Ruff check/format 已通过。
- 成功 bash 记录只是候选 recipe；失败命令可能留下持久副作用。进入研究基线前必须在新容器与空 `/workspace`、`/artifacts` 中实际 replay，不能把 `repro_bundle` 生成成功等同于独立复现成功。
- Windows 挂载目录在编译镜像中可能触发 Git `dubious ownership`；replay 初始化仓库后必须把 `/workspace/repo` 加入 `safe.directory`。
- 不要把含 `$()`、重定向和多层引号的后验校验直接嵌进 PowerShell → WSL → `docker run ... bash -lc`；参数可能被中间层重解释。应先单独运行 `bash /repro/build.sh` 获取退出码，再用独立命令检查类型、输出与哈希。
- PowerShell → WSL 的审计命令也不要嵌套 `python -c` 与多层单双引号；即使前置生成已成功，末尾展示命令仍可能因引号截断让整段汇总失败。应把 manifest 校验、哈希显示和 PowerShell 文件审计拆成固定参数的独立命令。
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
