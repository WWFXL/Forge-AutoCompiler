# Workflow + Jev + Agent 混合编译链路实施计划

日期：2026-10-11。设计：`../specs/2026-10-11-jev-hybrid-workflow-design.md`。追踪：Issue #409。

## A. 设计冻结

- [x] 核对 Issue #408 正式结论、知识库长期机制和当前产品入口。
- [x] 创建并回读独立 tracking Issue #409。
- [x] 从冻结结果提交建立 `yiwei/409-jev-hybrid-workflow` 分支。
- [x] 冻结职责边界、状态所有权、控制权交还、固定安全预算和严格终点。
- [x] 提交并推送 spec/plan，使其先于实现和实验结果。

## B. 最小协调器

- [x] 为观察、步骤结果、预算、trace 和最终结果定义不可变数据结构。
- [x] 实现异步协调循环和同步/异步 callback 边界。
- [x] 复用 `route_next_action` 与 `dispatch_route`，不复制校准逻辑。
- [x] 实现 Jev 异常、直接动作失败和 Agent handoff 的 fail-closed 行为。
- [x] 保证任何 callback 结果都不能直接绕过 observer 的严格终态。
- [x] 从 `deerflow.compile` 暴露内部候选 API，但不改变 Lead Agent 默认入口。

## C. 零 Provider 资格

- [x] 添加高置信度直接动作、低置信度拒答、Provider 异常、动作失败和 Agent 回退测试。
- [x] 添加状态未推进、预算耗尽、缺失 verifier、Agent 伪成功和 trace 重建测试。
- [x] 运行协调器、Jev controller 和 Agent Workflow 相邻回归。
- [x] 运行后端 lint 和完整非 Docker 测试；完整收集仍有 13 个历史 opaque-provenance 导入错误，聚焦与相邻回归通过。

## D. 真实 Docker 资格

- [x] 运行 `scripts/require-docker-runtime.sh`。
- [x] 建立独立零 Provider qualification identity 和 create-once 输出目录。
- [x] 用 CMake、Make、Autotools 三个最小 fixture 验证真实 bound command、严格 evaluator、clean replay 和 cleanup。
- [x] 验证 0 credential read、0 Provider request、0 formal attempt、0 managed resources。
- [x] 生成版本化 qualification JSON/Markdown 报告并冻结哈希；v1/v2 失败保持只读，v3 为 `3/3` strict。

## E. Provider canary

- [x] 只在 D 通过后冻结 `cpp-jev-hybrid-workflow-canary-v1` manifest、Schema 和预注册。
- [x] 固定 exact commit、Jev/Agent 模型、请求/token/费用上限、超时、停止规则和独立 evidence 目录。
- [x] 先执行 release、parent、Docker、credential presence 和 0-orphan preflight，不输出 credential。
- [x] 执行最小三构建系统 canary；Provider 异常作为结果保留，不 retry/replacement/backfill。
- [x] 生成 create-once 报告，审计控制权交还、严格成功、成本、cleanup 和 evidence inventory。

## F. 阶段结论与发布

- [x] 根据设计中的通过/停止条件给出 `proceed_to_natural_failure_evaluation_design`。
- [x] 更新 `RESEARCH_STATUS.md`、工程交接和知识库长期机制文档。
- [x] 运行 `git diff --check`、报告哈希和 0 managed resource 复核。
- [ ] 提交、推送并创建中文 PR，通过 `Closes #409` 关联 tracking Issue。

## 固定边界

- Issue #408 及更早 manifest、报告和 raw evidence 永久只读。
- 本阶段不恢复偏序义务状态 v1、合同反馈或 mechanism v2。
- 固定安全预算不作为动态预算控制有效性的证据。
- qualification/canary 不解释为自然失败 treatment effect 或通用模型排名。
