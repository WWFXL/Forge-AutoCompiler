# Opaque build provenance 零 provider 契约门禁预注册

本协议承接 Issue #174 与已冻结的路线 P。研究对象是 **provenance compliance repair**：真实 CMake 产物可能已经存在，但可信执行证据不足，导致 verifier 不能证明冻结构建系统在本次 physical attempt 中产生该产物。该 stratum 不与 `artifact_staging_missing` 池化，也不表述为普通编译失败修复。

## Reference truth 与证据等级

- P0：模型声明的 command role、summary 或自然语言，只用于诊断。
- P1：从 shell 字符串推断 `cmake`、`ninja` 或 `make`，只用于兼容诊断。
- P2：trusted runtime invocation、configure/generator/build-tree 关系、source/environment identity、artifact output binding 与完整 ledger hash chain；这是本门禁的 reference truth。
- P3：签名、SLSA 或 in-toto attestation，本阶段不实现。

P2 只有同时绑定下列 identity 才能记为 `proven`：repository URL、exact commit、不可变 image ID、physical attempt、workdir、build directory、target、trusted command ID、规范化叶子 invocation、exit/timeout、artifact type/size/SHA-256，以及未删除、未重排、未改写的 ledger hash chain。

## 冻结 CMake 单 case

本门禁只使用确定性的 synthetic CMake identity，不 clone 仓库、不启动 Docker、不读取 AK。正向 reference 包含：

1. trusted runtime 直接记录 `cmake --build <frozen-build-dir> --target <frozen-target>`，并把冻结 artifact 绑定到该 producer command；预期 P2 `proven`。
2. trusted runtime 先记录 `cmake -S ... -B ... -G Ninja`，再记录同一 attempt、同一 build directory 的 native Ninja invocation；完整 generator link 与 artifact binding 均存在，预期 P2 `proven`。
3. 顶层 wrapper 可解析到规范化叶子 Ninja invocation，且 wrapper SHA-256 与完整 generator link 均存在；预期 P2 `proven`。

负向 reference 包含 opaque wrapper、仅模型声明 build role、configure/build directory 不一致，预期 `opaque_build_provenance` / `unproven`。source、commit、image、attempt、artifact 或 ledger identity 漂移不是可修复负例，必须立即抛错并 fail closed。

## Controlled fault

首个 fault 使用真实 artifact identity 与成功 native Ninja producer command，但不提供 trusted generator link。预期结果固定为：

- `status=unproven`；
- `classification=opaque_build_provenance`；
- production 对应分类为 `build_system_unproven`；
- `reason=missing_trusted_generator_link`；
- `replay_attempts=0`。

fault 构造前后的 command history 必须逐对象相等且 canonical SHA-256 相同。不得通过删除 configure 命令、重排命令、改写 model role 或重算历史来制造 fault；缺失的 generator evidence 从一开始就不属于可信 ledger。

## 零消耗边界

本阶段只运行纯 Python contract test，固定输出：

- `provider_calls=0`；
- `formal_attempts=0`；
- `model_tokens=0`。

禁止启动 Forge 服务、Docker、canary、clean replay 或 behavioral pilot；禁止读取任何 AK；禁止修改 production Compiler、Oracle、`operations.py`、历史 runner、manifest 和 evidence。

## Treatment 与 estimand 边界

后续 treatment 候选只能提供白名单结构化 repair packet，说明冻结 build directory、target 和 `proof_status=missing_trusted_generator_link`，要求通过 trusted runtime 补齐构建证据。不能泄露完整命令答案。

未来主要 estimand 是 post-checkpoint provenance conversion：同一 committed checkpoint 派生的 continuation 是否从 P1/unproven 转为 P2/proven，并最终通过 candidate verification 与 clean replay。当前零 provider gate 只验证构造效度，不估计模型效果。

## 停止规则

出现任一条件即停止，不进入真实 lifecycle gate：正向 direct/native-wrapper 被错拒；负向 opaque case 被错接收；fault 需要改写 command history；fault 同时触发其他分类；或必须修改 production Compiler/Oracle 才能通过纯契约门禁。
