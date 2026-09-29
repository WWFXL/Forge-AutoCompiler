# 契约驱动修复 mechanism v1 availability qualification 结果审计

> 本报告从 create-once availability marker 做只读冻结；原始 evidence 未修改。本结果是基础设施可用性证据，不是 C0/T1/T2 treatment observation。

## 身份与完整性

- 执行 release：`09d7ff36ca081f5bfa39f8e1d6f3b3daa53c93a0`。
- Execution manifest canonical SHA-256：`cf21d2c228e46b39a3287d3c9ab7139c9f24d8ba36990e4b8e94475c9b0d7839`。
- Manifest 文件 SHA-256：`83d78d1a0512472ef45a801f8d37537effc4f43fbe4244dc936cd14b6cf44e08`。
- Marker：`.compile-sessions/benchmark-evidence-contract-driven-repair-mechanism-v1-authorized/markers/availability.json`。
- Marker SHA-256：`8527d64acc50a88ea0d5f8b64fc25971d68294fb142b043f1e889586ad088bee`，1,437 bytes。
- 只读 `audit` 通过：manifest/revision、attempt 顺序、token ledger、exact response、actual model、0 tool side effects 与 0 managed resources 均有效；formal batch 在该 identity 中保持关闭。

## 观察结果

DeepSeek `deepseek-flash` 的唯一预注册 logical request 在首个 attempt 完成，无 transport retry：

| Attempts | Input tokens | Output tokens | Total tokens | Exact response | Model identity | Tool side effects |
|---:|---:|---:|---:|---|---|---:|
| 1 | 39 | 19 | 58 | 是 | 是 | 0 |

请求前 marker 已以 create-once 模式 claim；响应正文、credential value 和 Provider 原始错误均未写入 evidence。响应只保留 SHA-256、长度、匹配结果、模型身份和 token 计数。

## 解释边界

本结果支持：固定的 `deepseek-flash` endpoint 在 2026-09-29 的该执行时点完成了预注册的确定性往返；返回值、模型身份、token accounting 和 cleanup 满足 availability 合同；formal collection 的 endpoint 可用性门禁已解除。

本结果不支持模型能力或总体可靠性，不是 C0/T1/T2 arm outcome，不估计 treatment effect、统计显著性或 Provider/模型排名，也不外推到其他时点、端点、项目或实验 identity。

## 后续边界

该 availability identity 已消费，不允许重跑、retry、replacement 或 backfill。正式 36-arm collection 必须使用独立 execution identity，绑定本 marker 的 SHA-256、执行 release、既有 12-checkpoint schedule、288-attempt 上限、逐响应 token 记账与第二个 endpoint-censored arm 早停规则；严格 preflight 通过前不得创建 formal batch。
