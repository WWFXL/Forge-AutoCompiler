# Stage C v5 Session identity 修复预注册

日期：2026-09-27。追踪：Issue #327。来源：Stage C v4 失败审计 `benchmarks/reports/cpp-stage-c-paired-calibration-v4-failed.json`。

## 研究用途

Stage C v4 已完整闭合 `json-c` 与 `stockfish-11` 的 replicate 1 pair，并证明 `src/Makefile`、规范 build-system 输入和候选镜像 oracle 修复有效。随后 `rnnoise-0.1.1` A 臂闭合，B 臂在正式 attempt 前创建 Compile Session 失败：runner 把包含点号的 pair ID 直接拼入只允许字母、数字、下划线和连字符的 thread ID。

v4 已包含 5 个正式 arm attempt，必须永久停止。v5 不导入 v1-v4 的 outcome、pair、reachability、batch marker、源码或 Session，重新执行完整 12 projects × 2 replicates × 2 arms。

## 唯一允许变化

1. Forge B 臂 thread ID 使用完整 pair ID 的 SHA-256 与 manifest 摘要前缀构造，固定长度且只含安全字符；原 pair ID 继续保留在 evidence 和实验上下文中。
2. `validate` 与 `preflight` 除全部 12 个 Agent 输入外，还必须构造并按 Compile Session 的真实路径合同校验全部 24 个 pair 的 thread ID，并验证唯一性。
3. evidence 目录、pair ID、attempt ID、protocol、runner 和 manifest/schema identity 更新为 v5 session-identity。

任务、exact commit、project order、replicate、arm order、A/B 方法、Provider/model、不可变镜像、每臂预算、48-arm 上限、统一 evaluator、S0-S5、源码准备、网络策略、oracle、严格成功定义与 project-level 配对分析保持不变。

## 成本与身份

- evidence：`/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v5-session-identity`
- pair：`stage-c-v5-{task_id}-r{replicate}`
- attempt：`stage-c-v5-{task_id}-r{replicate}-{arm}`
- v5 reachability：最多 1 request / 5,000 recorded tokens
- v5 formal arms：48 arms / 14,400,000 recorded tokens
- v1-v4 实际消耗：286,143 recorded tokens
- 历史实际消耗与 v5 最坏上限合计：14,691,143 recorded tokens

## 执行与停止规则

合并后的干净 `main == origin/main` 先执行 validate、preflight 和真实 Docker 门禁，再执行唯一 reachability 与 batch。只有完整连续 pair 前缀可以跳过；任一 attempt 已存在但 pair 未闭合时，v5 永久停止。禁止 retry、replacement、fallback、backfill、按结果重排或导入旧 identity outcome。
