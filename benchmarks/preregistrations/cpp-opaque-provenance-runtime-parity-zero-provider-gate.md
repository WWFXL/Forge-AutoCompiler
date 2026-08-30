# Opaque provenance runtime-parity 零 provider 门禁

## 研究问题

Issue #184 的 treatment 在执行 eligible repair build 前被 post-build fence 机械拒绝。只读审计确认 controlled parent 绕过了公开 submit wrapper，而 Issue #178 的确定性 treatment 又绕过了真实 bound tool。本门禁只验证 checkpoint 后的真实 Agent 执行面，不估计模型效果。

## 冻结边界

- Parent 仍使用 Issue #178 的 opaque wrapper、exact commit、image、build directory、target 与 artifact identity。
- Parent constraint failure 必须只有 `build_system_unproven`，P2 必须为 `unproven/opaque_wrapper`。
- 失败 submit 必须通过与 Agent 相同的 `submit_build_result` wrapper；capture 前 post-build fence 三个字段必须全部释放。
- Repair packet 保持 Issue #178 白名单，不增加命令、argv、shell、prompt 或完整解法。
- Issue #184 marker、ledger、report 与 evidence inventory 保持不可变。

## 动作预算

| 动作 | 每臂上限 | 说明 |
| --- | ---: | --- |
| inspection | 4 | 只读环境与 build-tree 检查；成功、失败或 timeout 均消耗。 |
| repair build | 2 | 只允许 direct `cmake --build`，且 build directory 与 target 必须匹配冻结 identity。 |
| artifact stage | 2 | 每次只允许把冻结 build output 复制到冻结 `/artifacts` 路径。 |
| continuation submit | 2 | Stage 会尝试 automatic submit；已有 staged artifact 时成功 repair build 也会 automatic submit，因此对应动作在执行前原子预留一次 submit。 |

数字来自“最小闭环 + 一次修正机会”，不是从 Issue #184 的 DeepSeek 命令序列反推。Clone、configure、dependency、housekeeping、手动 replay、复合 build+stage 命令继续 fail closed。

预算 admission 与 consume 必须在同一锁内原子完成。Provider tool binding 固定 `parallel_tool_calls=false`；本阶段只验证 LangChain model-setting 契约，不创建真实模型。

## 门禁矩阵

1. 静态正向：冻结 direct CMake build 与 artifact stage 被接受，四类预算独立记录。
2. 静态负向：build directory/target 漂移、compound shell、configure、第三次 build、第三次 submit 被拒绝。
3. 并发负向：并行 inspection claim 最多接受 4 条，不得超额执行。
4. 真实 Docker 正向：公开 submit wrapper 形成 parent failure 并释放 fence；真实 bound tool 完成 inspection、repair build/automatic submit、candidate verification 与 clean replay。Stage 的独立路径由静态 adapter 门禁覆盖。
5. 终态：replay cleanup 成功，compile/replay container 清理，无 provider call、formal attempt 或 model token。

## 解释规则

Issue #184 baseline 继续是 `endpoint_censored`。Treatment 追加 `measurement_policy_censored / intervention_delivery_failure`，不得表述为 repair packet 无效或严格资源约束下的模型失败。本门禁通过只说明 intervention 在真实工具面可交付；新的 provider amendment 仍需独立协议与授权。

## 停止规则

若正向路径必须修改 production Compiler/Oracle、改写历史 command ledger、放宽 P2/source/image/artifact identity、泄露完整解法，或不能通过真实 bound tool 闭合，则停止，不调用 provider、不追加 pair。

## 2026-08-30 门禁结果

中文 Issue [#186](https://github.com/WWFXL/Forge-AutoCompiler/issues/186) 已创建并回读。实现保持 experiment-only，没有修改 production Compiler、Oracle、`operations.py`、历史 runner、manifest 或 Issue #184 evidence。

- 静态 gate `8 passed`：四类预算独立、并发 inspection 最多接受 4 条、越界 build-dir/target、compound shell、configure、第三次 build 和第三次 submit 均在底层工具调用前拒绝。
- LangChain/DeepSeek 依赖的 `bind_tools` 原生支持 `parallel_tool_calls`；experiment middleware 固定把 `False` 合并到最终 model settings，不创建模型或读取 credential。
- Ubuntu-native Docker gate 为 `1 passed in 36.80s`：parent 通过真实 bound submit 形成唯一 `build_system_unproven` 后，三个 post-build fence 字段全部释放；随后真实 bound tool 完成一次 inspection 与一次 direct CMake repair build，并在已有 staged artifact 上 automatic submit。
- Production candidate verification 与 clean replay 均为 `passed`，replay cleanup 成功；动态 P2 从 `unproven/opaque_wrapper` 转为 `proven/direct_cmake`，动作消耗为 inspection 1、repair build 1、stage 0、submit 1。
- 编译核心相邻回归 `159 passed`；路线 P 回归 `84 passed, 1 deselected`。被排除的旧 #182 测试把 gitignored 真实 evidence 目录假设为空，在 #184 正式采集后该前提已失效；原始全套结果为 `84 passed, 2 skipped, 1 failed`，失败不涉及本阶段代码，且不得通过删除冻结 evidence 修复。
- Ruff check/format、Python 语法、CLI、diff 与敏感信息检查通过；CLI 固定报告 0 provider、0 formal attempt、0 model token。Ubuntu daemon 为 `ubuntu-native/default//var/run/docker.sock`，测试容器和 replay 容器均清理。

首次 Docker 执行在 adapter 预检查处拒绝了测试自身的 `&&` compound inspection，未进入 repair/replay；修正为单一只读命令后，第二次已完成 candidate/replay，但测试误读不存在的 `VerificationResult.passed` 属性。改用真实 `status`/`failed_checks` 后最终门禁通过。两处都只修测试，没有放宽被测策略。

本门禁证明 Issue #184 的 measurement-policy censoring 已有可执行的 runtime-parity 修复路径，但仍不是 provider 效果证据。下一阶段只能形成新的、独立的一次性 provider amendment 候选；在协议审阅与授权前继续保持 0 provider，不 retry、replacement、backfill 或追加 Issue #184 pair。
