# Workflow + Jev + Agent 混合链路零 Provider 资格预注册

日期：2026-10-11。追踪：Issue #409。身份：`cpp-jev-hybrid-workflow-qualification-v1`。

## 研究问题

冻结实现 `062d7d7830364c984bc33f3d74df03c2f66d47f4` 能否在真实 Forge Compile Session 中保持以下合同：

1. Jev 只能选择代码绑定动作，直接动作返回后由确定性 Workflow 继续执行；
2. Jev 拒答后只发生一次有界 Agent handoff，Agent 返回后 Workflow 重新读取权威状态；
3. 回调不能自行宣告成功，只有 Forge 严格 submit、显式 smoke、provenance 和 clean replay 全部通过才算成功；
4. CMake、Make、Autotools 三类 Session 均能 finalize，结束后没有受管容器、paused parent 或受管镜像残留。

这是工程链路资格，不估计自然失败总体效果，也不评价 Jev 或 Agent 的模型能力。

## 固定 Case

- CMake：`MattClarkson/CMakeHelloWorld@6fda0b1`，scripted Jev 选择 `configure`，随后 Workflow build、stage、smoke、submit。
- Make：`redis/hiredis@60e5075`，scripted Jev 选择 `build`，动作生成一个最小链接验证程序，随后 Workflow stage、smoke、submit。
- Autotools：`libcheck/check@11970a7`，Jev 响应固定缺失并升级 scripted Agent；Agent 执行 dependency、configure、build、stage、smoke 后交还控制权。

scripted Jev 只构造满足现有 `jev_controller` 合同的固定概率分布，不调用 Provider。scripted Agent 只执行 manifest 已绑定命令，不调用模型。真实副作用全部经过 `_run_container_bash_impl`、`submit_build_result_impl` 和 `cleanup_and_finalize_compile_session_impl`。

## 预算与停止规则

- 3 个 qualification attempt，每个 case 恰好一次；不 retry、replacement 或 backfill。
- 每个 case 最多 2 个恢复循环、1 个直接动作、1 次 Agent handoff、1800 秒总墙钟。
- 单命令最多 900 秒。
- 首个不可恢复失败立即停止后续 case，保存失败 marker、已完成 rows 和 cleanup 状态。
- Provider call、credential read 和 formal attempt 必须全部为 0。

## 通过门槛

以下条件必须同时成立：

- 三个构建系统都形成真实 marker、冻结 selection 和成功命令记录；
- 三个 case 都由 observer 返回 `strict_success`，且 submit 与 clean replay 均为 `passed`；
- 至少观察 2 次 Jev 直接动作后的控制权交还；
- 至少观察 1 次 Agent handoff 后的控制权交还；
- 三个 Session 均 cleanup 成功并进入 `completed`；
- 结束后受管资源为 0；
- identity、组件哈希、镜像 ID、预算和 create-once 输出没有漂移。

全部通过时决定为 `proceed_to_provider_canary_identity_freeze`。任一失败时决定为 `stop_and_repair_hybrid_workflow`。

## 结论边界

通过只能说明限定 fixture 上的多步控制链、回退、严格终点和清理闭合。它不能说明自然失败成功率、Provider 成本下降、Jev 校准迁移、动态预算优势或开放世界泛化；这些主张需要新的 Provider canary 和后续未见项目族对照实验。
