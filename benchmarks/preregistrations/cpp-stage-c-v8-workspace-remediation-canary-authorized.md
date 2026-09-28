# Stage C v8 workspace remediation authorized canary 预注册

日期：2026-09-28。追踪：[Issue #347](https://github.com/WWFXL/Forge-AutoCompiler/issues/347)。

## 来源与授权边界

本 identity 从 v8 workspace remediation candidate canonical SHA-256 `4ed33a827d2c801ed1b0f56c717ee332f0a65141ed8d07d05326ff373dd07f6d` 派生。v7 reachability、batch、attempt、报告和 ledger，以及 v8 candidate manifest、Schema、protocol、runner 和预注册全部保持只读；不导入 v7 的 70-token reachability 或失败 attempt，不允许 retry、replacement、backfill 或续跑旧 batch。

授权范围只包含一个新的 create-once reachability 和按冻结顺序执行的四项 B 臂 canary。任务顺序固定为 `theora -> json-c -> libjpeg-turbo -> oatpp`，任一失败立即停止。Token 不设总量上限，但每次模型响应必须记录 input、output 和 total token；模型请求数、Agent step、工具调用、命令数和墙钟限制保持不变。

## Workspace 与执行门禁

Compile Session process/host workspace 必须显式绑定到当前 release repository root，`.compile-sessions` 必须是仓库直属的非符号链接、可写、可进入目录；授权 evidence 固定为其直属子目录 `.compile-sessions/benchmark-evidence-stage-c-v8-workspace-remediation-canary-authorized-v1`。该路径检查必须在 credential、model、Provider 和 create-once marker 前完成。

Preflight 还必须验证干净 `main == origin/main`、当前 revision 为授权基线后代、`FORGE_NETWORK_ACCESS_MEDIUM=ethernet`、Linux Docker `default` context、`unix:///var/run/docker.sock`、冻结 image ID、0 managed resources，以及 credential 环境变量仅存在性。任何失败都在模型和 marker 前 fail closed。

## Reachability、attempt 与停止规则

唯一 reachability 最多一次请求，精确响应 `STAGE_C_V8_WORKSPACE_OK`，并核对实际模型身份与逐响应 token。失败 marker 不得删除或覆盖；失败后本 identity 不再执行 batch。

每个 attempt 使用独立 thread、Session、candidate、evaluator 和 ledger。运行 Agent Workflow Runtime v3、pre-freeze candidate verifier 和 external evaluator v4；candidate create-once，允许 pre-freeze 拒绝后的同 attempt 修正，不允许 external evaluator 反馈给 Agent。每个 attempt 必须 finalize、cleanup 并回到 0 managed resources；首个失败后停止，不补跑后续任务。

## 发布与真实执行边界

本 PR 的开发、测试和 CI 使用确定性本地模型，保持 0 Provider request、0 formal attempt、0真实 model token、0正式 evidence write。只有本 identity 经代码审查合并，且实验负责人再次明确确认后，才可在干净主干执行真实 preflight、唯一 reachability 和 batch。
