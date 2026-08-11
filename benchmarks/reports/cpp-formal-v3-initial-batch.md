# Forge C/C++ formal v3 首批描述性审计报告

> 状态：预算边界停止后的冻结描述性复核；不是模型总体排名。

## 摘要

- 首批完成 7/10 个授权 slot，停止原因为 `recorded_token_boundary_reached`；slot 8-10 未创建。
- Oracle 通过 4/7；ledger hash chain、离线 gate、Session finalization 与 cleanup 均为 7/7，orphan=0。
- 记录 1,700,577 tokens；边界 1,633,165，完成中的 slot 使最终值越界 67,412，随后未创建下一槽。
- 双 provider canary 选用 `provider_canary_8599bcf904ce4ccb8a6c113f19701ec4`；正式批次请求闭合 195/195，其中完成 194、失败 0、取消 1。

## Condition 汇总

| Condition | Oracle | Attempts | Requests closed/started/failed/cancelled | Tokens | Compiler calls | Wall time (s) |
|---|---:|---:|---:|---:|---:|---:|
| `richlab-gpt-5.5` | 2/3 | 3 | 36/36/0/0 | 205,784 | 4 | 1505.264 |
| `deepseek-v4-flash` | 2/4 | 4 | 159/159/0/1 | 1,494,793 | 10 | 4956.297 |

## 每个 slot

| # | Case | Condition | Oracle | Tokens | Wall time (s) | Compiler calls | Submit | Replay | Failures |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `cppitertools` | `richlab-gpt-5.5` | pass | 40,530 | 250.260 | 1 | 1 | 1/1 | - |
| 2 | `cppitertools` | `deepseek-v4-flash` | pass | 61,581 | 149.418 | 1 | 1 | 1/1 | - |
| 3 | `janet` | `deepseek-v4-flash` | pass | 56,434 | 178.666 | 1 | 1 | 1/1 | - |
| 4 | `janet` | `richlab-gpt-5.5` | pass | 37,235 | 217.886 | 1 | 1 | 1/1 | - |
| 5 | `open62541` | `richlab-gpt-5.5` | fail | 128,019 | 1037.118 | 2 | 3 | 0/4 | agent_tool:compiler_wall_clock_timeout<br>submit_replay:size_mismatch<br>submit_replay:size_mismatch<br>submit_replay:size_mismatch<br>completion:experiment_failed |
| 6 | `open62541` | `deepseek-v4-flash` | fail | 764,048 | 1387.455 | 4 | 8 | 0/4 | agent_tool:graph_recursion_limit<br>agent_tool:post_build_reserve_exhausted<br>submit_replay:size_mismatch<br>submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:size_mismatch<br>submit_replay:size_mismatch<br>submit_replay:size_mismatch<br>completion:GraphRecursionError<br>completion:experiment_failed |
| 7 | `powerdns` | `deepseek-v4-flash` | fail | 612,730 | 3240.758 | 4 | 0 | 0/0 | agent_tool:post_build_reserve_exhausted<br>agent_tool:post_build_reserve_exhausted<br>completion:GraphRecursionError<br>completion:experiment_failed |

## 有效性与预算解释

- 7 个 ledger 均为冻结 schedule 的连续前缀；没有 retry、replacement 或 backfill。
- Token 边界在创建下一槽前检查，不会中途截断已经创建的 physical attempt。
- 当前 900 秒 wall-clock 是每次 Compiler 调用的预算。同一 physical attempt 可由 Lead 多次调用 Compiler，因此 attempt 总时长可以超过 900 秒。
- 下一协议应预注册独立的 physical-attempt 总时限；该建议不改变 v3 结果，也不授权补跑 slot 8-10。
- 手机热点是已记录的接入分类，不足以把历史 endpoint timeout 归因于热点、WSL、路由或 provider 中任一层。

## 研究边界

- 当前有效分母为实际创建并终结的 7 个 slot，不是计划中的 10，也不是完整 180 槽。
- Condition 样本不平衡且每个 case 仅一次，不能做显著性检验或总体模型排名。
- 剩余 170 槽仍需实验所有者再次确认；slot 8-10 也不能在当前 token 授权下继续创建。

## 复算

```bash
/app/backend/.venv/bin/python /repo/scripts/forge_formal_collection_v3_report.py \
  --evidence-dir /workspace/.compile-sessions/benchmark-evidence-formal-v3-authorized
```

JSON 是机器可读来源；Markdown 由同一分析器确定性生成。
