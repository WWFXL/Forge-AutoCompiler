# Agent Workflow Node v1

`agent_workflow_node_v1` 是自动化编译实验的显式运行路径。它复用现有 Compile Session、Compiler 提示词和 `run_container_bash`，但把候选冻结与最终验证拆开，供后续外部 evaluator 使用。

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
└── events.jsonl
```

## 当前边界

Phase 2 只实现 Agent 运行与候选冻结。外部 evaluator、S0-S5 综合判定、正式 Docker 运行和实验 evidence 不在本阶段内。调用方不得把 `node_status="submitted"` 解释为构建已验证或 Session 已完成。

主要实现位于：

- `backend/packages/harness/deerflow/compile/agent_workflow_runtime.py`
- `backend/packages/harness/deerflow/compile/agent_workflow_node.py`
- `backend/packages/harness/deerflow/compile/agent_workflow_schemas.py`

回归测试使用假 `BaseChatModel` 和本地临时 Session，不调用真实 provider 或 Docker：

```bash
cd backend
UV_CACHE_DIR=/home/yiwei/.cache/uv-user PYTHONPATH=. uv run pytest \
  tests/test_agent_workflow_runtime.py \
  tests/test_agent_workflow_node_contract.py \
  -o cache_dir=/home/yiwei/.cache/pytest-forge
```
