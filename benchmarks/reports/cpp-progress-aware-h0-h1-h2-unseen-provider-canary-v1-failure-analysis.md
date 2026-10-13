# H0/H1/H2 未见项目族 Provider Canary 失败分析

本文是 `cpp-progress-aware-h0-h1-h2-unseen-provider-canary-v1` 冻结 evidence 的只读 sidecar。它不修改正式
分类、资格决定、分母或 raw evidence，也不把 canary 解释为 treatment effect。

## 审计对象

- Arm：`05-make-mjson-h2_runtime_v5`
- 终态：`no_candidate`
- Provider：31 requests，453,780 recorded tokens
- Harness：10 次 submit、7 次 replay closure、14 条命令、31 次 progress snapshot
- 最终限制：未达到 600,000 recorded-token 停止阈值或 36-request 上限；在 96 Agent steps 后以
  `node_status=no_submission` 终结

## 证据链

1. Agent 首先执行 `make`。该命令先成功编译并运行 `test/unit_test`，随后因 `all` 目标继续调用不可用的嵌套
   Docker 构建而以 exit 2 失败。失败命令仍在工作区留下了有效的 `test/unit_test`。
2. Agent 随后执行 `make unit_test`。由于二进制已经存在，该命令只返回 `unit_test is up to date`，没有从干净源码
   重建目标；Harness 却将它记录为成功 build。artifact stage 和 functional smoke 都在当前工作区通过。
3. H2 对七个候选执行 pre-freeze replay closure。七次均从干净 source archive 启动，七次均分类为
   `recipe_execution_failed`、exit 2、actual delivery 为空。干净环境中的 `make unit_test` 触发 GNU Make 隐式规则，只链接
   `unit_test.c`，遗漏 `../src/mjson.c`，因此出现 `mjson_*` 和 `jsonrpc_*` undefined reference。
4. 七次 closure 的 frontier SHA-256 和 recipe fingerprint 均不同，说明 Agent 尝试了不同 command-ID 组合；但 Session
   中唯一正确生成目标的命令是失败的 `make`，不能进入 replay recipe，而唯一成功 build `make unit_test` 又不具备干净
   重建语义。已有命令集合中不存在可接受配方。
5. 每次 submit 都会先追加一次受信 functional smoke 命令。Runtime v4/v5 的 progress guard 在 submit 前记录已尝试
   frontier；smoke 使 `command_count` 改变，submit 后的新 frontier 又被视为“尚未提交”。因此后续修复 Shell 被
   `candidate_ready_requires_submit` 拒绝。该 arm 共出现 14 次这种拒绝，Agent 无法执行正确的
   `make -C test test`，只能继续提交或重组旧 ID。
6. 最后三次 submit 分别又触发 `invalid_contract`、`command_role_invalid` 和 `command_order_invalid`；最终图步预算耗尽。

## 指标解释修正

主报告中的派生字段 `replay_closure_rejections=0` 不表示 closure 没有拒绝候选。冻结 reporter 只统计以
`replay_` 开头的 rejection code，以及 `missing_bootstrap_step`、`missing_generated_input`；它遗漏了
`recipe_execution_failed`。Raw events 明确包含 7 个 `candidate.replay_closure_completed(passed=false)` 和紧随其后的
7 个 `candidate.submit_rejected(rejection_codes=["recipe_execution_failed"])`。主报告和 raw evidence 保持原样，本
sidecar 负责说明该派生指标缺口。

## 结论与下一门禁

- H2 replay closure 在本 arm 上发挥了预期作用：它阻止了一个在当前工作区可运行、但无法从干净源码复现的候选进入
  正式 evaluator。
- 失败不能归结为 Token 预算不足。增加 Token 或 request 不能解除 progress guard 的恢复死锁；96-step 限制只是最终
  终结点。
- 该 observation 暴露的是 H1/H2 状态建模与动作门禁的组合缺口：`workspace_ready=true` 在 closure 拒绝后仍触发
  “必须再次 submit”，而没有表达“候选已拒绝、允许执行一次修复动作”。
- Canary 仍按预注册通过其生命周期、计量、instrumentation、evaluator coverage 和 cleanup 硬门禁，正式决定保持
  `proceed_to_unseen_three_arm_formal_comparison_design`。但在冻结 18-arm 正式比较前，应先建立独立零 Provider 工程
  门禁：submit 拒绝后的当前 frontier 必须允许有界 repair command；正确修复应能新增可复现 build 命令并再次提交，且
  未发生拒绝时的 candidate-ready 强制提交行为不得退化。

## 权威来源

- 主报告：`benchmarks/reports/cpp-progress-aware-h0-h1-h2-unseen-provider-canary-v1.{json,md}`
- Raw events：`.compile-sessions/benchmark-evidence-cpp-progress-aware-h0-h1-h2-unseen-provider-canary-v1/q1/arms/05-make-mjson-h2_runtime_v5/session-evidence/agent-workflow/q1-05-make-mjson-r1/events.jsonl`
- Session：`.compile-sessions/benchmark-evidence-cpp-progress-aware-h0-h1-h2-unseen-provider-canary-v1/q1/arms/05-make-mjson-h2_runtime_v5/session-evidence/session.json`
- Inventory canonical SHA-256：`e911bb1d5d40fc270ede9921bbb4781bcd75d4851bf8fe4ef1f95d02f97e6696`
