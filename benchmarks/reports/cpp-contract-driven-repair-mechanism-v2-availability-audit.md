# 契约驱动修复 mechanism v2 availability qualification 结果审计

> 本报告从 create-once availability marker 做只读冻结；原始 evidence 未修改。本结果是基础设施可用性证据，不是 C0/T1/T2 treatment observation。

## 身份与完整性

- 执行 release：`12681ffb0fd2997e2f572f3355e02b50a1b79744`。
- Execution manifest canonical SHA-256：`71d2f5e2e84b4e24eac5bff0fac43a092ceffa8abdf396714801f93d7ed41065`。
- Manifest 文件 SHA-256：`39f390cef095eff1f03fe066f4e66990c99aa89aa931994f805e9d110ad25dfd`。
- Marker：`.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v2-independent/markers/availability.json`。
- Marker SHA-256：`73a505f396278eaa93430264fb3ef8d86964891763d242d419e4793b475f21ee`，1,442 bytes。
- 只读 `audit` 通过：manifest/revision、attempt 顺序、token ledger、exact response、actual model、0 tool side effects 与 0 managed resources 均有效；formal batch 在该 identity 中保持关闭。

## 观察结果

DeepSeek `deepseek-flash` 的唯一预注册 logical request 在首个 attempt 完成，无 transport retry：

| Attempts | Duration | Input tokens | Output tokens | Total tokens | Exact response | Model identity | Tool side effects |
|---:|---:|---:|---:|---:|---|---|---:|
| 1 | 1054 ms | 39 | 119 | 158 | 是 | 是 | 0 |

请求前 marker 已以 create-once 模式 claim；响应正文、credential value 和 Provider 原始错误均未写入 evidence。响应只保留 SHA-256、长度、匹配结果、模型身份和 token 计数。

## 解释边界

本结果支持：固定的 `deepseek-flash` endpoint 在 2026-09-30 的该执行时点完成了预注册的确定性往返；返回值、模型身份、token accounting 和 cleanup 满足 availability 合同；formal collection 的端点可用性前置门禁已通过。

本结果不支持模型能力或总体可靠性，不是 C0/T1/T2 arm outcome，不估计 treatment effect、统计显著性或 Provider/模型排名，也不外推到其他时点、端点、项目或实验 identity。

## 后续边界

该 availability identity 已消费，不允许重跑、retry、replacement 或 backfill。正式 36-arm collection 必须使用独立 execution identity，绑定本 marker 的 SHA-256、执行 release、既有 12-checkpoint schedule、288-attempt 上限、逐响应 token 记账与第二个 endpoint-censored arm 早停规则；还必须获得独立 Provider/formal execution 授权并通过严格 preflight，之后才可创建 formal batch。
