# Agent Workflow Runtime v3

Runtime v3 在 `submit_candidate_v1` 的 create-once candidate 持久化之前运行零 Provider verifier。它解决 Stage C v6 中结构和功能缺陷反馈过晚的问题，但不改变 external evaluator v4 的最终裁决权。

## 冻结前门禁

每次提交按以下顺序执行：

1. 复用 Runtime v2 的 Session、命令证据和 required artifact 校验。
2. 遍历完整 `/artifacts`，拒绝符号链接、特殊文件、不可读文件和零字节文件，并按内容分类 compiled artifact。
3. 拒绝 candidate 未声明的 executable、shared library、static library 和 object。
4. 要求 `target_mapping` 只包含节点合同中的唯一 `target_id`，且目标路径已声明、类型允许并匹配冻结路径模式。
5. 通过显式注册的 `FunctionalOracleSpec` 运行 system-owned oracle。只有结构检查全部通过才运行 oracle。
6. 全部门禁通过后才创建 candidate 文件和 submission identity。

拒绝不会终止 Agent。Agent 可以根据 `rejection_details` 在同一 attempt 内修复 staging 或 target mapping 后重新提交。每项 evidence 最多返回 12 条排序去重后的路径或值，同时保留 `total_count` 和 `truncated`，不会返回 oracle 原始输出；功能失败只返回 command identity、退出状态及 stdout/stderr SHA-256。

## 调用合同

调用方必须提供与 `target_contract.functional_oracle_ref` 精确匹配的受信 registry：

```python
result = await run_agent_workflow_node_v3(
    node_input=node_input,
    session=session,
    manager=manager,
    model=model,
    oracle_registry={oracle_spec.oracle_ref: oracle_spec},
)
```

缺少或 identity 不匹配的 oracle 会在 Node 启动前拒绝执行。Runtime v3 与 v2 共享串行绑定锁，避免两个版本同时修改 v1 的运行时绑定。

## Token 与权威边界

`max_recorded_tokens=None` 表示不设置 token 总上限；每次模型请求仍分别记录 input、output 和 total token。pre-freeze verifier 与 system-owned oracle 不发起 Provider 请求。

candidate 冻结后，external evaluator v4 仍独立运行 S0-S5、功能 oracle、clean replay 和 delivery 比较。pre-freeze 通过只表示 candidate 可以冻结，不表示实验成功。

## 验证

单元门禁覆盖 Stage C v6 的四类失败形状以及同 attempt 修复后重提：

```bash
cd backend
PYTHONPATH=. uv run pytest tests/test_candidate_prefreeze_verifier.py -q
```

真实 Docker lifecycle 门禁使用确定性本地模型，不构造 Provider client；它依次验证 broad delivery、错误 target mapping、缺失 header closure、修复后冻结、evaluator v4 独立复算、bitwise replay、finalize 和 0 managed orphan：

```bash
cd backend
FORGE_RUN_PREFREEZE_DOCKER=1 PYTHONPATH=. uv run pytest tests/test_candidate_prefreeze_verifier_docker.py -q
```
