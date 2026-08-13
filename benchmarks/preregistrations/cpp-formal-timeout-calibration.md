# C/C++ formal 模型请求 300 秒超时校准预注册

## 研究问题

formal v4 的 63 次模型请求中有 8 次在 120.01–120.85 秒被客户端截止点终止。本校准检验：在模型、endpoint、编译任务、调用预算和重试策略不变时，将客户端请求超时延长到 300 秒后，请求能否形成完整闭合证据。

## 冻结设计

- 项目固定为 `cppitertools@531b3d753d2bbfe3b0ababe61c2e95e965c54a66`。
- 只执行原 schedule order `1` 和 `2`：RichLab `gpt-5.5` 与 DeepSeek `deepseek-v4-flash` 各一次。
- Lead 与 Compiler 的请求超时统一为 300 秒，`max_retries=0`。
- Memory、Skill、fallback、replacement 和 backfill 保持关闭。
- 使用 WSL2 `Ubuntu` 原生 Docker Engine、Compose/DooD、Compile Session 与 clean replay。
- evidence 使用独立 append-only 目录，maximum recorded tokens 为 500,000。

## 判定

- 报告每次请求的角色、终态、延迟和安全错误分类，不保存响应正文、请求头或凭据。
- 超过 120 秒后成功闭合的请求构成“延长截止点可挽救慢请求”的直接证据。
- 若所有请求均在 120 秒内完成，只能证明 300 秒配置路径可运行，不能证明历史 8 次超时可被挽救。
- 300 秒仍超时说明客户端等待更久仍未获得响应，但不能单独定位上游服务、跨境链路或本机接入的具体责任层。

## 边界

本校准不进入 formal 模型能力主比较，不修复 Oracle/端到端预算语义，不开展 verifier-driven repair treatment，也不授权其他项目或 slot。
