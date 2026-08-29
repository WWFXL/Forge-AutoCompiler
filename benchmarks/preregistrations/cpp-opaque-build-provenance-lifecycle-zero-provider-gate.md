# Opaque build provenance 生命周期零 provider 门禁预注册

本协议承接 Issue #174 的 P2 reference criterion 与 Issue #176。目标是验证 `opaque_build_provenance` 能否安全进入 failure checkpoint 的双臂 continuation 契约，而不是估计模型效果或宣称真实编译成功。

## 实验单位与 capture point

实验单位固定为一个 synthetic CMake failure checkpoint。capture point 是失败 submit 已形成中性反馈、candidate replay 尚未启动、下一次 continuation 尚未发生的时刻。Parent 固定 repository URL、exact commit、image ID、physical attempt、workdir、build directory、target、artifact type/size/SHA-256、两条 trusted invocation 与 ledger hash chain。

Parent artifact 存在且绑定成功的 native Ninja producer command，但 trusted generator link 缺失。P2 reference outcome 固定为：

- `status=unproven`；
- `mechanism_classification=opaque_build_provenance`；
- production 对应分类 `build_system_unproven`；
- `proof_status=missing_trusted_generator_link`；
- `replay_attempts=0`。

## 双臂唯一差异

Baseline 与 treatment 必须引用同一个 parent checkpoint SHA-256 和 common-state SHA-256，session identity 相互隔离。Baseline 接收原始中性 feedback；treatment 只在同一 feedback 增加一个白名单 `repair_packet`。

Packet 只允许：Schema version、production/mechanism classification、expected/selected CMake identity、冻结 build directory、target、proof status 和抽象 repair goal。禁止 `command`、`argv`、shell、prompt、solution、secret 或完整命令字符串。Packet 不告诉 continuation 使用 `cmake --build`、Ninja 或任何可直接复制的 shell 答案。

## 合成 continuation 与 ledger

本门禁不调用模型。Baseline 确定性不追加 trusted invocation，再次 P2 判定仍为 unproven。Treatment 使用实验夹具模拟一个遵循 repair goal 的 continuation，在 parent ledger 尾部 append 一条新的 trusted direct-CMake build invocation，并把 artifact producer binding 更新到该新 invocation；parent history 必须保持逐对象前缀相等，parent history SHA-256 不变。

Treatment 的预期 P2 outcome 为 `proven/direct_cmake`。这个合成转换只证明 adapter 能表达 post-checkpoint provenance conversion，不能证明模型会采取相同行为。

## 终态 observer

Candidate verification、clean replay 与 cleanup 使用依赖注入的 deterministic contract callback。它们只记录调用顺序和 fail-closed 行为，不执行 production verifier、Docker、Compile Session 或真实 clean replay：

1. baseline 不调用 candidate/replay，只调用 cleanup；
2. treatment 只有 P2 proven 后才能调用 candidate；
3. candidate passed 后才能调用 clean replay；
4. 任一阶段失败都阻断后续阶段，但 cleanup 仍必须运行；
5. 正向 treatment 顺序固定为 `candidate -> clean_replay -> cleanup`。

三个 observer result 还必须绑定同一个 observation subject SHA-256；该 subject 包含 parent checkpoint、arm/session、P2 decision 与 continuation history。来自其他 arm、checkpoint 或 history 的 `passed` 结果必须 fail closed。

CLI 必须明确输出 `observation_mode=deterministic_contract_callback` 与 `docker_executed=false`，不得把 callback 的 `passed` 写成真实构建证据。

## 零消耗与禁止范围

- `provider_calls=0`；
- `formal_attempts=0`；
- `model_tokens=0`；
- 不读取 AK，不启动 Docker；
- 不修改 production Compiler、Oracle、`operations.py`；
- 不修改历史 checkpoint/repair runner、manifest 或 evidence。

## 停止规则与下一门禁

若双臂不能保持同源、packet 必须泄露完整命令、treatment 需要改写 parent ledger、baseline 被误转为 proven，或 observer 可以越过失败阶段，则停止路线 P。

本门禁通过后仍不能创建 provider canary。下一步应单独设计真实 Docker lifecycle gate，使用 fake continuation 或预注册命令在隔离 Compile Session 中闭合真实 candidate verifier、clean replay 与 cleanup；只有该运行时门禁通过并冻结 evidence identity 后，才能申请最小 provider canary。
