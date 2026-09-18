# Forge 页面模式与工具消息协议

## 页面模式

模式是应用的执行策略，不是模型等级。`supports_thinking` 只控制是否向模型启用显式思考，不控制规划或子代理权限。

| 模式     | `thinking_enabled` | `is_plan_mode` | `subagent_enabled` |
| -------- | ------------------ | -------------- | ------------------ |
| Flash    | false              | false          | false              |
| Thinking | 模型支持时为 true  | false          | false              |
| Pro      | 模型支持时为 true  | true           | false              |
| Ultra    | 模型支持时为 true  | true           | true               |

不支持 thinking 的模型仍可选择 Pro/Ultra；仅独立 Thinking 模式降级为 Flash。模型能力尚未加载或未知时不发送 thinking/reasoning 参数，但保留显式选择的 Pro/Ultra。未选择模式时沿用原默认：支持 thinking 选 Pro，否则选 Flash。

完整页面编译流程需要 **Ultra**，这样 Lead Agent 才能通过 `task` 委派 compiler 子代理。开启委派表示工具可用，不表示模型必然调用它。Pro 的规划启用 TodoMiddleware 和相应任务清单工具，用于记录计划；它不是一个自动强制推进编译步骤的调度器。系统提示词规定职责，工具执行和验证结果才是完成依据。

`reasoning_effort` 只在模型明确声明 `supports_reasoning_effort` 时发送。支持时默认 Thinking/Pro/Ultra 分别为 low/medium/high，用户设置可覆盖；不支持时同时移除历史偏好与额外上下文残留。

参数统一由 `frontend/src/core/threads/run-context.ts` 生成，输入框选择与线程提交共用模式解析；后端模型能力和工具注册规则不变。

## 防循环警告

LoopDetectionMiddleware 在 `after_model` 记录重复工具调用。默认第三次相同调用集合触发一次警告，第五次强制停止；哈希规则、滑动窗口和阈值不变。

警告先按线程暂存，在 `before_model`/`abefore_model` 核实最近一轮 assistant 的每个 `tool_call_id` 都有返回后，才追加 HumanMessage：

```text
assistant(tool_calls) -> tool(result)... -> human(loop warning) -> 下一次模型请求
```

不能把警告插在 assistant 与工具返回之间，否则 DeepSeek/OpenAI 兼容接口可能拒绝请求。待发送警告在消费、强制停止、reset 和线程 LRU 淘汰时清理；历史工具结果不能补齐当前轮返回。

## 编译终态消息

`finalize_session` 到达终态后，`CompileTerminationMiddleware` 会直接结束 Lead Agent graph，避免为了总结再次调用模型。工具返回的完整 JSON仍保留在 ToolMessage 中，供状态机、审计和实验取证使用；面向用户的最终 AIMessage 则由同一份载荷确定性生成简洁 Markdown，展示会话、提交、构建系统、候选验证、clean replay、容器清理和产物。

成功终态会在同一个状态更新中把仍为 `in_progress` 的 Todo 标记为 `completed`。失败、取消和超时不会伪装成任务完成。该收尾不调用 `write_todos`，因此不会增加模型请求或 Token，也不改变 compiler 子代理的 `submit_build_result` 机器协议。

前端消息组不依赖 ToolMessage 紧邻其 AIMessage，而是按 `tool_call_id` 关联 processing/subagent 分组。这样 LangGraph 流式状态即使暂时呈现 `AI(tool call) -> final AI -> ToolMessage`，也不会把正常的晚到工具返回误报为页面错误。没有匹配调用的 ToolMessage 不附加到其他分组，也不在 React render 路径输出错误。

## 编译过程证据与底部布局

Compiler 卡片默认展开，显示持久化会话中的执行命令、角色、容器工作目录、退出码、耗时和超时状态；命令与日志可以逐条展开。候选验证检查与每一次 clean replay 的结果、失败原因、清理状态同时保留，不以最终成功覆盖中间失败。卡片按目标 `task` 之前对应 `prepare_compile_session` 的工具返回绑定 session，而非读取线程最新的 session ID，因此历史刷新和同线程多次编译不会串记录。

Leader 的 `prepare_compile_session`、`clone_repository`、`identify_build_system` 和 `finalize_session` 提供「步骤结果」展开区，显示已有返回。Compiler 的公开最新说明可以显示，但本功能不生成不存在的模型内部思考，也不增加任何模型请求；最终确定性 Markdown 与原始工具协议不变。

Gateway 新增三个只读端点：

- `GET /api/threads/{thread_id}/compile-sessions/{session_id}`：状态、命令、verification 与 replay 白名单快照。
- `GET .../commands/{command_id}/log`：记录引用的命令日志。
- `GET .../replays/{attempt_id}/log`：记录引用的独立 replay 日志。

运行中的会话约每 2 秒读取快照，结束时刷新；日志只在展开后读取，运行时刷新展开的日志。每条仅返回最后 16 KiB，截断会明确提示，完整文件仍保留于宿主 `.compile-sessions/<thread>/<session>/`。读接口不创建目录、不保存 session、不执行 shell。路径限定于对应日志目录，拒绝跨 session、跨线程及符号链接越界；常见凭据和当前敏感环境变量值脱敏。不承诺识别任意自定义 secret，也没有新增多用户鉴权：服务仍应限制于可信 Tailscale 网络，不能作为公网安全隔离方案。

文件缺失、无权限或记录损坏会显示「证据不可用」，并不代表编译一定失败。日志以文本渲染；编译产物仍应在宿主 `artifacts/` 或通过 SCP 查看，通用文件预览 API 不会自动变为编译产物下载接口。

已开始的普通聊天与自定义 Agent 聊天页采用独立消息滚动区和正常占位的 Todo/followups/输入区，取消绝对定位、平移及固定底部空白补偿。完成 Todo 仍可展开，长清单和短屏底部区域各自有界滚动，不覆盖正文。

离线浏览器回归：启动本地生产服务后，使用已有 Playwright 环境运行 `node scripts/test-compile-trace-layout.cjs`。可设置 `FORGE_TEST_BASE_URL`（只允许 localhost）、`FORGE_PLAYWRIGHT_PATH`、`FORGE_CHROME_PATH` 和 `FORGE_TEST_OUTPUT`。测试会拦截全部业务 API，用固定多 session/双 replay/长日志和事件流 fixture 验证展示，不连接真实模型或 Docker。

## 实验与网络边界

页面模式修复不修改独立实验客户端的参数。循环检测和编译终态处理是页面与实验共享的中间件，因此重复工具调用的失败路径和最终展示会变化；后续实验应记录新代码 revision，不能覆盖旧 evidence 或将不同版本当作同一基线。编译终态修复保留原始 ToolMessage、模型调用次数和 compiler 子代理协议，但 Todo 状态与合成 AIMessage 文本属于可观察状态变化。

编译核心、镜像、挂载、预算、产物验收、clean replay、冻结 manifest 与协议哈希均未修改。历史 FMT 克隆有超时/TLS 中断，但后续宿主机与容器 GitHub 探针恢复；不能据此断言一直存在容器网络隔离，也不能把本次消息顺序修复描述为网络修复。再次失败应保留 clone 日志，分别检查宿主机与编译容器；本轮不新增 DNS、代理或重试配置。

本轮回归使用离线 fake model，不调用 provider，不产生正式科研样本。生产模型的页面编译仍需单独验证。
