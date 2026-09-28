# Stage C v7 workspace 失败审计

Stage C v7 authorized canary 在 `main@5a01b2ac51da57b699202de02dec6065a8f643be` 形成不可覆盖终态。唯一 reachability 使用 `deepseek-flash`，1 次请求记录 46 input、24 output、70 total tokens，并通过冻结响应与模型身份核对。

首个 `theora` attempt 在 Compile Session 创建前触发 `PermissionError`。错误哈希 `1f6ef341...e6a6` 精确对应 `/workspace/.compile-sessions/stage-c-v7-b-278bb68aa24fa13d3858797e9fd6fcbc-261da6d0d0416073` 的目录创建拒绝。该路径的父目录为 `root:root 0755`；全局 `Paths()` 因宿主存在 `/workspace` 而隐式选择了它。原 preflight 只检查 evidence 文件为空，没有检查 evidence 路径可创建、Compile Session process root 可写或 host root 与 process root 一致。

本 attempt 为 0 模型请求、0 Agent step、0 工具调用、0 命令、0 attempt tokens，未创建 Session、候选或 evaluator 结果。Batch 按 stop-on-first-failure 停止，后三项未启动；cleanup 与零 managed resource 核验通过。该终态不能用于判断 Agent、pre-freeze candidate verifier、external evaluator 或四个任务的工程效果。

Evidence 共 7 个文件、7,416 bytes；按 `relative-path<TAB>sha256<TAB>size<LF>` 排序连接后的 inventory SHA-256 为 `ca7e467911c5ac798bc9ed2042b5dd949bab9bbabbefa31e0bc0c5ee954e404f`。完整逐文件哈希见同名 JSON。

v7 batch 永久禁止 retry、replacement、backfill 或续跑。下一 identity 必须显式绑定 release repository root 作为 process/host workspace，在 credential、model、Provider 和 marker 前检查 evidence 与 Compile Session 路径，并先通过零 Provider Docker lifecycle 门禁。
