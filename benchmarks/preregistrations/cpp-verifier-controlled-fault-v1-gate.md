# Verifier-driven repair controlled fault v1 零 provider 门禁预注册

## 研究问题

Issue #145 已冻结 checkpoint 机制实验设计。本门禁只回答：能否在真实、可恢复的 C/C++ build output 已存在时，确定性移除 `/artifacts` 中唯一 required artifact，由真实 verifier 产生 pre-replay `candidate_verification_failed`，再从同一 committed checkpoint 派生两个隔离 arm 并恢复正确 staging。

## 冻结范围

- 跟踪 Issue：#147。
- fault family：`artifact_staging_missing`；expected classification：`candidate_verification_failed`。
- Provider calls、formal physical attempts、model tokens 均为 0；不读取任何 AK。
- Docker 只允许 WSL2 Ubuntu 原生 `docker.service`，不使用 Docker Desktop 或 Windows Docker CLI。
- 不修改生产 Compiler、自然任务 ITT runner、Oracle、clean replay、历史 evidence 或 `_ACTIVE_EXPERIMENTS`。
- 只新增薄的 controlled-fault adapter、聚焦测试和未授权 primary canary manifest 候选；复用 Issue #143 的真实 lifecycle gate。

## Fault 契约

1. 冻结 recipe 先生成真实 required artifact，并把同一字节复制到 `/artifacts`。
2. 注入前，workspace output 与 staged artifact 的类型和 SHA-256 必须相同，`/artifacts` 只能包含该文件。
3. fault 只删除 staged artifact，workspace output 和容器 rootfs 保持不变。
4. 调用 verifier 前写入 `controlled.fault_injected`；payload 只含 case/session/fault identity、相对路径、artifact type、SHA-256 和布尔状态。
5. 真实 submit 必须只发生一次，产生 `candidate_status=failed`、无 replay、`candidate_verification_failed`，且 `replay_attempts == 0`。

## 恢复门禁

- baseline/treatment 从同一个 committed message/environment/budget checkpoint 派生。
- 两臂初始 canonical environment 相同，`/artifacts` 均为空，workspace output 均存在。
- 非模型恢复动作只把 workspace output 复制到 arm-local `/artifacts`；任一臂不得污染另一臂或父 snapshot。
- 两臂分别调用真实 submit，candidate verification 与 clean replay 均应通过。
- cleanup 后无 paused/orphan container、continuation image、helper 或 snapshot。

## Canary candidate 边界

机器可读候选为 `benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-candidate.json`。它固定 primary provider 候选、1 次 reachability request、1 个 controlled pair 和 245,000 maximum tokens，但 `provider_canary_authorized=false`、`collection_authorized=false`。本 gate 通过不会自动授权任何请求。

## 通过与停止

- 聚焦非 Docker 测试、checkpoint/lifecycle 相邻回归和 Ruff 必须通过。
- 唯一 opt-in Docker gate 使用冻结的 `cppitertools@531b3d7...` CMake recipe；网络/daemon/image preflight 失败时停止，不切换 Docker daemon，不把基础设施失败解释为 fault 失败。
- submit 重复、classification/replay 漂移、arm 污染、敏感信息进入 evidence 或 cleanup 遗留均立即失败。
- 通过只证明 controlled fault v1 与 checkpoint 生命周期可供后续 canary 使用，不产生 repair effect 结论。
