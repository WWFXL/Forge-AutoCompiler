# Phase 5 v3 独立授权评测设计

日期：2026-09-25。追踪：Issue #303，关联 Issue #299、#291。

## 决策

Phase 5 v2 的六项目 batch 已闭合，原始 evidence 和结果保持只读。其结果只能按审计报告分为 1 项可靠成功、2 项工作流失败和 3 项 evaluator 缺陷导致不可判定，不能通过定向重评追认为一次完整的新 batch。

本阶段创建 `Phase 5 v3 independent evaluation`：在完全独立的授权 identity 和 evidence 目录中重新执行六个项目，并把 external evaluator v3 作为预注册运行时的一部分。该评测仍只用于已暴露 Stage B 项目的工程校准，不产生无偏成功率，也不授权 Stage C。

## 冻结与允许差异

从 Phase 5 v2 authorized manifest 原样继承：

- 六个 task、exact commit、target、oracle 和固定顺序；
- build-system capabilities 与 selected build system；
- DeepSeek provider、endpoint、300 秒请求超时、0 retry 和禁止 fallback；
- Docker image ID、网络策略、并行度；
- per-task 与 batch token、请求、工具、命令和墙钟预算；
- 每个 task 一个 physical attempt，禁止 reorder、replacement 和 backfill；
- clean replay、finalize、cleanup 和 0 managed orphan 门禁。

唯一允许的语义差异是：

- protocol、runner、manifest、Schema 和预注册升级为 Phase 5 v3；
- external evaluator 从 v2 升级到 v3，并冻结文件、版本和 rules identity；
- release baseline、attempt、thread、evaluation、report 和 evidence identity 全部更新；
- 独立性声明明确禁止导入 v2 reachability、attempt、outcome 和 evidence。

任何 task、Provider、镜像、预算、顺序、oracle 或授权范围漂移都使 manifest 无效。

## Evaluator v3 identity

冻结：

- 路径：`backend/packages/harness/deerflow/compile/external_evaluator_v3.py`
- 版本：`forge-external-evaluator-1.2.0`
- rules SHA-256：`5c5579f426bf2b805599dbc8341c351a31802c1ad396e16ce0687ff02b14e8aa`
- oracle authority：`system_owned_post_build_fence_isolated_v1`

系统 oracle 可以绕过 Agent 已耗尽的 post-build inspection 次数门禁，但仍受严格 shell、`/repro` 禁止、阶段角色、命令记录、functional oracle 和 clean replay 规则约束。Agent 工具权限和剩余预算不因 evaluator 执行而增加。

## 独立执行身份

- evidence 目录：`/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v3-authorized`
- attempt：`phase5-v3-{task_id}-attempt-1`
- thread 前缀：`phase5-v3`
- evaluation：`phase5-v3-{task_id}-evaluation-v3`
- batch report：`reports/stage-b-phase5-v3.json`

新 reachability 不复用 v2 marker 或请求。六个 task 均从 exact commit、空的新 Compile Session 和新 evidence 开始。v2 manifest 与审计报告只作为冻结设计来源，不作为运行输入或结果来源。

## Runner 结构

v2 authorized runner 已进入冻结身份，不能通过重构增加注入点。新 runner 使用薄适配器：

1. 验证父 manifest、父 runner、v3 evaluator 和新授权组件哈希；
2. 在单进程串行临界区把父 runner 绑定到 v3 protocol、v3 evaluator 和新 document identity；并发进入或父 binding 已被其他 identity 修改时，在任何执行副作用前拒绝；
3. 调用父 runner 已验证的 preflight、reachability、task lifecycle、连续前缀恢复和报告流程；
4. 在成功或异常退出时恢复全部父模块绑定；
5. evidence 写入结束后按配置的宿主 UID/GID 规范化新 evidence tree。

适配器不得修改父 runner 文件，不允许并发执行两个绑定不同 identity 的 batch。

## 授权和停止规则

本 identity 授权一次 create-once reachability 和固定顺序的六个 task。reachability 预算为 5,000 recorded tokens，batch 预算为 1,800,000，每 task 为 300,000。

以下任一情况立即失败关闭：identity 漂移、reachability 失败、evidence 非连续、task 异常、evaluator 异常、cleanup 不闭合、managed orphan、ownership 规范化失败或 token ceiling 耗尽/超出。失败后不自动 retry、replacement 或 backfill。

## 结果边界

报告分别输出 candidate generated、candidate submitted、S0-S5、strict success、bitwise reproducibility 和资源清理结果。即使六项全部通过，也只能说明在已暴露校准集合上修复后的工程闭环有效，不能据此声称总体成功率或方法优越性。

Stage C 始终为 `authorized=false`。进入 Stage C 仍需冻结 12 个新 task、A/B 共享条件、endpoint attrition 规则、重复与随机顺序，并获得新的执行授权。
