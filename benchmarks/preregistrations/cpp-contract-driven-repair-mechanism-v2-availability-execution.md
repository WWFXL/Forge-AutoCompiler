# 契约驱动修复 mechanism v2 独立 availability 授权执行身份

日期：2026-09-30
状态：availability_execution_authorized_not_started
Tracking Issue：#371

## 授权来源与目的

研究负责人已在当前会话明确授权派生、提交、推送并合并独立 availability execution identity，并在合并后的
干净主干执行唯一 availability qualification。父 release-bound identity 已由 PR #370 合并为
`main@646ff59a67b27038b241358261bc92adcb100eb6`；父 manifest canonical SHA-256 为
`9ce0b7ebef27f03c4c918e4e20577cacfac971a947e60e9a787914bdc6e08197`。

本身份只授权 availability，不授权 formal batch。它产生的 marker 是基础设施可用性证据，不是 C0/T1/T2
observation。

## Provider 与请求合同

- Provider、profile 与 actual model 固定为 DeepSeek `deepseek-flash`；
- endpoint 固定为 `https://api.deepseek.com`；credential 只从冻结环境变量名读取；
- SDK/model factory 内部 retry 为 0，streaming、fallback 和 parallel tool calls 均关闭；
- 唯一 logical request 为 `Reply exactly with FORGE_READY.`；唯一通过响应为 `FORGE_READY`；
- 请求不含项目、checkpoint、arm、feedback、treatment、工具或编译内容；
- 最多 2 个 request attempts；仅当第一次为 0 response、0 recorded tokens、0 tool side effects 时才允许第二次；
- unexpected response、model identity mismatch 或已有 token 的响应不允许 retry；
- `max_recorded_tokens=null`，逐 attempt 记录 input/output/total tokens，token 总量不作停止条件；
- 禁止人工 retry、replacement、backfill 和 Provider fallback。

## Evidence 合同

evidence 目录为父身份冻结的
`.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent`，执行前必须完全不存在。
本身份唯一允许写入 `markers/availability.json`：

1. 首个 Provider request 前以 create-once 模式 claim；
2. 每个 attempt 后原子追加 request sequence、响应哈希/长度、actual model、token accounting、0 tool side effects、
   bounded error class 和 retry eligibility；
3. 最后原子转为 `passed` 或 `failed`；
4. 不保存响应正文、credential value、authorization header 或 Provider 原始错误文本；
5. marker 已存在时禁止任何 Provider request。

availability 失败不得创建 formal batch。失败 marker 必须保留，不能删除、覆盖或在相同 identity 下补跑。

## 执行顺序

1. manifest、const Schema、protocol、runner、Provider factory、配置解析和 marker schema 通过哈希门禁；
2. 必须位于干净 `main`，且 `HEAD == origin/main`，并是父 release-bound identity 的 descendant；
3. 只读核对 Docker/Compose/socket、冻结镜像、v1 evidence inventory、0 managed resources 和 v2 evidence 目录不存在；
4. 只检查 Provider config 与 credential presence，不保存 credential value；
5. claim marker；创建冻结模型；执行唯一 logical request；按冻结条件决定是否进行一次 transport retry；
6. 写入终态并核对 0 managed resources；随后只读 audit marker。

## 停止与解释边界

release、hash、配置、credential、Docker、镜像、evidence、marker 或 managed-resource 门禁失败时，不调用 Provider。
availability 未通过时立即停止后续研究执行。通过只说明 `deepseek-flash` 固定端点在该时点完成了一个确定性往返，
不能解释为模型能力、可靠性、arm outcome、treatment effect、统计显著性或模型排名。
