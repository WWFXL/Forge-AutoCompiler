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

## 实验与网络边界

页面模式修复不修改独立实验客户端的参数。循环检测和编译终态处理是页面与实验共享的中间件，因此重复工具调用的失败路径和最终展示会变化；后续实验应记录新代码 revision，不能覆盖旧 evidence 或将不同版本当作同一基线。编译终态修复保留原始 ToolMessage、模型调用次数和 compiler 子代理协议，但 Todo 状态与合成 AIMessage 文本属于可观察状态变化。

编译核心、镜像、挂载、预算、产物验收、clean replay、冻结 manifest 与协议哈希均未修改。历史 FMT 克隆有超时/TLS 中断，但后续宿主机与容器 GitHub 探针恢复；不能据此断言一直存在容器网络隔离，也不能把本次消息顺序修复描述为网络修复。再次失败应保留 clone 日志，分别检查宿主机与编译容器；本轮不新增 DNS、代理或重试配置。

本轮回归使用离线 fake model，不调用 provider，不产生正式科研样本。生产模型的页面编译仍需单独验证。
