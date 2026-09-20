# Compile Runtime v5 工程契约

Runtime v5 继承 `ab0b79356ea4f27780675eaee2f0f12d64a03fa5` 的 v4 实现，仅处理交互式产品导出与面向中文用户的模型表达。Runtime v2/v3/v4 的身份、历史文档与实验 evidence 均保持只读。v5 只允许交互式产品验证，不授权 provider canary 或正式实验。

## 导出范围

- 左上角导出和历史会话导出读取真实 Thread 元数据，Markdown 按消息顺序保留工具名、调用 ID、原始参数以及完整 ToolMessage 对象；JSON 保留整个消息对象，不丢弃 `additional_kwargs`、工具结果等字段。
- 对话中有效的 `prepare_compile_session` 结果对应的每个 Session，都追加只读证据 API 返回的命令、退出状态、日志、候选验证、clean replay 和完整产物路径/大小/SHA-256。
- 日志复用既有只读 API：该 API 仅返回末尾 16 KiB，并执行原有脱敏规则。导出保持响应原样，同时明确标记 `truncated`，不把日志预览伪称为全量文件。
- 读取编译证据失败时停止导出并提示错误，不产生缺失证据却声称成功的文档。无编译会话的普通聊天不发起证据请求。
- 导出保留模型返回的原文，不翻译旧消息；不能以提示词保证模型供应商的原始推理内容使用某种语言。

## 中文可见说明

Leader 和 Compiler 的提示词说明默认用户是国内高等院校学生，要求中文请求的用户可见进度说明、诊断和最终总结使用中文。Compiler 返回 JSON 的字段名保持固定，只要求 `summary` 字符串使用中文；命令、路径、日志和技术标识不翻译。

## 验证与边界

- 前端离线单元测试覆盖多 Session 提取、日志与失败读取；离线浏览器 fixture 验证 Markdown/JSON 的真实下载内容和缺证据时的错误提示。
- 后端提示词测试与身份测试固定 v4 历史字节，并校验 v5 当前组件哈希。
- 本次不运行模型调用、provider canary、Compile Session 实验或正式 evidence；服务器更新后由用户发起交互式 FMT 验收。
