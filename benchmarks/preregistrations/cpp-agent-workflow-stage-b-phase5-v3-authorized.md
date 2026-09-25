# C++ Agent Workflow Stage B Phase 5 v3 独立授权评测预注册

日期：2026-09-25。追踪：Issue #303，关联 Issue #299、#291。

## 研究用途

本评测只验证 external evaluator v3 修复后的单 Agent Workflow Node 工程闭环。六个 Stage B 项目及其历史结果已经暴露，因此结果不得解释为无偏成功率、泛化能力或相对 CXXCrafter 的优越性。

Phase 5 v2 的 reachability、task attempt、outcome、report 和 evidence 均不导入、不续跑、不定向补评。v2 manifest 和只读审计报告只用于冻结本设计的来源与差异。

## 冻结条件

继承 Phase 5 v2 authorized identity 的六个 exact commit、task 顺序、target/oracle、build-system qualification、DeepSeek `deepseek-flash`、`https://api.deepseek.com`、300 秒请求超时、0 retry、禁止 fallback、完整 Docker image ID、并行度、Agent/命令/replay/cleanup 预算。

唯一方法变化是 external evaluator v3：版本固定为 `forge-external-evaluator-1.2.0`，rules SHA-256 固定为 `5c5579f426bf2b805599dbc8341c351a31802c1ad396e16ce0687ff02b14e8aa`。系统 functional oracle 使用内部独立权限，不消费或继承 Agent post-build inspection 次数门禁，其他安全与证据规则保持不变。

## 独立 identity

- evidence：`/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v3-authorized`
- attempt：`phase5-v3-{task_id}-attempt-1`
- thread：`phase5-v3-{task_id}-{manifest-prefix}`
- evaluation：`phase5-v3-{task_id}-evaluation-v3`
- report：`reports/stage-b-phase5-v3.json`

每项从新的 Compile Session、exact-commit checkout 和空 task evidence 开始。新 reachability marker 与 report 位于独立 evidence 目录，不能复用 v2 reachability。

## Release 与前置门禁

真实执行必须来自干净的 `main == origin/main`，revision 是授权 baseline 的后代，并记录到每项 evidence。在创建模型前必须验证 manifest/Schema、父 v2 identity、审计报告、runner、evaluator v3、Provider 配置、网络介质、冻结镜像、完整 build-system qualification 与 0 managed resources。

开发和 PR 门禁阶段为 0 Provider、0 credential read、0 Docker、0 formal attempt、0 model token、0 experiment evidence write。

## Reachability 与 batch

只允许一个 create-once reachability：固定提示 `Reply with exactly CANARY_OK and nothing else.`，最多 1 request / 5,000 recorded tokens。失败或不完整终态禁止启动 task。

task 顺序固定为 `yyjson`、`cppitertools`、`openh264`、`uwebsockets`、`c-ares`、`libass`。每项一个 physical attempt，每项最多 300,000 recorded tokens，batch 最多 1,800,000。禁止 retry、fallback、replacement、backfill 和 outcome 后重排。

恢复只允许同一 manifest、同一 release revision、同一 `started` batch marker 下已经闭合的连续前缀。已启动但未闭合的 task、缺少 batch marker 的既有 task evidence 或任意缺口都会阻断恢复。

## 终点与停止规则

每项分别记录 candidate generated、candidate submitted、S0-S5、strict reproducible build success、bitwise reproducibility、tokens、cleanup 和 0 orphan。task 异常、evaluator 异常、identity 漂移、非连续 evidence、cleanup/ownership 失败、orphan 或预算耗尽/超出都会终止 batch，且不自动创建新 attempt。

Stage C 始终保持未授权。完成后必须人工审计 Phase 5 v3 报告，再另行决定是否设计 Stage C identity。
