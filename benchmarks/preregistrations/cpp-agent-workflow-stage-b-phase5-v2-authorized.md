# C++ Agent Workflow Stage B Phase 5 v2 授权预注册

日期：2026-09-25。追踪：Issue #297，关联 Issue #291、#294。

## 授权对象

本修订仅授权 Phase 5 v2 candidate 的一次 Provider reachability 和冻结顺序中的六个正式 task。父 candidate canonical SHA-256、qualification result SHA-256、完整 Docker image ID、六个 exact commit、构建系统能力集合、选定构建系统、external evaluator v2 与预算均保持冻结。

首次 Phase 5 的 outcome、attempt、thread、evidence 和停止报告只作为历史来源引用，不导入、不续跑、不 replacement、不 backfill。

## Release 与执行前门禁

执行必须来自干净的 `main == origin/main`。当前 revision 必须是授权基线 `03a870eeef54f3fe591b115428dba51637acbcca` 的后代，并写入每项 evidence。

在创建模型前，runner 必须验证：父 candidate 与 qualification digest、授权组件哈希、冻结镜像 ID、Provider 配置、网络介质、0 managed orphan；每个 task 还要在 exact checkout 后重新探测完整构建能力集合，并验证选定构建系统。任一门禁失败时 Provider request 必须保持为 0。

## Reachability

只允许一个 create-once 请求：提示词固定为 `Reply with exactly CANARY_OK and nothing else.`，响应、模型 identity 和 token evidence 必须同时通过。失败或不完整 marker 不得创建任何正式 task。

## Batch

task 顺序固定为 `yyjson`、`cppitertools`、`openh264`、`uwebsockets`、`c-ares`、`libass`，每项只允许一个 physical attempt。恢复只接受同一 manifest、同一 release revision、同一 `started` batch marker 下已经闭合的连续前缀；缺少 batch marker 时不得导入已有 task evidence。只有进程在两个 task 之间异常退出时才允许继续；已创建但未闭合的 task 会阻断恢复。不允许越过缺口、失败 task、retry、replacement 或 backfill。

每项使用新 `phase5-v2` attempt/thread/evaluation identity，由 external evaluator v2 独立判定 S0-S5、strict reproducibility 与 bitwise reproducibility。task 结束后必须完成 cleanup 并重新验证 0 managed orphan，之后才可创建下一项。

## 预算与停止规则

reachability 上限为 5,000 recorded tokens；六项目 batch 上限为 1,800,000 recorded tokens，每项上限为 300,000。预算只在 attempt 之间检查，已启动的单项允许完成并记录；若完成后超过上限，batch 立即失败，不创建后续 task。

以下任一情况停止：reachability 失败、identity 或 qualification 漂移、非连续 evidence、task 异常、cleanup 不闭合、存在 managed orphan、batch token ceiling 耗尽或超出。停止后不自动创建新 attempt。

## 报告边界

报告分别呈现 candidate generated、candidate submitted、S0-S5、strict success 和 bitwise reproducible。该校准不得宣称无偏成功率。Stage C 始终保持未授权，必须在 Phase 5 v2 结果经人工审核后另行决策。
