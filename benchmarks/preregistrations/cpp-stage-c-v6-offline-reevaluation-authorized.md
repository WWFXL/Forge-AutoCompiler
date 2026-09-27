# Stage C v6 零 Provider 离线定向重评授权预注册

日期：2026-09-27。追踪：[Issue #333](https://github.com/WWFXL/Forge-AutoCompiler/issues/333)。父候选为 Stage C v6 measurement remediation candidate，canonical SHA-256 为 `739201108b9389a30d1f2c620e124ba30f1232c764c315674e1122b524084698`。

## 研究问题

对 Stage C v5 中已经提交候选的 22 个 Forge B 臂，在修复后的离线源码 replay 和三类 oracle adapter 下重新执行 external evaluator v4。两次未生成候选的 CivetWeb attempt 不纳入重评。结果只用于事后 measurement-remediation sensitivity analysis，不替代 v5 的 A 臂 `19/24`、B 臂 `0/24` 正式结果。

## 冻结输入

- v5 manifest、报告、Session、candidate、node input、事件链、命令、产物和 evaluator evidence 全部只读。
- 来源收据逐条绑定原 Session JSON、node input、candidate、事件链、命令集合、交付产物集合、B 臂结果和既有 evaluator result 的 SHA-256。
- 新 evaluator 使用原 node input 与原 candidate；由于原 `AgentBuildNodeResult` 未单独持久化，重评显式构造 synthetic node result。它绑定原 terminal event、submission、candidate、usage 和原 evaluator 中记录的 node result SHA-256，但不声称与原对象字节一致。
- 每条重评使用独立 thread 和新 Session 树；保留原 session ID 以满足冻结 node input 的 S0 身份合同。v5 Session 不得加载后保存，也不得写入新 evaluation 或 replay。

## 执行边界

- 每条重评在 attempt 登记前获取 exact commit，生成并校验独立 `git archive`；之后 compile container、functional oracle 和 clean replay 均为 `network=none`。
- replay 从 `/repro/source.tar` 解包，校验 `source_snapshot_sha256`，不得执行远程 Git bootstrap，也不得依赖代理。
- oracle adapter 必须在 batch 前覆盖并校验 `command`、`compile_and_run` 和 `service_probe`。
- 22 条按冻结 schedule 串行执行。禁止 retry、replacement 和 backfill；只允许从 create-once、连续完整的 evaluation 前缀恢复。
- 每条结束后必须完成 Session cleanup；batch 前后及每条之间均要求 0 managed resources。

## Token 与 Provider

本阶段禁止读取 Provider 凭据、创建模型和发出 Provider 请求。每条 evaluation 保存 request token ledger；因为请求数为 0，`requests=[]` 且 input、output、total token 均为 0。token 不设硬上限，也不是终止条件；若观察到任何非零请求或 token，立即停止 batch 并判定身份违规。

## 报告

结果报告给出 22 条 S0-S5、strict success、bitwise reproducibility、按 project/replicate 的分布、原 v5 终态和修复后终态。报告必须同时声明选择条件、事后分析属性和 v5 不可覆盖边界，并生成 create-once evidence inventory。
