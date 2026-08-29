# Checkpoint 行为终态 v2 六配对实验结果

本报告对应 Issue #165、PR #166 与预注册 `cpp-verifier-checkpoint-behavioral-pilot-v2.md`。旧 v1 pair-01 与 recovery pair-02 仅作为 exploratory feasibility evidence，不进入本报告的分母或统计。

## 实验身份

- Release: `381657247ba395de893a5e67035afa0df5c49a24`
- Manifest canonical SHA-256: `1df45a6e0b72f67a914098fc7336eee3bcc8f7b517b132407b88244da10882a3`
- Provider: DeepSeek `deepseek-v4-flash`
- Endpoint policy: 300 秒 timeout、0 retry、非 streaming、禁止 fallback
- 网络介质: `wifi`
- Docker: WSL Ubuntu 原生 Docker Engine；Compose/DooD control plane；未使用 Docker Desktop
- Pilot report SHA-256: `932d47bb9a3ce30f68f86aee660c4ae2ca36b343333f4a77d6dab0a60a8049bd`
- Evidence inventory: 50 files / 837,282 bytes；按 `relative_path<TAB>sha256<TAB>size<LF>` 排序连接后的 SHA-256 为 `95014c1169fe6950c14726a16f43fd45454c10604f3b9f38494bff0b106f88d8`

## 预注册终态

- 6/6 新 pair 已观察，12/12 arms 均被尝试。
- 0 endpoint-censored pair，6/6 pair 进入 primary mechanism estimand。
- 累计 231,944 recorded tokens，低于 1,440,000 机械上限。
- 18/18 parent/baseline/treatment Session 均为终态，最终 0 Compile Session、replay、checkpoint container/image orphan。

## 配对结果

| Pair | Arm order | Baseline | Treatment | Baseline req/tokens | Treatment req/tokens | Repair delta |
|---|---|---|---|---:|---:|---:|
| v2-pair-01 | baseline -> treatment | passed | passed | 6 / 21,380 | 6 / 20,766 | 0 |
| v2-pair-02 | treatment -> baseline | graph-step limit / verification failed | passed | 8 / 27,943 | 4 / 12,532 | +1 |
| v2-pair-03 | baseline -> treatment | passed | passed | 5 / 15,659 | 2 / 5,419 | 0 |
| v2-pair-04 | treatment -> baseline | passed | graph-step limit / no submit | 4 / 11,797 | 8 / 29,893 | -1 |
| v2-pair-05 | baseline -> treatment | graph-step limit / verification failed | passed | 8 / 29,855 | 3 / 8,843 | +1 |
| v2-pair-06 | treatment -> baseline | graph-step limit / verification failed | passed | 8 / 34,152 | 4 / 13,705 | +1 |

## 描述性结果

- Baseline repair success: 3/6；treatment repair success: 5/6。
- 配对 conversion delta（treatment - baseline）: `[0, +1, 0, -1, +1, +1]`。
- Baseline 合计 39 requests / 140,786 tokens；treatment 合计 27 requests / 91,158 tokens。
- Baseline 3 次 `completed`、3 次 `graph_step_limit`；treatment 5 次 `completed`、1 次 `graph_step_limit`。
- 4 个模型行为失败全部被保留为 outcome；没有因第一臂失败跳过第二臂，也没有 replacement、backfill 或第 7 个 pair。

## 研究解释

该结果支持 verifier repair packet 在这个受控 failure checkpoint 上可能提高 repair conversion：treatment 在 6 个配对中成功 5 次，baseline 成功 3 次。v2 还证明先前被当成采集异常的 `GraphRecursionError`、无 submit 和 verification failure 可以作为结构化模型行为结果进入分母。

但这仍是单 provider、单仓库、单 controlled fault、6-pair 的小样本机制 pilot。不能计算有意义的显著性结论，不能做模型排名，也不能直接外推到自然仓库任务或其他失败类型。下一阶段应先冻结分析和复制策略，再决定独立 provider replication 或 natural-failure ITT，而不是在本批次追加样本。

## 冻结 outcome SHA-256

- Batch marker: `97e4fb7bdbae0529e387fc873c02ba81e430f5145021fc1db5f1420c0ebb272b`
- v2-pair-01: `7475650e5eb6e0539987777afb6699cdc22f44226b27e1f4d9d2cbc1319d85ea`
- v2-pair-02: `9db9aafc24d4e1e95943090b979570d613e3cde87b2c589dc9cfb0fb815cc8a5`
- v2-pair-03: `2e194e060c1ea9c29600b5f33d7387751daf23ba74c102855adba6442c4e2b90`
- v2-pair-04: `1038ca01db51072c21aaeb8c9d33189cb933b675094d6f24f4eaa4a011da0200`
- v2-pair-05: `5a03e3452b11cc2cbeeb30943cc719d04226d12665683d704c4fe5f4ad3604d9`
- v2-pair-06: `6848eb9a259d26a9595e3f2626ecfa10f6371d45291e9fcfa7c7d0e3a59b2fbc`
