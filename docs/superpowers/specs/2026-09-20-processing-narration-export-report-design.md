# 真实过程正文与可折叠导出报告设计

日期：2026-09-20。状态：**Issue #277 本地实现与验证完成，待 PR 交付**。

## 1. 问题证据

服务器 FMT 会话 `f99bc0ea-5fcc-41bf-86c0-a26d878b6a79` 使用 `deepseek-flash`。同一条带工具调用的 AI 消息同时包含：

```text
content: 编译会话已准备就绪（session_id=691dd52ff3fd）。接下来克隆仓库。
reasoning_content: Session prepared. Now clone the repository.
```

流式初期只有正文时，前端短暂显示中文；工具调用到达后，消息进入 processing group。当前 `convertToSteps()` 只转换 reasoning 和 tool call，不转换 `content`，最终中文正文消失，只留下英文原始推理。

PR #276 已让 Markdown/JSON 保留工具结果与编译证据，但 Markdown 把完整 ToolMessage、命令日志、replay 及 Session 原始响应直接铺开。信息虽然完整，却存在工具调用与结果分离、证据重复、长日志占满页面的问题。

## 2. 目标

1. processing group 保留并展示模型真实生成的非空 `content`。
2. `reasoning_content` 保持供应商原文，明确标记为“原始模型推理”并默认折叠。
3. 没有 `content` 时不由前端生成、翻译或推断过程说明。
4. 工具调用与相同 `tool_call_id` 的 ToolMessage 配对显示；参数、结果和长日志按需展开。
5. Markdown 使用 `<details>` 提供可折叠结构；新增可离线打开的自包含 HTML 报告。
6. JSON 继续输出完整原始消息和编译证据对象，不改变审计数据语义。
7. HTML/Markdown 只改变表现形式，不改变既有 Gateway 日志截断、脱敏和证据读取失败策略。

## 3. 实时消息展示

### 3.1 消息事实优先级

每条 AI 消息按自身真实字段处理：

- 非空 `content`：作为模型过程正文展示，即使同一消息还有 tool call 也不能丢失；
- 非空 `reasoning_content`：作为原始推理展示，默认折叠，不翻译；
- tool calls：继续按调用顺序展示；
- ToolMessage：与调用 ID 配对，保持原始返回；
- `content` 为空：不新增 narration step，不用工具名称合成中文句子。

这一区分“模型对用户说的话”和“供应商返回的推理字段”。前端不再把 reasoning 当成过程正文的替代品。

### 3.2 流式稳定性

一条消息可以从 `content-only` 增量演进为 `content + reasoning + tool_calls`。渲染身份必须以消息 ID 和 tool call ID 稳定绑定，新增字段只能增加步骤，不能让已有正文在重分组后消失。

### 3.3 展示层级

- 真实 `content` 使用现有 Markdown 渲染能力；
- 原始推理使用明确标题的折叠区；
- 工具名称、参数和结果保持现有工具卡语义；
- 不把原始推理翻译后冒充模型输出；
- 不修改 checkpoint 中保存的 Message。

## 4. 导出信息架构

### 4.1 统一数据来源

导出入口继续一次性读取 Thread 元数据、完整 messages 和所有关联 Compile Session evidence。格式渲染前建立只读关联关系：

- `tool_call_id -> tool call`；
- `tool_call_id -> ToolMessage`；
- `session_id -> commands/logs/replay/artifacts`。

JSON 仍直接序列化原始 `messages` 与 `compile_sessions`，不替换为面向展示的裁剪结构。

### 4.2 Markdown

Markdown 保持可移植文本格式，同时使用 GitHub 等常见渲染器支持的 `<details>/<summary>`：

- 助手真实 `content` 默认展开；
- 原始推理默认折叠；
- 每个工具调用与对应结果位于同一个折叠块；
- 未匹配 ToolMessage 单独进入“未匹配工具结果”折叠块，不能静默丢弃；
- 每条编译命令一个折叠块，summary 包含 role、退出码、耗时和超时状态；
- 命令正文和日志位于折叠块内部；
- artifacts 默认显示 compiled artifacts，support files 单独折叠；
- candidate verification、每次 replay 和 Session API 原始响应默认折叠；
- 失败命令/失败 replay 可以默认展开，成功项默认折叠。

纯文本阅读器仍会看到全部原文，这是 Markdown 的兼容边界，不伪装为统一交互体验。

### 4.3 HTML

新增“导出为 HTML”，生成一个自包含 `.html` 文件：

- 不加载 CDN、字体、图片或远程脚本；
- 使用语义化 `<details>` 实现折叠，离线 `file://` 可用；
- 提供会话摘要、消息、工具、命令、产物、验证、replay 和原始响应分区；
- 长文本使用可横向滚动的 `<pre>`，不截断前端已取得的数据；
- 所有动态文本、属性和 JSON 必须 HTML escape，仓库输出不能注入标记或脚本；
- 可使用只操作静态 `<details>` 的最小内联脚本提供“全部展开/全部折叠”，不得把动态内容拼入脚本；
- 已有证据日志若标记 `truncated=true`，报告必须继续显式说明仅包含末尾 16 KiB。

HTML 是默认人类阅读格式；Markdown 用于知识库、版本控制和文本检索；JSON 用于机器审计。

## 5. 安全与原始数据

- 不新增内容脱敏或翻译；沿用 Gateway 既有日志边界。
- 不把 Message 内容作为原始 HTML插入。
- HTML escape 至少覆盖 `& < > " '`。
- 文件名继续清除路径和特殊字符。
- 证据读取任一失败时，三种格式都不得生成缺项报告。
- 导出是只读行为，不调用模型、不启动编译容器。

## 6. 测试策略

### 前端逻辑

- 固定消息同时含中文 content、英文 reasoning 和 tool call，验证三类事实均保留且顺序稳定；
- content 为空时不存在 narration，不出现前端合成句子；
- ToolMessage 按 ID 配对，晚到结果仍落入正确调用；
- Markdown 断言 `<details>`、summary、参数、完整结果和未匹配结果；
- HTML 断言完整文档、动态内容转义、自包含、无外部 URL/资源引用；
- JSON 与输入原始对象深度相等。

### 浏览器

- 流式 fixture 从 content-only 更新为 content + reasoning + tool call，中文正文始终存在；
- 原始推理默认折叠，展开后看到供应商原文；
- HTML、Markdown、JSON 均能从当前会话和历史列表下载；
- HTML 在新页面离线加载，工具、日志和 raw evidence 默认折叠并可展开；
- 页面和报告无脚本注入、console error、横向布局溢出。

## 7. Runtime 身份与边界

Runtime v5 保持历史只读。本次改变 processing message 与导出报告的外部行为，新增仅允许交互产品验证的 Runtime v6；不授权 provider canary、formal collection 或历史 evidence 改写。

本次不改变 Lead/Compiler 提示词，不试图强制供应商内部推理使用中文，不修改 Compile Session、replay 或 artifact 验证语义，不调用真实模型。

## 8. 验收标准

- FMT 类消息的中文 `content` 在 tool call 到达后仍可见。
- 英文 `reasoning_content` 位于“原始模型推理”折叠区，原文不变。
- content 缺失时前端不生成替代正文。
- Markdown 和 HTML 中长工具结果、命令日志及 raw Session 默认折叠。
- HTML 离线可用，动态文本无法注入 HTML/JavaScript。
- JSON 继续完整保留原始 messages/evidence。
- Runtime v5 与历史实验资产没有 diff。
