# Compile Runtime v6 工程契约

Runtime v6 继承 `e7c93d1df6a3311bea64f0ba84bdd3815c55d353` 的 v5 实现，修复带工具调用的 AI 消息在 processing group 中丢失真实正文的问题，并把长篇导出整理为可折叠报告。Runtime v2/v3/v4/v5 的身份、文档与历史实验 evidence 均保持只读。v6 只允许交互式产品验证，不授权 provider canary 或正式实验。

## 实时消息事实

- AI 消息的非空 `content` 是模型真实面向用户生成的正文。即使同一消息随后出现 tool call，正文仍保留在 processing group 中，不由 reasoning 替代。
- `reasoning_content` 是供应商返回的原始推理字段，保持原文并放入默认折叠的“原始模型推理”。前端不翻译、不重写，也不把它冒充用户可见正文。
- 没有真实 `content` 时，前端不根据工具状态合成中文过程说明。
- ToolMessage 继续按 `tool_call_id` 与调用配对；本版本不修改 checkpoint、消息协议或模型调用次数。

## 导出报告

- 当前会话和历史列表都支持 HTML、Markdown、JSON 三种格式。
- HTML 是自包含离线报告，不引用外部脚本、样式、字体或图片。工具参数与结果、命令日志、验证、clean replay 和 Session 原始响应按项折叠，并提供全部展开/折叠操作。
- HTML 中来自仓库、模型、工具和日志的动态内容统一转义；内联脚本只操作静态 `details` 元素，不能执行导出内容。
- Markdown 使用 `<details>/<summary>` 配对每个工具调用及对应 ToolMessage，并折叠命令、日志、replay 和原始 Session。纯文本阅读器仍能读取全部原文。
- JSON 保留原始 messages、todos、artifacts 和 compile sessions 对象，不替换为展示层结构。
- 三种格式继续复用 v5 的只读证据读取：日志最多返回末尾 16 KiB 并沿用既有脱敏；读取任一编译证据失败时不生成不完整报告。

## 验证与边界

- Node 纯逻辑测试固定中文 `content`、英文 reasoning、tool call/result 配对、未匹配结果、HTML 注入文本和 JSON 原样保留。
- 离线浏览器 fixture 覆盖桌面、手机和短屏实时布局，以及当前会话/历史会话的 HTML、Markdown、JSON 下载；测试不调用模型、不创建 Compile Session。
- 本版本不改变 Lead/Compiler 提示词、Compile Session、artifact、replay、provider policy 或正式实验语义。
