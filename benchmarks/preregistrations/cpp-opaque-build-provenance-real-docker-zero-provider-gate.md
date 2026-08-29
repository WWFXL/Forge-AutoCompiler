# C/C++ opaque build provenance 真实 Docker 零 provider 门禁预注册

## 身份

- Tracking Issue：#178
- Schema：`forge-opaque-build-provenance-real-docker-gate-1.0.0`
- Case：`cppitertools@531b3d753d2bbfe3b0ababe61c2e95e965c54a66`
- 构建系统：CMake + Ninja
- Compile image：`autocompiler:gcc13`，运行时固定实际 image ID
- Fault family：`opaque_build_provenance`
- Production classification：`build_system_unproven`
- P2 parent reason：`opaque_wrapper`

## 研究目的

Issue #174 已证明 P2 reference criterion 能区分可信 direct CMake、可信 generator link 与 opaque/unbound invocation；Issue #176 已证明 failure checkpoint 双臂和 observation binding 的合成生命周期契约。本门禁只补真实执行证据：在同一个可恢复 CMake checkpoint 上闭合 production candidate verifier、独立 clean replay 和 cleanup。

本门禁不测模型效果，不产生正式实验样本，也不把 provenance compliance repair 表述为普通编译失败修复。

## Controlled fault

Parent Compile Session 在 trusted runtime 中执行一条顶层为 `sh -c` 的自包含命令。Wrapper 内真实完成：

1. 清理并用 CMake + Ninja configure 冻结 build directory；
2. 构建真实 `accumulate_examples` target；
3. 将 executable staging 到 `/artifacts/accumulate_examples`。

Production role parser 能从 wrapper 叶子文本识别 `configure/build/artifact_stage`，但 build-system identity parser 只接受顶层可信 executable，因而不能用该 opaque wrapper 证明 CMake。父命令自身包含完整 configure/build/stage，所以 clean replay 从空 workspace 检出冻结 commit 后可以成功执行，不依赖未记录的 preparation 状态。

本 gate 的 experiment policy 将 `cmake_arguments` 冻结为空：参数观察不是本阶段 estimand，且不能让 shell wrapper 的 token 可见性额外产生 `cmake_arguments_not_observed`。实际 parent command 仍固定使用 `-DCMAKE_BUILD_TYPE=Release`。

Parent submit 必须只有 `build_system_unproven`，artifact checks 可以通过，但 candidate bundle 与 clean replay 不得启动，`replay_attempts == 0`。P2 reference evaluator必须独立得到 `unproven / opaque_wrapper`。

## 双臂与唯一差异

Baseline 与 treatment 从同一个 committed message/environment/budget checkpoint 派生。两臂必须具有相同 continuation image、workspace、artifact 和 parent command records。

- Baseline：只接收原始中性 submit failure；不追加 invocation，再次 submit 仍为 `build_system_unproven`，0 replay。
- Treatment：唯一 checkpoint exposure 是白名单 repair packet。Packet 只包含 classification、build system、build directory、target、`proof_status=opaque_wrapper` 与抽象 repair goal；禁止完整命令、argv、shell、prompt、solution 和 secret。
- Treatment continuation：append-only 执行可信 direct `cmake --build`，再重新 staging 同一 artifact；不得删除、重排或改写 parent command records。

## Gate outcomes

Treatment 必须同时满足：

1. P2 reference evaluator 为 `proven / direct_cmake`；
2. production candidate verification 为 `passed`；
3. clean replay 在原 continuation image ID、空 workspace/artifacts 和独立 replay container 中为 `passed`；
4. replay cleanup、Compile Session cleanup 与 checkpoint cleanup 为 `passed`；
5. parent、baseline、treatment、replay、checkpoint container 与 checkpoint image 均为 0 orphan。

## 授权和运行边界

- 固定 `provider_calls=0`、`formal_physical_attempts=0`、`model_tokens=0`；
- 不读取任何 AK，不创建模型 client，不运行 provider canary；
- 只允许 WSL Ubuntu 原生 `docker.service`；禁止 Windows Docker CLI、Docker Desktop context 和 Docker Desktop fallback；
- Docker 测试默认 skip，只有显式设置 `FORGE_RUN_OPAQUE_PROVENANCE_DOCKER=1` 才运行；
- 不修改 production Compiler、Oracle、`operations.py`、历史 runner、manifest 或 evidence；
- 本门禁通过不自动授权 behavioral pilot。

## 停止规则

出现下列任一情况即停止：

1. Parent 同时产生第二个 protocol failure；
2. Parent wrapper 无法从 clean workspace 独立 replay；
3. Baseline 意外启动 replay 或转为 proven；
4. Treatment 必须改写 parent records，或 P2/candidate/replay 任一层不能通过；
5. Cleanup 不能闭合或发现 orphan；
6. 完成 gate 需要修改 production Compiler、Oracle 或历史 evidence。
