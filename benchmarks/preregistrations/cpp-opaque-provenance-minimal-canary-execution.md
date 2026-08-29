# Opaque build provenance 最小 canary 一次性执行 amendment

本 amendment 承接 Issue #182 已合并的授权候选与真实 0-provider preflight。实验负责人回复“继续执行”，据此只授权 Issue #184 所述的一次 DeepSeek reachability；只有 reachability 通过，才执行一个固定 `baseline -> treatment` pair。

## 冻结身份

- 父基线：`main@323430f1fb3f3fb7ac09c6ea1aefa801298e5619`。
- 父 manifest canonical SHA-256：`00ce7eaadda3e89b63d093f4e360473fe372850dd39290d69e1a4a7e675e7771`。
- Evidence identity SHA-256：`f83fb4a3d228c82839df68905ee603c79095c919fe0cc8ab0c52ce4debaeb538`。
- Provider：DeepSeek `deepseek-v4-flash`，endpoint `https://api.deepseek.com`，credential env `DEEPSEEK_API_KEY`。
- 请求策略：300 秒、0 retry、非 streaming、禁止 fallback。
- Pair：`opaque-provenance-cppitertools-pair-01`，顺序固定 `baseline -> treatment`。

## 一次性机会与预算

Reachability marker 在请求开始前 create-once；started、failed 或 passed 都消耗唯一机会。Reachability 最多 1 次、5,000 recorded tokens。失败时 pair 必须机械拒绝。

每臂最多 8 requests、8 model turns、24 graph steps、600 秒工作时间、120 秒 cleanup reserve 和 120,000 recorded tokens。Pair 上限 240,000，阶段总上限 245,000。启动每一臂前按已记录 token 重新检查能否容纳完整下一臂；禁止 retry、replacement、backfill 或追加 pair。

## Checkpoint 与 treatment

Parent 使用 Issue #178 冻结的自包含 opaque `sh -c` wrapper，真实完成 CMake/Ninja configure、target build 与 artifact staging。Production submit 必须只有 `build_system_unproven`，P2 必须为 `unproven/opaque_wrapper`，且 candidate/replay 不启动。

双臂从同一个 committed message、environment 和 budget checkpoint 派生。Baseline 只看到原始 submit 失败；treatment 唯一额外 exposure 是 Issue #178 白名单 repair packet。Packet 不包含命令、argv、shell、prompt、secret 或完整解法。

主要 outcome 是 post-checkpoint P2 provenance conversion。Production candidate verification 与 clean replay 通过但 P2 未证明时 fail closed；artifact、build tree、source、image、ledger、token 或 cleanup identity 漂移时停止。

## 执行与解释边界

真实执行只允许从干净 `main == origin/main`、Wi-Fi 记录、Ubuntu-native Docker `/var/run/docker.sock`、0 managed orphan 的 Compose/DooD control plane 发起。Evidence 写入 #182 冻结目录，marker 与报告不可覆盖；AK 值不得进入日志、报告或 Git。

该单 pair 只验证真实 provider 与机制测量链能否接线。无论结果如何，都不估计 treatment effect，不计算 p 值、不排名模型、不与 `artifact_staging_missing` 历史 pair 池化，也不自动授权多 pair pilot。
