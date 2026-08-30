# Opaque build provenance R1 yyjson 一次性 execution amendment

本 amendment 承接 Issue #196 的 result-blind `yyjson` 候选和 Issue #198 的真实 Docker 零 provider checkpoint 生命周期门禁。它只授权一次 reachability 和一个 state-matched `baseline -> treatment` pair，不修改任何历史协议或 evidence，不把 #184/#190 exploratory pair 纳入 R1 分析池。

## 冻结身份

- Case：`https://github.com/ibireme/yyjson@9365ddc7061033df656578bf86040048b5b5531a`。
- CMake build directory / target：`/workspace/repo/build` / `yyjson`。
- Output / staged artifact / type：`build/libyyjson.a` / `libyyjson.a` / `static_library`。
- Provider：DeepSeek `deepseek-v4-flash`，endpoint `https://api.deepseek.com`，credential 仅允许从 `DEEPSEEK_API_KEY` 读取。
- 请求策略：300 秒、0 retry、非 streaming、禁止 fallback。
- 机会：一次 reachability，随后至多一个 `baseline -> treatment` pair；marker 在开始时消耗，禁止 retry、replacement、backfill 和 schedule extension。
- Recorded-token ceiling：reachability 5,000、每臂 120,000、单 pair 240,000、全阶段 245,000。

## Checkpoint 与 intervention

真实 pair 在 reachability 通过后重新创建 Issue #198 已验证的 controlled parent：顶层 `sh -c` wrapper 完成 configure、build 和 stage，但不提供 trusted direct-CMake identity，因此 parent 必须只形成 `build_system_unproven / opaque_wrapper`。Parent submit 继续走真实 bound post-build wrapper，并在 capture 前释放 fence。

Message、environment、budget 绑定同一 capture ID；两臂从同一 neutral checkpoint 派生，初始 workspace、artifact、image 和剩余预算 canonical 同源。Baseline 只收到原 verifier feedback；treatment 唯一额外 exposure 是冻结 repair packet。Packet 不提供完整命令、argv、模型正文或 credential。

## Runtime parity 与 R0 可观测性

两臂共享 4/2/2/2 的 inspection、repair build、artifact stage、submit 原子预算，并强制 `parallel_tool_calls=false`。Repair build 只允许 direct `cmake --build /workspace/repo/build --target yyjson`；artifact stage 只允许把 `build/libyyjson.a` 复制为 `/artifacts/libyyjson.a`。Clone、configure、dependency、housekeeping、manual replay 和 compound build+stage 全部 fail closed。

Continuation 必须使用 Issue #194 的 `ObservableRuntimeParityToolAdapter` 和 `RejectionObservationRegistry`。每个可稳定分类且具有唯一 model/tool-call origin 的拒绝，必须同时留下历史七字段 `agent.tool_failed` 与通过 `failure_id` 关联的 `agent.tool_rejection_observed`；后者只记录 classification、action kind、model request ID、tool ordinal 和 command SHA-256。原始命令、错误文本、模型正文、工具参数与 credential 不得持久化。未知或歧义 origin 只保留历史事件。

## 执行顺序与停止规则

1. 在合并后的干净 `main == origin/main` 上验证 Ubuntu WSL2 原生 Docker endpoint、Compose/DooD control plane、provider 配置、网络介质和 0 managed orphan；preflight 不写 evidence。
2. 仅一次 reachability。开始即写 fail-closed marker；失败立即停止，不执行 pair。
3. Reachability 通过后仅一次 pair。开始即写 fail-closed marker；identity、checkpoint、evidence、budget、Docker、cleanup 或未分类失败立即停止。
4. 已分类 arm outcome 可继续另一臂；endpoint timeout 记为删失而非重试。最终 cleanup 必须闭合并恢复 0 managed orphan。

## 结果边界

主要结果是单个独立 checkpoint pair 中的 post-checkpoint P2 conversion，并同时要求 candidate verification、clean replay 和 cleanup。报告描述两臂 conversion、请求数、token、延迟、动作预算及拒绝 companion evidence。单 pair 只提供 intervention delivery 和机制可达性的描述性证据，不估计 treatment effect、不计算 p 值、不排名模型，也不与历史 pair 池化。
