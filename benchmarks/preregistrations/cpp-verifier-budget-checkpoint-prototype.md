# Verifier-driven repair budget checkpoint 非模型原型预注册

## 研究问题

Issue #135 / PR #136 已证明 compiler 消息 checkpoint 的中性分支与冷恢复；Issue #137 / PR #138 已证明合成环境的 rootfs + bind-mount 同源双臂恢复。本门禁只回答：能否从同一个父预算 checkpoint 确定性重建 baseline/treatment 的相同 continuation budget，同时隔离两臂后续消耗并保留 capture 前累计成本。

## 冻结范围

- 跟踪 Issue：#139。
- Provider、Docker、formal physical attempt、model token：实际调用或消耗均为 0。
- 只新增实验专用 manifest、deterministic fake clock/counters 与聚焦测试。
- 不修改生产 `_ACTIVE_EXPERIMENTS`，不提供从历史 ledger 恢复生产 runtime 的入口。
- 不修改 Oracle、clean replay、verifier-driven repair runtime、自然任务 ITT runner 或冻结 evidence。
- 不接入组合 continuation runner，不授权 provider canary 或 mechanism slots。

## Manifest 契约

版本 `forge-budget-checkpoint-1.0.0` 固定以下层次，并以 canonical JSON 的 SHA-256 拒绝漂移：

- `limits`：provider requests、compiler invocations、compiler model turns、graph recursion steps、attempt/compiler wall-clock、cleanup/post-build reserve 与 post-build commands。
- `consumed_before_capture`：上述可消耗资源在 capture 前的累计值，以及累计 tokens。
- `remaining_at_capture`：每项限制减去 capture 前累计值；不允许调用方自行声明不一致的剩余额度。
- `continuation_clock`：attempt total/work 与 compiler total/exploration 的 capture 前 elapsed 和 continuation remaining。
- `post_build`：是否已进入 post-build、reserve、command limit/consumed/remaining。
- `parent_cost`：capture 前 tokens、provider requests 与 compiler invocations，后续报告不得隐藏。
- `arm_identity`：父 manifest 固定为 neutral；baseline/treatment identity 属于各自 runtime，不改变父 manifest。

## 双臂规则

1. baseline/treatment 均深拷贝并重验同一个父 manifest。
2. 两臂的 canonical initial budget 必须完全相同；绝对 fake-clock 起点不进入比较。
3. 每臂独立记录 provider request、compiler invocation、model turn、graph step、post-build command 与 token 增量。
4. 任一臂 claim 不得改变另一臂或父 manifest。
5. 普通新工作受 attempt work deadline 约束；model turn/graph step 还受 compiler exploration deadline 约束；post-build command 使用预留时间但受 compiler total deadline 约束。
6. finalize 与 cleanup 不被新工作预算耗尽阻塞；报告仍显式显示 total deadline 是否归零。

## 通过条件

- 所有离散预算满足 `limits - consumed_before_capture = remaining_at_capture`。
- attempt 与 compiler 墙钟均能区分 work/exploration deadline 和 total deadline。
- 两臂初始 canonical budget 相同，后续 claim 相互独立。
- 五类离散预算均能耗尽并拒绝下一次 claim。
- compiler exploration reserve、post-build total deadline 和 attempt cleanup reserve 的边界行为由 fake clock 固定。
- finalize/cleanup 在预算耗尽后仍可调用。
- 最终 cost report 同时保留 parent cost、arm continuation cost 与两者总和。
- 未知字段、负数、超限、算术漂移、parent cost 漂移、clock 漂移和 hash 篡改均失败关闭。
- 聚焦 pytest、消息/环境 checkpoint 相邻非 Docker 回归与 Ruff check/format 通过。

## 失效条件

- 原型导入 provider、Docker runtime 或 formal runner。
- 任一实际 provider request、Docker 命令、formal physical attempt 或 model token 消耗。
- 两臂初始预算不一致，或一臂 claim 污染另一臂。
- capture 前成本未进入最终报告，或 remaining/deadline 可被不一致输入伪造。
- 预算耗尽阻止 finalize/cleanup，导致资源清理语义倒置。

## 解释边界

通过只证明实验专用预算 manifest 和 continuation 计数器可以确定性重建并隔离，不证明生产 attempt runtime、真实 compiler transcript、provider client 或端到端 continuation runner 已可恢复，也不产生 verifier repair 的因果效果结论。消息、环境、预算三层均通过后，下一阶段仍需单独评审组合 runner；任何真实模型请求和机制实验预算继续由实验负责人另行授权。
