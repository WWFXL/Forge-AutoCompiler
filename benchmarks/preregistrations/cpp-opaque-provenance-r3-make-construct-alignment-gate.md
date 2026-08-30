# C/C++ opaque provenance R3 Make 构造对齐零 provider 门禁

状态：本地候选。追踪 Issue：[#212](https://github.com/WWFXL/Forge-AutoCompiler/issues/212)。

## 研究动机

#208 的 treatment 在有效网络下未发生 P2 conversion，但 #202 reference criterion 不要求固定 jobs，#208 runtime 却把 jobs 恰好为 `2` 作为动作准入条件，而且双臂共享的工具描述没有公开该条件。冻结结果仍是有效的 `observed_no_conversion`，但不足以排除 intervention under-specification。

本门禁不修改、重跑或补写 #208/#210 evidence。它只验证未来新 identity 的 action surface 是否与 outcome construct 对齐，不构成模型效果证据。

## 构造对齐规则

- P2 provenance identity：direct `make/gmake`、冻结 effective directory、单 target、exact run/artifact producer identity；jobs 不属于 P2 identity。
- 资源策略：jobs 可以省略或取 `1..2`，禁止无界 `-j`、`0`、超过 `2` 和非数字值。
- Runtime-admissible direct Make actions 必须是 P2-acceptable actions 的子集；资源策略比 P2 更严格的部分必须在 baseline/treatment 共用的工具契约中明示。
- Build 与 artifact stage 必须拆成两个动作；stage source/destination 固定为 `/workspace/repo/libhoedown.a` 与 `/artifacts/libhoedown.a`，并通过双臂共享工具契约公开。继续禁止 clone、configure、dependency、housekeeping、manual replay 和 compound build/stage。
- Repair packet 保持 #208 九字段内容不变，仍不包含 command、argv、shell 或完整解法；它是唯一 treatment exposure。

## R0 可观测性

未来 adapter 必须区分 `repair_build_jobs_unbounded`、`repair_build_jobs_out_of_bounds`、directory drift、target drift、invocation invalid 和 arguments invalid。Companion 仍只允许 bounded classification、action kind、model request ID、tool ordinal 与 command SHA-256，不保存原始命令、异常正文、模型正文、工具参数或凭据。

## 停止规则

本阶段只运行静态 validator、单元测试、冻结哈希与敏感信息审计。固定 0 provider、0 credential read、0 Docker、0 checkpoint、0 formal attempt、0 model token、0 evidence write。

门禁通过只允许下一阶段另建真实 Docker lifecycle identity 候选；不授权 reachability、provider canary、single pair、replacement 或 batch。
