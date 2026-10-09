# Jev API 合同审计

## 审计目的

本审计把 TypeSafe 官方文档中的调用约束映射到 Forge 的 Jev 离线资格实验。它只确认 API、SDK 和已知模型限制，不调用 Provider，也不构成 Jev 效果证据。

审计日期：2026-10-09。

## 官方来源

- [Quick start](https://docs.typesafe.ai/introduction/quickstart)
- [API reference](https://docs.typesafe.ai/api)
- [Models](https://docs.typesafe.ai/models)
- [Confidence](https://docs.typesafe.ai/confidence)
- [Choice](https://docs.typesafe.ai/primitives/choice)
- [State](https://docs.typesafe.ai/concepts/state)
- [Python SDK](https://docs.typesafe.ai/sdk/python)
- [Python SDK usage](https://docs.typesafe.ai/sdk/python/usage)
- [RetryPolicy](https://docs.typesafe.ai/sdk/python/api/retries)
- [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)

## 调用合同

官方 Quick start 和 API reference 给出的原生接口为：

```http
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

请求顶层字段为 `state`、`model` 和 `questions`。`state` 可为字符串、对象或文本数组；多个问题在同一请求中共享 state，并独立求值。Python SDK 从 `TYPESAFE_API_KEY` 读取凭据。

Forge 使用 `typesafe-sdk==0.7.3` 的同步 `TypeSafeClient.system_one()`。本地 `httpx2.MockTransport` 已验证 SDK 实际发送 `/v1/systemone`、Bearer header、固定模型和两个并行 Choice；该验证没有建立网络连接到 Provider。

## 模型与费用

官方 Models 页面在审计日列出：

- 稳定版本：`jev-1.13.0`
- `jev-latest` 当前指向 `jev-1.13.0`
- 输入价格：每十亿 token 42 美元，即每百万 token 0.042 美元
- 输出 token：免费
- 请求上下文：总计 64k token；state 加最长单题为 32k token
- 输入：文本；主训练语言为英语

Alias 会随版本发布移动，响应的 `model` 字段报告实际执行版本。Forge 必须固定 `jev-1.13.0` 并拒绝响应版本漂移，不能用 `jev-latest` 或 `jev-preview` 维持实验身份。

## Choice 与 confidence

Choice 接收由调用方定义的有限 `criteria` 映射，返回：

- `choice`：最高概率选项；
- `probabilities`：所有选项的完整概率分布；
- `confidence`：从该分布派生的集中度。

有 `n` 个选项、最高概率为 `p_max` 时，Choice confidence 为：

```text
(n * p_max - 1) / (n - 1)
```

Forge 固定四个动作，因此公式为 `(p_max - 0.25) / 0.75`。这说明 confidence 与最高概率单调等价，不是额外的模型判断。实验保存完整概率，并使用真实动作 outcome 做独立校准；原始 confidence 只作为基线。

## SDK 重试与请求身份

SDK `RetryPolicy` 默认 `max_retries=2`，含初次请求时最多可产生三次物理请求；默认 timeout 为 30 秒。正式实验把 `max_retries` 显式设为 0，同时保留 30 秒 timeout。这样 429、529、连接失败或 timeout 都只形成一次物理 attempt，避免隐藏重试改变样本数和成本。

SDK 响应暴露 `request_id`，API 响应提供 `usage.input_tokens` 与 `usage.output_tokens`。Forge 记录 request ID、usage、延迟和按 input token 计算的费用，不记录 Authorization header 或原始 credential。

SDK debug 日志可能包含 request/response body；正式实验关闭 `typesafe_sdk` debug 日志。构建日志属于研究输入，可以进入 evidence；API key 不属于实验输入，不能进入日志或版本库。

## Jev 1.13 已知限制与实验处理

官方 jaggedness 页面记录了以下相关限制：

| 已知限制 | Forge 处理 |
| --- | --- |
| Choice 选项顺序可能影响答案，并偏向首项 | 同一请求加入正序与完全逆序 Choice，冻结顺序一致性门槛 |
| 不适合算术、精确计数和日期比较 | 阶段事实、预算计算、费用、门槛和验证全部由代码完成 |
| 多层间接推理和双重否定较弱 | instructions 直接描述“选择下一动作”，每个 option 明确边界 |
| 大量无关 state 会降低准确率 | 只发送阶段事实、有限预算、失败日志和动作成本 |
| 不适合文本生成 | 只使用 Choice，不让 Jev 生成 Shell、参数或解释 |
| 英语是主训练语言 | 问题和动作描述使用英语；原始工具日志不翻译 |
| state 中的对抗性内容可能影响判断 | 当前受控构建日志不含用户提供指令；开放世界部署不由本实验支持 |

## Forge 映射

Jev 的角色是闭集语义动作判断：代码枚举已经绑定命令并通过前置条件检查的动作，Jev 只选择一个动作或 `escalate_agent`。阶段事实和严格终点仍由 Forge 确定性组件负责。

正式请求 state 不包含项目 ID、项目族、fault 名称、动作绑定命令或标签，避免直接泄漏受控故障身份。一次请求中的两个 Choice 共享相同 state 和语义，只改变 criteria 顺序。

## 凭据交接

API key 不应粘贴到 Issue、PR、提交、报告或聊天。仓库根的 `jev-apikey.txt` 已被 `.gitignore` 排除；candidate 阶段只允许检查文件是否存在和权限，不读取内容。真实执行前应将其权限限制为仅当前用户可读，并由 authorized runner 一次性注入 `TYPESAFE_API_KEY`。

读取 credential 前还必须满足：candidate 已提交并推送、authorized amendment 已绑定 exact revision、请求/token/费用上限和 create-once evidence 路径、用户已明确授权读取与调用。

## 结论边界

官方文档支持 Jev 作为结构化闭集 Choice 判断器，也表明原始 confidence 和选项顺序不能被当作未经验证的安全门禁。当前 mock 只证明 SDK 适配和失败关闭合同可实现；它不能说明 Jev 能正确选择编译动作、概率已经校准、费用一定低于通用 LLM，或 controller 能保持严格成功率。
