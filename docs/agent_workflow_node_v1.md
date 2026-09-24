# Agent Workflow Node v1

`agent_workflow_node_v1` 是自动化编译实验的显式运行路径。它复用现有 Compile Session、Compiler 提示词和 `run_container_bash`，并把候选冻结与外部确定性评测分开。

现有 Lead Agent + Compiler 仍是默认产品路径，`submit_build_result` 的 artifact verification、repro bundle 和 clean replay 语义保持不变。新路径只有调用 `deerflow.compile.run_agent_workflow_node_v1(...)` 时才会启用。

## Phase 2 能力

- 调用方必须显式传入 `AgentBuildNodeInput`、authoritative `CompileSession`、对应的 `CompileSessionManager` 和 `BaseChatModel`。运行时不会自行选择或创建 provider。
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

## 当前边界

Phase 4 是研究路径的集成门禁，不自动接入现有 Lead + Compiler 产品路径，也不运行 Phase 5 的六项目内部校准或写正式实验 evidence。调用方仍不得把 `node_status="submitted"` 解释为构建已验证；只有外部 evaluator 的 S0-S5 结果可以形成严格成功结论。

主要实现位于：

- `backend/packages/harness/deerflow/compile/agent_workflow_runtime.py`
- `backend/packages/harness/deerflow/compile/agent_workflow_node.py`
- `backend/packages/harness/deerflow/compile/agent_workflow_schemas.py`
- `backend/packages/harness/deerflow/compile/external_evaluator.py`

Phase 1-3 回归测试使用假 `BaseChatModel` 和本地临时 Session，不调用真实 provider 或 Docker：

```bash
cd backend
UV_CACHE_DIR=/home/yiwei/.cache/uv-user PYTHONPATH=. uv run pytest \
  tests/test_agent_workflow_runtime.py \
  tests/test_agent_workflow_node_contract.py \
  tests/test_external_evaluator.py \
  -o cache_dir=/home/yiwei/.cache/pytest-forge
```
