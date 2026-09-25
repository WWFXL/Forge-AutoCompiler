# Agent Workflow Node v1

`agent_workflow_node_v1` 是自动化编译实验的显式运行路径。它复用现有 Compile Session、Compiler 提示词和 `run_container_bash`，并把候选冻结与外部确定性评测分开。

现有 Lead Agent + Compiler 仍是默认产品路径，`submit_build_result` 的 artifact verification、repro bundle 和 clean replay 语义保持不变。新路径只有调用 `deerflow.compile.run_agent_workflow_node_v1(...)` 时才会启用。

## Phase 2 能力

- 调用方必须显式传入 `AgentBuildNodeInput`、authoritative `CompileSession`、对应的 `CompileSessionManager` 和 `BaseChatModel`。运行时不会自行选择或创建 provider。
- 首次模型请求会收到冻结 target ID、artifact 类型与路径规则、functional oracle 引用、operation policy 和 initial observation；项目差异通过节点输入表达，不写入公共 Compiler prompt。
- Agent 只获得绑定到当前 Session 的 `run_container_bash` 和版本化 `submit_candidate_v1`。模型调用强制设置 `parallel_tool_calls=False`。
- `submit_candidate_v1` 只校验并冻结候选，不执行 verifier、repro bundle 或 clean replay。候选必须引用当前 Session 中唯一、已完成、成功且顺序有效的 command，并且 artifact 必须是 `/artifacts` 对应宿主目录内的普通非符号链接文件。
- accepted Submit 会立即停止 Agent 循环。未 Submit、预算耗尽、取消和节点错误进入独立终态；finalizer 失败记录为 secondary failure，不覆盖首个终止原因。
- 节点输入和候选使用 create-once JSON 文件。模型请求、工具调用、新 command、artifact observation、候选提交和终态写入独立 hash-chain JSONL ledger。

节点目录位于 Compile Session 下：

```text
agent-workflow/<attempt_id>/
├── input.json
├── candidate.json    # 仅 accepted Submit 后存在
├── events.jsonl
└── evaluations/<evaluation_id>/
    ├── events.jsonl
    ├── failure.json  # 仅 evaluator 自身异常时存在
    ├── result.json
    ├── summary.json
    └── oracle/
        ├── stdout.log
        └── stderr.log
```

## Phase 3 外部 Evaluator

- `run_external_evaluator_v1(...)` 读取冻结候选和 authoritative Compile Session，先离线复算 S0 身份/生命周期与 S1 命令证据，再通过可注入 backend 判定 S2-S5。
- `ForgeCompileEvaluationBackend` 复用现有 artifact verifier、replay recipe、provenance 检查和 clean replay。S3 oracle 由冻结 registry 选择；相对可执行文件必须保留显式 `./binary` 语义。
- 主要终点 `strict_reproducible_build_success` 只有在 S0-S5 全部通过时成立。bitwise SHA-256 一致性单独记录，不会在 task contract 未要求时覆盖功能重放结果。
- Agent 的 `agent_summary`、`known_limitations` 或自报成败不参与各层判定。每层只保存稳定 reason code 和可复核 evidence reference。
- evaluator ledger 的首 hash 接到 Phase 2 节点 ledger 终点。异常会形成 create-once `failure.json`、失败 ledger 终态、`result.json` 和 `summary.json`，不继续追加普通评测事件。
- 每次修订使用新的 `evaluation_id`，旧目录保持只读。`adjudicate_external_evaluations_v1(...)` 按冻结 task 顺序选择定向 replacement，并拒绝 commit、build system、candidate 或节点输入/结果身份漂移；evaluator 版本和规则可以随修订变化。

## Phase 4 零 Provider 集成门禁

`backend/tests/test_agent_workflow_phase4_docker.py` 使用注入的确定性 `BaseChatModel` 和真实 Docker Compile Session，覆盖：

- 由临时本地 Git daemon 提供 exact-commit CMake、Make、Autotools 最小仓库；compile 与 clean replay 容器读取同一源码身份，不依赖 GitHub 出口。
- 真实 `run_container_bash` command evidence、`submit_candidate_v1` candidate freeze、S0-S5、功能 oracle、clean replay、finalize 和 cleanup。
- no-submit、功能保持但 size/SHA-256 不一致的 replay、evaluator exception、cancel、timeout 和 cleanup failure/retry。
- 每轮门禁前后检查 Forge managed container、paused managed parent 和 managed image 均为 0。
- provider model factory 被显式禁用；门禁不激活 experiment policy，不读取 provider credential，也不创建正式 attempt/evidence。

运行前需要可用的 Docker daemon、`/var/run/docker.sock` 和 `autocompiler:gcc13` 镜像：

```bash
cd backend
FORGE_RUN_AGENT_WORKFLOW_PHASE4_DOCKER=1 \
  UV_CACHE_DIR=/tmp/forge-phase4-uv-cache \
  PYTHONPATH=. uv run pytest \
  tests/test_agent_workflow_phase4_docker.py -p no:cacheprovider -v
```

