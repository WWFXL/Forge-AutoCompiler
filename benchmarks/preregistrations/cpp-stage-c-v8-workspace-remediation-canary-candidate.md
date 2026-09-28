# Stage C v8 workspace remediation canary candidate 预注册

日期：2026-09-28。追踪：[Issue #345](https://github.com/WWFXL/Forge-AutoCompiler/issues/345)。

## 来源与边界

本 candidate 从 Stage C v7 authorized manifest canonical SHA-256 `261da6d0d0416073998d9aed544c99dba3097784fa2c3edd0022a2cd96e3086f` 派生。v7 reachability、batch、attempt、报告和 ledger 保持只读；v7 已停止，不允许 retry、replacement、backfill、删除 marker 或导入 outcome。

本阶段只实现 workspace remediation identity 与零 Provider 门禁。Credential read、Provider 调用、模型创建、reachability、正式 attempt、evidence 写入和 model token 均未授权。Token 继续采用无上限逐响应计量设计，但 candidate 阶段实际消耗必须为 0。

## 路径合同

Compile Session 的 process workspace root 与 Docker host workspace root 都显式解析为当前 release repository root。两者必须解析到同一路径，compile sessions 目录固定为仓库相对 `.compile-sessions`；不得因系统上存在 `/workspace` 而切换到隐式默认根。

Preflight 在 credential、model、Provider 和 create-once marker 前验证：repository root 与 `.compile-sessions` 均为真实目录且不经过符号链接；process/host roots 一致；compile sessions root 可写且可进入；candidate evidence 路径位于该 root 的直属安全相对路径下，已存在时必须是非符号链接目录且可写，未存在时其父目录必须可写。任一失败都返回 fail closed，并保持 0 evidence。

## 科学合同

任务、顺序、Provider、模型、镜像、Runtime v3、pre-freeze candidate verifier、external evaluator v4、操作限制、无 token ceiling 和 stop-on-first-failure 规则继承 v7。新 attempt identity 使用 v8 命名和独立 evidence 路径，不导入 v7 的 70-token reachability 或失败 attempt。

## 零 Provider 门禁

单元测试覆盖路径解析、符号链接、不可写父目录、旧 v7 evidence 哈希、未授权入口和纯验证无副作用。Opt-in Docker gate 使用 root-owned decoy workspace 复现旧故障，同时让 runner 将真实 Session 显式绑定到可写 release root；确定性本地模型必须完成 Runtime v3、candidate repair、external evaluator v4、clean replay、finalize、cleanup 和 0 managed resources，并逐响应记录 synthetic token。

通过代码审查并合并后，才可另行派生 create-once authorized amendment；本 candidate 不授权任何真实 Provider 行为。
