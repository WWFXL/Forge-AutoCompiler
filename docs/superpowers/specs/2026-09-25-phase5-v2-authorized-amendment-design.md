# Phase 5 v2 授权修订设计

日期：2026-09-25。追踪：Issue #297，关联 Issue #291、#294。

## 目标

把已合并的 Phase 5 v2 未授权 candidate 派生为独立 authorized amendment，使实验所有者可以执行一次 reachability 和六项目正式 batch，同时保持首次 Phase 5 停止结果只读。

## 身份边界

父 candidate canonical SHA-256 固定为 `babc7d2f07058aa7968bea19cd8e022eea6442bd64388c99965f5333d12e4ee3`，授权基线固定为 candidate 合并提交 `03a870eeef54f3fe591b115428dba51637acbcca`。authorized manifest 只允许改变授权位、运行 protocol/runner、独立 evidence 目录和新增 execution identity；tasks、预算、Provider、镜像、qualification 与报告口径不得改变。

## 模型创建前门禁

全局 preflight 验证干净 release、父 candidate/qualification/authorized component identity、网络介质、Provider 配置、Docker control plane、冻结 image ID 和 0 managed orphan。task preflight 在模型创建前完成 exact clone，复核 commit、完整 build-system capabilities 与 selected build system，并把选择写入 Session。

## 生命周期

reachability、batch 和 task marker 均 create-once。batch 只恢复同 manifest、同 release revision、同一 `started` batch marker 下完成且 cleanup 闭合的连续前缀；缺少 batch marker 时拒绝导入已有 task evidence。只有进程在两个 task 之间异常退出时才能继续；已创建但未闭合的 task 或任何 task failure 都会阻断恢复，不能自动重试。

每个 task 使用独立的 `phase5-v2` attempt、thread、run 和 evaluation identity。external evaluator v2 读取 candidate，执行功能 oracle，再由产品提交验证和 clean replay 独立判定。每项结束后 finalize、cleanup 与 0 orphan 必须闭合，才能进入下一项。

## 输出

授权 evidence 写入 `/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-phase5-v2-authorized`。完整 batch 生成校准报告和 Stage C 决策输入；决策包中的 `stage_c_authorized` 固定为 false。

## 验收

- authorized manifest、Schema 与 allowed delta 可确定性验证。
- release、qualification、image、task probe 与 orphan 漂移均在模型创建前失败。
- reachability create-once、batch 连续前缀和失败终态有单元测试。
- runner 只调用 external evaluator v2，并使用冻结 capabilities/selection。
- 非 Docker 测试和 lint 通过；真实 Docker 与 Provider 命令由实验所有者执行。