## Phase 5 六项目内部校准候选

Issue #289 冻结 CXXCrafter Stage B 的 `yyjson`、`cppitertools`、`openh264`、`uwebsockets`、`c-ares` 和 `libass` 六项目身份、target、oracle、顺序、预算与停止规则。候选 manifest 的 canonical SHA-256 为 `303b41c0ee95c4732eb9388a39176789064e131c19217632175fa19e1526434f`。

- 历史只读 fixture 绑定原综合裁决 SHA-256，独立报告 generated `6/6`、submitted `4/6`、strict S0-S5 `6/6` 和 bitwise `5/6`；仅 uwebsockets 选择 evaluator v3 定向修订。
- 新 evidence 根与历史 CXXCrafter evidence 分离；历史 outcome 不导入 Phase 5 方法结果。
- manifest、Schema、protocol 和 candidate runner 均为确定性文件。当前所有 provider、credential、Docker、evidence 和 formal attempt 授权为 false，model token 授权为 0。
- `reachability` 和 `batch` 在读取 credential 或创建模型前硬拒绝。合并后必须派生 authorized amendment，冻结 release commit 和完整 image ID，才可开始真实校准。

离线验证不会调用 provider、读取 credential、启动 Docker 或写 experiment evidence：

```bash
cd backend
UV_CACHE_DIR=/tmp/forge-phase5-uv-cache uv run python \
  ../scripts/forge_agent_workflow_stage_b_calibration_protocol.py validate
UV_CACHE_DIR=/tmp/forge-phase5-uv-cache uv run python \
  ../scripts/forge_agent_workflow_stage_b_calibration_runner.py preflight
```

## 当前边界

Issue #291 后续以独立 identity 完成 v2 审计、evaluator v3、Phase 5 v3/v4 和 v5 定向重评。v5 授权 manifest canonical SHA-256 为 `69f3a363d686365142152fbb32179c1d94e2870501a94abb02a6cd0737514c85`，正式运行绑定 `main@1d5107e8`，仅重新执行 `uwebsockets`。唯一 reachability 使用 `deepseek-flash`，记录 1 个请求、58 tokens；正式任务生成并提交候选，S0-S5 全部通过，清理后为 0 managed resources。

`uwebsockets` 的功能 service probe 和 clean replay 均通过，但 `uSockets/uSockets.a` 的 size/SHA-256 不一致，因此 `bitwise_reproducible=false`。这不覆盖当前任务合同的功能重放结论：`strict_reproducible_build_success` 按预注册定义由 S0-S5 决定，bitwise 一致性作为独立指标记录。`HelloWorld` 在 clean replay 中保持字节一致。

最终裁决只读组合 v3 的 `yyjson`、`cppitertools`、`openh264`，v4 的 `c-ares`、`libass`，以及 v5 的 `uwebsockets`。六项均满足候选提交、S0-S5、严格成功、cleanup 和 0 managed resources，固定证据哈希全部通过，因此 Stage C decision 为 `stage_c_authorized=true`、`stage_c_execution_started=false`，下一动作是设计 Stage C 协议。该结论仅用于跨 run 工程准入，不能表述为一次新的六项目同条件实验或无偏成功率。

历史失败 batch、reachability、task result 和 evidence 均保持只读，不允许 retry、replacement、backfill 或覆盖。该研究路径仍不自动接入现有 Lead + Compiler 产品入口；调用方不得把 `node_status="submitted"` 单独解释为构建已验证。

主要实现位于：

- `backend/packages/harness/deerflow/compile/agent_workflow_runtime.py`
- `backend/packages/harness/deerflow/compile/agent_workflow_node.py`
- `backend/packages/harness/deerflow/compile/agent_workflow_schemas.py`
- `backend/packages/harness/deerflow/compile/external_evaluator.py`
- `scripts/forge_agent_workflow_stage_b_calibration_authorized_protocol.py`
- `scripts/forge_agent_workflow_stage_b_calibration_authorized_runner.py`
- `scripts/forge_agent_workflow_stage_b_calibration_result.py`
- `scripts/forge_agent_workflow_stage_b_phase5_v5_remediation_authorized_protocol.py`
- `scripts/forge_agent_workflow_stage_b_phase5_v5_remediation_authorized_runner.py`

Phase 1-3 回归测试使用假 `BaseChatModel` 和本地临时 Session，不调用真实 provider 或 Docker：

```bash
cd backend
UV_CACHE_DIR=/home/yiwei/.cache/uv-user PYTHONPATH=. uv run pytest \
  tests/test_agent_workflow_runtime.py \
  tests/test_agent_workflow_node_contract.py \
  tests/test_external_evaluator.py \
  -o cache_dir=/home/yiwei/.cache/pytest-forge
```
