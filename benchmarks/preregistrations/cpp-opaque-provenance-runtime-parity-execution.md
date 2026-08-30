# Opaque build provenance runtime-parity 一次性 execution amendment

本 amendment 承接 Issue #188 / PR #189 已冻结并通过 0-provider preflight 的候选。实验负责人回复“继续执行”，据此授权 Issue #190 所述的一次 DeepSeek reachability；只有 reachability 通过，才执行一个新的 `baseline -> treatment` pair。

## 冻结身份

- 父候选 manifest canonical SHA-256：`27b161720d3ab1208d6792e59df4509a611c3967645787a083b0fb9bdc6bdcb2`。
- 父候选 evidence identity SHA-256：`ce7e4277bcedab8b203ebe51863877b2d3f958e838ed7dcc960a47f23981c25a`。
- Provider：DeepSeek `deepseek-v4-flash`，endpoint `https://api.deepseek.com`，credential env `DEEPSEEK_API_KEY`。
- 请求策略：300 秒、0 retry、非 streaming、禁止 fallback、`parallel_tool_calls=False`。
- Pair：`opaque-provenance-cppitertools-runtime-parity-pair-01`，顺序固定 `baseline -> treatment`。

## 一次性机会与预算

Reachability marker 在请求开始前 create-once；started、failed 或 passed 都消费唯一机会。Reachability 最多 1 次、5,000 recorded tokens。失败时 pair 必须机械拒绝。

每臂最多 8 requests、8 model turns、24 graph steps、600 秒工作时间、120 秒 cleanup reserve 和 120,000 recorded tokens。Pair 上限 240,000，阶段机械上限 245,000。启动每一臂前重新核对能否容纳完整下一臂；禁止 retry、replacement、backfill 或追加 pair。

## Runtime-parity exposure

Controlled parent 必须经 production `_submit_with_post_build_phase` 形成唯一 `build_system_unproven`，capture 前 post-build fence 三字段必须释放。双臂共享 inspection/build/stage/submit = 4/2/2/2 的原子预算；repair build 只允许冻结 build directory/target，stage 只允许冻结 output 与 `/artifacts` destination。Clone、configure、dependency、housekeeping、manual replay、compound build+stage 和越界动作继续 fail closed。

Baseline 与 treatment 唯一差异仍为白名单 repair packet。Runtime-parity policy 同时施加给两臂，不是 treatment。新 pair 是独立 measurement-policy amendment，不是 #184 的 retry、replacement、backfill 或 schedule extension；结果不得与 #184 或其他 fault family 池化。

## 证据与解释

新 evidence 写入 Issue #188 冻结的独立目录。每臂保留模型 request ledger、runtime-parity action budget、P2、candidate/replay 与 cleanup 结果。#184 canary report 只读核验 SHA-256，不修改历史 evidence。

该单 pair 只判断 intervention delivery 与 post-checkpoint provenance conversion 是否可观察。无论结果如何，都不估计 treatment effect、不计算 p 值、不排名模型、不自动授权多 pair pilot。AK 值不得进入日志、报告或 Git。
