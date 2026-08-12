# Forge C/C++ formal v4 有限端点诊断与新 canary 修正

## 背景与授权

- formal v4 authorized identity 的唯一双 provider canary 在任何模型请求前被匿名 endpoint preflight 拒绝。
- 旧 marker 固定为 `failed` / `RunnerError`，其 SHA-256 为 `9ab297d091967c15fae4f90caf18657b25214903b849fa3a695cd749fc19f724`；旧目录保持 0 provider report、0 formal ledger。
- 实验负责人于 2026-08-13 在 Issue #115 授权有限诊断和一次新的双 provider canary；当前接入介质记录为 `mobile_hotspot`。
- 该修正不改变模型、正式六槽、token 上限、Docker daemon、控制面或分析计划。

## 有限诊断

- 独立目录固定为 `/workspace/.compile-sessions/benchmark-diagnostics-formal-v4-canary-amendment`，不得包含 JSONL formal ledger。
- 顺序固定为 RichLab `gpt-5.5`，再 DeepSeek `deepseek-v4-flash`。
- 每家首先执行一次低成本请求；只有失败时才允许第二次，首次成功后禁止再次请求。
- 每次请求 timeout 为 120 秒、provider retries 为 0、输出上限为 32 tokens，提示词固定要求仅回复 `DIAGNOSTIC_OK`。
- 通过标准仅为请求完成且响应非空；两家都至少通过一次，才允许进入新 canary。
- 每次 attempt 在请求前以排他 `started` 文件预留机会，请求后以另一个排他 `terminal` 文件闭合；两类文件均不可覆盖。它们仅记录 condition/provider/model identity、序号、状态、开始和完成时间、duration、响应非空布尔值、错误类型和通过布尔值。
- 禁止记录响应正文或哈希、请求头、AK、凭据摘要、代理、SSID、IP、运营商账户或其他网络标识。
- 诊断不是 Compile Session，不创建 formal ledger，也不进入模型编译能力结果分母。

## 新 canary 与正式采集

- 新 formal evidence 目录固定为 `/workspace/.compile-sessions/benchmark-evidence-formal-v4-canary-amendment`。
- 新 canary 最多一次，无论成功、失败或进程中断均消耗机会；匿名 `/models` endpoint preflight 不再作为其门禁。
- canary 前必须重新校验旧 marker 字节哈希与失败终态、旧层 0 report/0 ledger、诊断双通过、新目录空 ledger、0 formal 残留容器和 Ubuntu 原生 daemon 门禁。
- 只有新双 provider canary 报告和 marker 都成功，才允许创建第一个 formal ledger。
- 后续仍严格串行执行原 schedule order `1, 2, 73, 74, 153, 154`，maximum recorded tokens 仍为 980,000。
- 禁止 retry、fallback、replacement、backfill 和 formal v3 slot 8-10；新 canary 失败立即停止，六槽不开始。

## 分析边界

- 旧 canary 失败与新 amendment 结果属于不同协议 identity，不能覆盖、迁移或合并为一次成功尝试。
- 诊断只能说明该时段内经认证的低成本请求路径是否完成，不能证明 provider 稳定性，也不能解释旧失败的具体网络因果层。
- 六槽结果继续服从 formal v4 的 complete-project-block 规则：完整六槽才进入 paired primary；token 边界产生的严格前缀只进入端到端描述性分母。
