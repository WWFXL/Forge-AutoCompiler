# Forge C/C++ pilot v8 描述性分析报告

> 状态：冻结 calibration 的描述性复核；不是正式模型比较。

## 摘要

- v8 collection：6/10 oracle passed；10/10 ledger hash chain、10/10 当前离线 gate、10/10 cleanup 有效，orphan=0。
- 冻结终态原始记录中的 `gate_recomputation_valid` 为 9/10；Issue #69 修复后当前只读重算为 10/10。二者差异保留历史来源，不回填 ledger。
- 实际模型身份与各 condition 配置匹配 10/10。
- 同目录另有 5 条历史 baseline ledger；5/5 hash chain 有效，不进入 v8 的成功率分母。
- 本报告只描述五个自选 case、每 condition 一次的 calibration；manifest 明确 `formal_comparison_enabled=false`，不得据此宣称模型总体优劣或统计显著性。

## Condition 汇总

| Condition | 模型 | Oracle | 请求 started/completed/failed | Tokens | 命令 | Submit | Clean replay passed/completed | 总墙钟（秒） | 中位墙钟（秒） |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `richlab-gpt-5.5` | `gpt-5.5` | 2/5 | 116/116/0 | 806,682 | 81 | 18 | 7/10 | 3642.391 | 870.474 |
| `deepseek-v4-flash` | `deepseek-v4-flash` | 4/5 | 75/74/1 | 499,850 | 47 | 5 | 4/4 | 1365.731 | 198.958 |

## 每个 slot

| # | Case | Condition | Oracle | 分类 | 请求 | Tokens | 墙钟（秒） | 命令 | Submit | Replay passed/completed | 观测失败事件 |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `fmt` | `richlab-gpt-5.5` | pass | `passed` | 12/12/0 | 64,175 | 201.725 | 9 | 1 | 1/1 | — |
| 2 | `fmt` | `deepseek-v4-flash` | pass | `passed` | 10/10/0 | 56,775 | 122.667 | 8 | 1 | 1/1 | — |
| 3 | `hiredis` | `richlab-gpt-5.5` | fail | `oracle_mismatch` | 26/26/0 | 146,651 | 414.691 | 14 | 3 | 3/3 | completion:experiment_failed |
| 4 | `hiredis` | `deepseek-v4-flash` | pass | `passed` | 23/23/0 | 163,314 | 198.958 | 13 | 2 | 1/1 | submit_replay:candidate_verification_failed |
| 5 | `libcheck` | `richlab-gpt-5.5` | fail | `oracle_mismatch` | 22/22/0 | 134,534 | 1058.648 | 13 | 3 | 0/1 | agent_tool:post_build_reserve_exhausted<br>submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:build_system_mismatch<br>completion:experiment_failed |
| 6 | `libcheck` | `deepseek-v4-flash` | pass | `passed` | 15/15/0 | 109,328 | 192.644 | 12 | 1 | 1/1 | — |
| 7 | `libgit2` | `richlab-gpt-5.5` | pass | `passed` | 24/24/0 | 139,042 | 1096.853 | 14 | 2 | 2/2 | — |
| 8 | `libgit2` | `deepseek-v4-flash` | pass | `passed` | 23/23/0 | 153,905 | 615.538 | 12 | 1 | 1/1 | — |
| 9 | `sysstat-nondeterministic` | `richlab-gpt-5.5` | fail | `oracle_mismatch` | 32/32/0 | 322,280 | 870.474 | 31 | 9 | 1/3 | submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:candidate_verification_failed<br>submit_replay:sha256_mismatch<br>submit_replay:sha256_mismatch<br>completion:experiment_failed |
| 10 | `sysstat-nondeterministic` | `deepseek-v4-flash` | fail | `submit_missing` | 4/3/1 | 16,528 | 235.924 | 2 | 0 | 0/0 | model_endpoint:timeout<br>completion:experiment_failed |

## 网络与 endpoint 解释边界

- 10 个 slot 的 `network_present` 与 `endpoint_reachable` 启动前检查分别通过 10/10 和 10/10。
- 共观察到 1 个带 timeout 的 physical attempt；这只能说明当时从 Forge 到兼容 endpoint 的完整请求路径未在冻结时限内闭合。
- 历史 v8 ledger 没有记录本机使用 Wi‑Fi、手机热点、有线网络或其他接入介质，也不能把 Windows 网络栈、WSL/Docker 转发、受限 relay、互联网路由与 provider endpoint 分离。
- 因此 timeout 的归因是 `indeterminate`：不得把它直接算作模型能力失败，也不得事后根据当前网络环境回填历史证据。

正式实验应在 attempt 前记录不含 SSID、IP、运营商账户或凭据的分类元数据：`access_medium ∈ {wired,wifi,mobile_hotspot,unknown}`、relay 是否启用、endpoint canary 延迟与 Docker/WSL 网络拓扑；这些只能进入新协议，不能回写 v8。

## 描述性观察

- RichLab condition 在本 calibration 中为 2/5，DeepSeek condition 为 4/5；该差值同时混合了项目差异、单次随机性、Agent 搜索轨迹、endpoint 路径和预算消耗，不能视为模型总体效应。
- `hiredis / RichLab` 的最终 oracle 失败来自 artifact identity 路径不匹配；`libcheck / RichLab` 同时出现候选验证失败、build-system mismatch 与 post-build reserve 耗尽；`sysstat / DeepSeek` 在 submit 前出现 endpoint timeout。
- `sysstat / RichLab` 的中间 SHA-256 mismatch 后续变为 clean replay 可通过，没有满足冻结的非确定性负向预期；Issue #69 只修复了离线 gate 解释，没有改变该 oracle 结论。

## 对下一阶段的约束

1. 保持 v1-v8 manifest、Schema、validator 和 ledger 冻结，不 retry、replacement 或 backfill。
2. 正式比较前预注册约 30 个分层 C/C++ 项目，每 condition 至少 3 次；primary metric、删失规则、失败层级和统计方法必须先写定。
3. endpoint timeout 作为可靠性/删失结果单列；是否重试必须由新协议预先固定，不能运行后决定。
4. verifier-driven repair、阶段 Skill、验证后 Memory 与控制面 A/B 分开设计，一次只改变一个 treatment。

## 复算

```bash
PYTHONPATH=backend/packages/harness python scripts/forge_benchmark_v8_report.py \
  --evidence-dir /workspace/.compile-sessions/benchmark-evidence
```

JSON 报告是表格数字的机器可读来源；Markdown 由同一分析器确定性生成。
