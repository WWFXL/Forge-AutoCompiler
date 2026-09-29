# 契约驱动修复 mechanism v1 availability qualification 候选 amendment

日期：2026-09-29
状态：availability_qualification_candidate_not_execution_authorized
Tracking Issue：#357

## 阶段目的

本候选从 PR #356 合并后的
`main@25b358814e4749031cc7fd3d83139a79d884f7a4` 派生，父 authorized manifest canonical
SHA-256 为 `840eac32711fc69e88609aa00b7e308fd7854bc2b7f5f4c3bffc6b5d0d39a0a0`。它只为唯一
availability qualification 准备可审阅的 amendment，不授权读取 credential、创建模型、调用 Provider、写
marker/evidence 或创建 formal batch。

## 继承边界

父身份的科学合同、六项目、双 fault stratum、12 checkpoints、36 arms、opaque schedule、C0/T1/T2 feedback
projection、终点、分析、预算、transport retry、停止规则和 create-once evidence identity 均保持逐字段相同。
本候选只允许新增 implementation release 绑定、父身份哈希、availability candidate 元数据和自身组件哈希。

36-arm formal collection 继续未授权。不得导入、覆盖、修改或回填父 candidate、authorized identity、历史
marker、ledger、attempt、report 或 evidence。

## Availability 合同

- Provider profile 与 actual model 固定为 DeepSeek `deepseek-flash`；
- formal marker 前只允许一个 logical request：`Reply exactly with FORGE_READY.`；
- 唯一接受响应为 `FORGE_READY`，且请求不含项目、checkpoint、arm、feedback 或 treatment 内容；
- 最多 2 个 request attempts；只有首请求为 0 response、0 recorded tokens、0 tool side effects 时才允许一次
  transport retry；
- `max_recorded_tokens=null`，每个 response 仍必须记录 input/output/total tokens；
- token 总量不是终止条件，请求数、transport retry 条件和停止规则仍然有效；
- availability 失败不得创建 batch，成功也不自动授权 formal collection。

以上合同在本候选中仅用于冻结未来授权输入。当前
`availability_execution_authorized=false`、`credential_read_authorized=false`、
`provider_calls_authorized=false`、`model_creation_authorized=false`、
`model_tokens_authorized=false`、`marker_write_authorized=false`。

## 非模型 preflight

`preflight` 必须在 credential、model、Provider、marker、evidence write 或 Docker Session 前完成：

1. 复算父 authorized canonical/file SHA-256 和全部 frozen component SHA-256；
2. 核对当前 revision 是 authorized implementation release 的干净 descendant；
3. 核对 Linux Docker daemon、Compose、DooD socket 和冻结镜像 ID；
4. 核对 0 Compile Session/replay/Stage C container、0 paused parent、0 managed image；
5. 核对父身份冻结的 create-once evidence 目录仍不存在。

preflight 只读取 Git、Docker 元数据和文件系统状态，不创建容器、目录、marker、ledger 或 attempt。通过只能说明
availability candidate 的非模型执行环境满足门禁，不能说明 Provider 可用。

## 命令与授权分层

- `validate`、`plan`、`preflight` 是唯一无执行授权时允许的命令；
- `availability` 与 `batch` 必须在加载 manifest、探测 runtime 或接触 credential 前 fail closed；
- 本候选 PR 合并不等于 availability execution 授权；
- 研究负责人后续明确授权后，才能派生或启用唯一 availability execution identity；
- availability 通过后仍需再次明确授权，才能创建 36-arm formal batch。

## 解释边界

本阶段只产生基础设施门禁证据。它不产生 Provider availability observation、arm outcome、treatment effect、
显著性结论或模型排名。未来一次 `FORGE_READY` 成功也只能说明固定端点在该时点完成确定性往返。
