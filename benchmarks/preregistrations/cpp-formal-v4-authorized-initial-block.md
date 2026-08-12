# Forge C/C++ formal v4 首批完整项目块授权

## 授权

- 实验负责人于 2026-08-12 明确授权 Issue #111 记录的首批范围。
- 项目固定为 `cppitertools`；这是冻结 schedule 中第一个项目，不依据 v3 结果选择。
- 授权原 schedule order 为 `1, 2, 73, 74, 153, 154`，覆盖两个 condition 各三次重复，共 6 个 physical attempt。
- manifest 继续保留完整 180-slot 计划和原 schedule hash；runner 只投影授权顺序，不重编号或改写原 slot identity。
- maximum recorded tokens 固定为 980,000，在当前 attempt 完成 terminalization、finalization、cleanup 和 orphan reconciliation 后、创建下一槽前检查。

## 前置门禁

- 只允许 WSL2 `Ubuntu` 中由 `docker.service` 管理的原生 Docker Engine、`default` context 和 `/var/run/docker.sock`。
- 唯一 evidence 目录为 `/workspace/.compile-sessions/benchmark-evidence-formal-v4-authorized-initial-block`。
- 首条 ledger 前必须通过 Ubuntu daemon gate、Compose/DooD 非模型 preflight、空 ledger、0 formal 残留容器和一次双 provider canary。
- 正式 canary 最多尝试一次；无论 provider 调用、endpoint preflight 或进程在哪一阶段失败，均保留 attempt marker 并停止，不能反复执行直到通过。

## 执行与停止

- 按 `1 -> 2 -> 73 -> 74 -> 153 -> 154` 严格串行执行，不允许 retry、fallback、replacement、backfill 或创建 v3 slot 8-10。
- 单 attempt 继续使用 1,800 秒总墙钟、120 秒 cleanup reserve、最多 2 次 Compiler 调用和 48 次模型请求。
- 六个授权 slot 全部终结、recorded-token boundary、runtime/daemon/canary gate、ledger/cleanup 不变量或用户中断任一触发时停止。
- token boundary 使 project block 未完成时，已有 attempt 只进入端到端描述性分母，不进入 paired primary estimate。
- 首批之外的 174 个 slot 均未授权，需要新的实验负责人确认和新协议 identity。
