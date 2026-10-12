# 进展感知结构化 Agent Harness 资格 v2 设计

## 失败驱动的修订

`cpp-progress-aware-harness-qualification-v1` 已按 create-once 合同封口。其进展快照、上下文裁剪、ready
门禁、快照提交、pre-freeze verifier、预算计数和 cleanup 全部通过；external evaluator 的 S0-S4 通过，S5 在
clean replay 获取 exact commit 时因 `gnutls_handshake() failed` 退出 128。失败发生在任何 replay 编译命令之前，
不构成 H1 机制失败，也不得改写为 v1 成功。

## v2 唯一变化

v2 继续使用同一 `cmake-cxxopts-state-3` 工作 checkpoint、Runtime v4、脚本动作、预算和严格裁判。它只增加
离线 replay source：从同一项目、同一 exact commit 的冻结 `cmake-cxxopts-state-1` source-ready checkpoint 复制
`workspace.tar.gz` 到新 Session 的 `repro/source.tar`，核对 SHA-256
`96bed50fe9c3f1a3ce6925d6828d252ac215fad7e48f35a34efd1d19a4b5ad77`，再绑定
`CompileSession.replay_source_archive_sha256`。

该 archive 是 configure 前的源码树，不包含 state-3 的 `build/` 或候选产物。Forge 已有 replay bundle 合同会在
新容器中校验 archive SHA-256、解包源码并执行相同 recipe；生成脚本不得包含 `git fetch`。这使 clean replay 的
源码身份继续受哈希约束，同时消除外部 Git 网络对 S5 的干扰。

## 资格门槛

v1 的全部门槛继续适用，并新增：

1. v1 evidence inventory 保持 `b45dd050963ecb033b15f246f62c4d0db4fa0b48c450e352d8d18ffc258024cd`；
2. source-ready checkpoint 与工作 checkpoint 的 repository URL、commit 和 image identity 一致；
3. Session、repro bundle 和 replay snapshot 使用同一 source archive SHA-256；
4. replay build script 包含 archive 解包且不包含 `git fetch`；
5. S0-S5、functional oracle、artifact verification、cleanup 全部通过。

## 解释边界

v2 通过只能解除 H1 Provider 比较之前的工程阻塞，不能把 v1 重分类为成功，也不能证明 H1 比 H0 更好。v2
失败则停止 Provider 比较；若仍为外部基础设施失败，只能建立新的独立 identity，不能重跑或覆盖 v1/v2。
