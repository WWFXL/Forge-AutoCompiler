# C++ 进展感知结构化 Harness H0/H1 v3 正式复现授权修订

## 身份与授权

本文件将未授权 candidate `cpp-progress-aware-harness-comparison-v3-candidate` 派生为独立 create-once identity
`cpp-progress-aware-harness-comparison-v3-authorized`。Candidate revision 固定为
`c5ac1e0875b1de84594afa91e2a1fa5bfb2bdde7`，manifest canonical SHA-256 固定为
`128c629dbcb5da28e0b68fb3fdfb0320e09cd1f86cac505b028d780ca692ced0`。

研究负责人在 2026-10-13 当前会话授权 Issue #440 使用 Docker、读取 `DEEPSEEK_API_KEY`、调用 DeepSeek、
创建正式 attempt 并写入新的正式 evidence，持续到得出 H1 正向信号能否复现的关键结论。历史 evidence、candidate
identity 与旧报告保持只读；replacement、backfill、失败重跑、删除失败 observation 和结果后修改阈值均未授权。

正式执行 revision 必须位于 `yiwei/440-h0-h1-v3-execution`，包含 candidate revision，工作树干净且该 revision
已经推送到同名远端分支。Q0 前记录该 revision；Q0、Q1、Q2 必须绑定同一 revision 和同一 manifest hash。

## 研究问题与冻结设计

RQ、样本、H0/H1 treatment、正式 schedule、模型、预算、判据和解释边界全部继承
`cpp-progress-aware-harness-comparison-v3-candidate`。本修订不读取 v2 arm outcome 来改变选择，不池化历史
observation，也不改变 checkpoint 深度机械旋转 `1 -> 3`、`2 -> 1`、`3 -> 2`。

- Q0：9 个正式 checkpoint 的零 Provider reference，必须 `9/9` strict。
- Q1：三个额外 checkpoint 上 H0/H1 共 6 arms，必须全部分类、计量和 cleanup 闭合，并满足 treatment separation。
- Q2：9 个正式 checkpoint、每项 3 次重复、H0/H1 配对，共 27 pairs / 54 arms。

Canary 数值不进入正式 estimate。Q0 或 Q1 失败时不得进入后续阶段。

## Provider 与预算合同

- Provider/profile/actual model：DeepSeek `deepseek-flash`；非流式、thinking 关闭、模型重试为 0。
- 每臂：最多 24 requests，停止阈值 300,000 recorded tokens，单响应上界 100,000 recorded tokens。
- 每臂授权上界：400,000 recorded tokens；60 个 Provider arms 的授权上界为 24,000,000。
- 整体最多 1,440 requests；Provider 费用上界为 `$28.80`。

完成的响应必须先把完整 usage 写入事件和 tracker，再判断 300,000 token 停止阈值。达到阈值后不得发起下一请求；
单响应超过 100,000 token 时保留该响应实际 usage，并以 `budget_contract_violation` fail closed。usage 缺失、负数、
或 input/output/total 不一致时以 `usage_incomplete` fail closed。

每个 arm 必须满足：

1. `model.request_started = completed + failed + usage_incomplete`；
2. request sequence 唯一且每个 started request 恰有一个终结事件；
3. completed event 的 input/output/recorded token 与 node result、budget tracker 和报告一致；
4. `usage_incomplete` 和 `budget_contract_violation` 数量均为 0；
5. cleanup、checkpoint/source 绑定、动作后观察和严格终点证据闭合。

任一 usage 或预算合同硬门禁失败，正式结论为证据无效；不得用效果数值覆盖完整性失败。

## 主要判据

只有全部硬门禁通过，且以下三项同时成立，才支持
`supports_same_project_cross_state_progress_aware_harness_replication`：

- H1-H0 strict success 差值的项目聚类单侧 95% bootstrap 下界不低于 `-0.10`；
- H1 Provider 总费用相对 H0 至少降低 20%；
- CMake、Make、Autotools 中 H1 strict 计数均不低于 H0。

替代通过路径保持 candidate 冻结值：strict 差值下界大于 0、点估计至少 `+0.10`、H1 费用增幅不超过 10%，
并满足分系统不退化和全部硬门禁。否则决定为 `stop_progress_aware_harness_as_primary_mechanism`。

## 结论边界

正向结果只支持当前 9 个项目族、受控 checkpoint、`deepseek-flash`、固定预算和严格 Forge 终点下的同项目族
跨状态深度复现。它不证明单一 Harness 组件的因果贡献，不评价 Jev、动态预算 controller、自然失败、开放世界、
未见项目泛化或 Claude Code/Codex 等通用 Agent Harness。
