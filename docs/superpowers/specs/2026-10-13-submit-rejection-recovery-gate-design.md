# Submit 拒绝后的有界恢复门禁设计

## 问题

Issue #447 的 `mjson/H2` 证明 Runtime v5 能拒绝只在脏工作区成立的 recipe，但拒绝后无法继续修复。原因由两个状态缺口叠加构成：

1. Runtime v4 在 submit 返回后仍记录 submit 前 snapshot。CandidateVerifier 执行的受信 functional smoke 会追加命令，导致当前 frontier 与已记录 frontier 不同；
2. `submit_candidate_v1` 是 Workflow Node 自定义工具，没有沿用产品 `submit_build_result` 在拒绝时释放 post-build phase 的语义。即使 Harness 放行，后续 build 仍会被 post-build guard 拒绝。

本阶段建立 Runtime v6，只验证拒绝后的恢复状态是否闭合。它是正式 H0/H1/H2 比较前的零 Provider 工程门禁，不形成 treatment effect。

## 状态机

Runtime v6 继承 Runtime v5 的 `workspace_ready` 与 `replay_closure_ready`，新增每个 frontier 的 submit 和 repair 状态：

- `unsubmitted`：当前 candidate-ready frontier 尚未提交；任何 Shell 都被拒绝，必须先 submit；
- `rejected_repair_open`：当前 frontier 的 submit 返回非终态拒绝；允许一个有界 repair window；
- `repair_build_consumed`：窗口已执行一个非 staging 修复命令；只允许最多一个 `artifact_stage`；
- `repair_window_closed`：窗口已消费、出现不允许的动作或达到上限；后续 Shell 被拒绝，必须重新 submit；
- `accepted_or_terminal`：submit 已接受、返回终态拒绝或响应不可解析；不发放 repair 权限。

frontier 继续绑定命令计数、成功 recipe 命令和 staged artifact 路径。submit 返回后必须重新读取持久化 Session，并对**当前权威 frontier**记录结果。

## Repair window

一个被拒 frontier 最多允许：

1. 一个 `build` 修复命令；
2. 若第一条是成功 build，随后最多一个 `artifact_stage` 命令；
3. 窗口关闭后必须再次 submit。

`diagnostic`、`smoke` 和第二个非 staging 修复命令不属于恢复窗口。每次命令调用在执行前消费对应许可；即使命令被底层策略拒绝、失败或没有改变 frontier，也不能重获同一许可。相同 frontier 的重复 submit 不重置已消费许可。

这一两步上限是生成合法 replay recipe 的最小边界：正确 build 命令之后还必须有顺序合法的 artifact-stage 命令。把“一次修复”实现成单条 Shell 会让 mjson 修复后的 recipe 无法同时满足命令顺序和 `artifact_stage` 必需条件。

## Submit 结果与 post-build phase

- 只解析 `submit_candidate_v1` 的结构化 JSON 响应；`accepted=false` 且 `terminal_for_agent=false` 才打开窗口；
- 非终态拒绝后，Runtime v6 仅为当前 Node 释放 post-build phase，使修复 build 可以执行；
- accepted、terminal rejection、异常或不可解析响应不释放 phase，也不发放窗口；
- CandidateVerifier、functional oracle、replay closure、candidate create-once 和 external evaluator 均保持原语义。

## 零 Provider 门禁

主要 Docker 案例构造与 `mjson` 同构的脏工作区陷阱：

1. 顶层 `make` 先生成 `test/unit_test`，再因额外目标失败；
2. `make unit_test` 在脏工作区返回 up-to-date，被作为初始成功 build；
3. 首次 submit 的 clean replay 在隐式单文件链接处失败，分类为 `recipe_execution_failed`；
4. Runtime v6 释放 post-build phase，并允许 `make -C test test`；
5. 允许一次重新 stage；
6. 第二次 submit 使用新 build/stage recipe，通过 CandidateVerifier 和 replay closure并冻结候选。

同时验证普通 candidate-ready 必须先 submit、第二个 repair build 被拒绝、窗口消费后 Shell 被拒绝、无效合同不形成无限窗口、预算终止闭合、Session cleanup 完成，以及 #447 inventory canonical SHA-256 保持不变。

## 结论边界

通过只说明 Runtime v6 修复了已观察到的 submit-rejection 恢复死锁，并保持严格终点和有界执行。它不证明 H2 提高严格成功率、降低成本、改善自然失败，亦不改变 #447 的 `3/3、3/3、2/3` 描述性结果。通过后才能冻结新的 18-arm 正式比较设计。
