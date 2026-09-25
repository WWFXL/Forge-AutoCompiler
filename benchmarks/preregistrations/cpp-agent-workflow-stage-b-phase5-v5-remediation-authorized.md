# CXXCrafter Stage B Phase 5 v5 定向修复重评预注册

## 目的与边界

本协议只用于工程化 Stage C 准入判定。Phase 5 v3 已严格成功的 `yyjson`、`cppitertools`、`openh264` 和 Phase 5 v4 已严格成功的 `c-ares`、`libass` 作为固定 SHA-256 的只读历史证据；v5 仅新执行 `uwebsockets`。结果必须表述为跨 run adjudication，不产生新的六项目同条件实验或无偏成功率主张。

Stage C 执行不属于本协议。无论判定结果如何，所有报告和 decision 都必须记录 `stage_c_execution_started=false`。

## v4 失败审计

v4 的 `uwebsockets` 已生成并暂存 `HelloWorld` 与 `uSockets/uSockets.a`，但子代理先把 uSockets 子模块编译误标为最终 build。随后包含 `timeout 1500` 和输出截断管道的 `make examples` 被命令策略拒绝；直接 `g++` 编译又被误标为 `artifact_stage`，候选提交最终因 `build_system_mismatch` 被拒，工作流继续诊断直至耗尽 recorded-token 预算。

v4 的跨 run 裁决还发现 v3 汇总报告内嵌 outcome 保留 v2 schema/document 标签，而独立 task result 使用 v3 标签。固定文件哈希及其余字段均匹配。v5 只允许把这两个已知 v2 标签规范化为 v3 标签后比较；任何其他字段差异仍拒绝。

## 冻结执行

- Provider、模型、endpoint、0 retry、镜像、网络策略、commit、target、oracle 和单任务预算继承既有 Phase 5 合同。
- 唯一正式任务为 `uwebsockets`，最多一个 attempt；batch ceiling 为 300,000 recorded tokens，另含唯一 reachability 的 5,000 token ceiling。
- 使用 external evaluator v4，要求 required artifacts 同时被候选声明并实际交付，功能 service probe 和 clean replay 由系统执行。
- 任务输入固定 `uwebsockets-make-examples-v1` 指导：在 `/workspace/repo` 以 dependency 角色执行 `git submodule update --init uSockets`，再以 build 角色执行 `make examples`；不得使用 shell timeout wrapper 或 `head`/`tail` 截断；精确暂存 `HelloWorld` 与 `uSockets/uSockets.a` 后立即以 `build_system=make` 提交，不手工执行 smoke test。
- 每次正式执行使用全新 compile session；不复用 v3/v4 reachability 或 task attempt，不导入失败 outcome，不修改历史 evidence。

## 跨 run 判定

v3 报告、decision 和三项 task result，v4 batch marker、报告和两项 task result，都必须通过预注册文件 SHA-256、manifest identity、任务顺序、语义和严格成功不变量核验。v5 的 `uwebsockets` 还必须满足 candidate submitted、S0-S5 全部通过、strict reproducible build success、cleanup 成功和 0 managed resources。

六项均严格成功时生成 `stage_c_authorized=true`；否则为 false，并要求建立新的 remediation identity。两种结果都禁止在本协议内启动 Stage C。

## 停止规则

reachability 只允许一次。正式 task result、batch report、cross-run adjudication 和 Stage C decision 均采用 create-once 证据；不得覆盖、补跑、replacement 或 backfill。任何 identity、哈希、资源清理或证据结构不一致均停止并保留现场。
