# 进展感知结构化 Harness H0/H1 配对比较 v2 预注册

## 身份

- Identity：`cpp-progress-aware-harness-comparison-v2`；
- Tracking Issue：[#433](https://github.com/WWFXL/Forge-AutoCompiler/issues/433)；
- Branch：`yiwei/433-h0-h1-provider-comparison`；
- Evidence root：`.compile-sessions/benchmark-evidence-progress-aware-harness-comparison-v2`，create-once；
- Remediation parent：`cpp-progress-aware-harness-comparison-v1`，inventory `3a03ec1a2bed0ab5311842ce51bc0292963871d2c9f3d9d364ce84aae51fa201`。

用户对 v1 的 Provider 与 evidence 授权继续适用于同一研究阶段的 v2。Credential 值不得写入日志或 evidence。v1 与所有历史 evidence 只读，禁止续跑、replacement、backfill 或把 v1 canary 放入 v2 正式 estimate。

## 继承合同

Treatment、estimand、9 个 checkpoint、3 次重复、27 pairs / 54 formal arms、3 pairs / 6 canary arms、交错顺序、`deepseek-flash`、单臂 24 requests / 300,000 tokens / 1,800 秒、批次 1,440 requests / 18,000,000 tokens / `$21.60`、离线 source archive、strict endpoint、bootstrap 和联合通过路径全部原样继承 v1 预注册。

## 唯一修订

v1 metrics reader 因同时发现主 Agent 和 evaluator events 而把 H1 机制事件错误记为 0。v2 只读取不在 `evaluations/` 下的唯一主 Agent events。Q1 除 v1 的完整分类、计量、身份和 cleanup 门禁外，新增：

1. 每个 H0 arm 的 `progress_snapshots == 0` 且 `context_compactions == 0`；
2. 每个 H1 arm 的 `progress_snapshots == model_requests > 0`；
3. 每个 H1 arm 的 `context_compactions == model_requests > 0`；
4. v1 Q2 path 必须不存在，v1 inventory 必须逐文件保持不变。

任一新增门禁失败即停止在 v2 Q1，不创建 Q2。Q0/Q1/Q2 全部以新 identity 重新执行，不复用 v1 observation。

## 分析与解释

主要通过路径仍为 strict difference 的 task-cluster 单侧 95% 下界 `>= -0.10`、H1 cost reduction `>=20%`、三系统不退化；替代路径仍为 difference `>=0.10`、下界 `>0`、cost increase `<=10%`、三系统不退化。解释边界与 v1 相同。
