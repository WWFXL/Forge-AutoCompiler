# C++ Agent Workflow Stage B Phase 5 v4 修复重评预注册

日期：2026-09-25。追踪：Issue #305，来源 Issue #303。

## 研究用途

本轮是工程修复后的定向重评，只执行 Phase 5 v3 未严格通过的 `uwebsockets`、`c-ares`、`libass`。Phase 5 v3 evidence 保持只读，三个既有成功结果只用于跨 run Stage C 工程准入判定。本轮不得解释为新的六项目同条件实验、无偏成功率或方法泛化能力。

## 允许变化

相对于 Phase 5 v3，只允许以下变化：

1. Agent Workflow 的 LangGraph recursion guard 高于业务 `max_agent_steps`，底层 recursion 终止统一记录为 `agent_steps` 预算终止。
2. post-build 提示明确要求只暂存普通文件并立即提交，功能 oracle 由外部 evaluator 执行。
3. candidate submit 必须声明全部 `required_candidate_artifacts`。
4. external evaluator v4 在 S2 独立检查 required artifacts 已声明且已交付。
5. task 集合缩减为三项历史失败任务，batch token ceiling 相应缩减为 900,000。
6. 新报告及其嵌套 outcome 使用一致的 v4 identity。

项目 commit、target/oracle、build-system qualification、DeepSeek `deepseek-flash`、endpoint、300 秒请求超时、0 retry、禁止 fallback、Docker image ID、每任务预算和并行度保持不变。

## 新 identity

- evidence：`/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v4-remediation-authorized`
- attempt：`phase5-v4-remediation-{task_id}-attempt-1`
- thread：`phase5-v4-remediation-{task_id}-{manifest-prefix}`
- evaluation：`phase5-v4-remediation-{task_id}-evaluation-v4`
- report：`reports/stage-b-phase5-v4-remediation.json`

每项使用新的 Compile Session、exact-commit checkout 和空 task evidence。只允许一个新 reachability request。禁止导入 v3 失败 outcome、继续 v3 Session、replacement、backfill 或覆盖历史文件。

## Stage C 判定

batch 闭合后生成跨 run adjudication，按原六项目顺序组合：

- Phase 5 v3：`yyjson`、`cppitertools`、`openh264` 的冻结严格成功结果；
- Phase 5 v4 remediation：`uwebsockets`、`c-ares`、`libass` 的新结果。

只有六项均满足 candidate submitted、S0-S5 全部通过、strict reproducible build success、cleanup 成功、0 managed resources，且 v3/v4 报告及任务结果哈希匹配时，才写出 `stage_c_authorized=true`。Stage C 执行仍不属于本协议，必须保持 `stage_c_execution_started=false`。

## 执行顺序

1. 在合并后的干净 `main == origin/main` 上执行 `preflight`。
2. 执行唯一 `reachability`。
3. 按 `uwebsockets`、`c-ares`、`libass` 顺序执行唯一 batch。
4. 只读审计账本、报告、adjudication、容器清理和权限。
5. 停在 Stage C 可进入但未执行的状态。
