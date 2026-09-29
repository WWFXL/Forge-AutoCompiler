# 契约驱动修复 mechanism v1 release-bound 授权身份

日期：2026-09-29
状态：release_bound_identity_not_execution_authorized
Tracking Issue：#355

## 阶段目的

本身份从 PR #354 合并后的 `main@a63f328b0cd2771ec656414e697ebbb831391ed9` 派生，原样继承父 candidate 的
六项目、双 fault stratum、12 checkpoints、36 formal arms、反馈合同、opaque schedule、终点、分析、预算和
停止规则。父 candidate canonical SHA-256 为
`fc1ec9adfb9961e258e4bb8fad8f1ae2f0f5e1b1356748d53d5783dd55700f8f`。

该 manifest 只表示研究负责人授权实现和审阅 release-bound identity。availability 和 formal collection 仍需
各自的明确执行授权；本阶段不得读取 `DEEPSEEK_API_KEY`、创建模型、调用 Provider、创建 Docker Compile
Session、formal attempt、marker、ledger 或 evidence。

## 不允许改变的科学合同

以下字段必须与父 candidate canonical 相同：Provider `deepseek-flash`、无 token ceiling、逐响应 token
accounting、每 arm 8 request attempts、36 formal arms 最多 288 attempts、availability 最多 2 attempts、
identity 最多 290 Provider attempts、C0/T1/T2 feedback projection、两个 checkpoint strata、strict endpoint、
六项目与 exact commits、schedule、主要/次级/支持性比较、删失处理和第二个 endpoint-censored arm 后停止。

## Release 与环境

- 科学合同 release revision 固定为 `a63f328b0cd2771ec656414e697ebbb831391ed9`；
- protocol、runner、预注册、父 manifest/Schema 和 Runtime authority 以 SHA-256 绑定；
- 执行实现必须是该 revision 的干净 descendant，并在 preflight、marker、attempt 和 report 中记录 exact SHA；
- formal execution 只允许合并后的 `main`，开发分支最多运行不写 evidence 的非模型 preflight；
- 编译镜像固定为 `autocompiler:stage-c-v1@sha256:adbef4a26de49e9cd2c361a50b5fe2a000073a343b072ed0e515cc67e6e758b1`；
- 网络策略固定为 clone 后 network none，`parallel_tool_calls=false`。

## 独立 evidence identity

未来 evidence 目录固定为
`.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v1-authorized`，必须 create-once，且在
执行授权 marker 前完全不存在。availability marker、batch marker、36 个 attempt/result 和 batch report 均使用
该目录的新 identity；不得导入、覆盖或回填任何历史 evidence 或父 candidate 文件。

## 非模型 preflight

`preflight` 必须在 credential、model、Provider、marker、evidence write 或 Docker Session 前完成：

1. 复算父 candidate canonical/file SHA-256 和全部 frozen component SHA-256；
2. 核对当前 revision 是科学合同 release 的干净 descendant；
3. 核对 Linux Docker daemon、Compose、DooD socket 和冻结镜像 ID；
4. 核对 0 Compile Session/replay/Stage C container、0 paused parent、0 managed image；
5. 核对独立 evidence 目录尚不存在。

preflight 只允许读取 Git、Docker 元数据和文件系统状态，不创建容器、目录、marker、ledger 或 attempt。通过结果
只能表示执行基础设施准备就绪，不能解释为 Provider 可用、arm outcome 或 treatment effect。

## 授权分层

- 当前：`identity_implementation_authorized=true`；
- 当前：availability、formal collection、credential、Provider、model creation、Docker Session、formal attempt、
  evidence write、model tokens 和 execution started 全部为 false；
- `validate`、`plan`、`preflight` 是唯一允许命令；
- `availability` 与 `batch` 在任何 credential、Provider 或 evidence 动作前 fail closed。

下一步是代码审阅、合并并记录 authorized implementation revision。之后由研究负责人单独决定是否授权唯一
availability qualification；只有它通过且 formal collection 再获明确授权，才能创建 36-arm batch。
