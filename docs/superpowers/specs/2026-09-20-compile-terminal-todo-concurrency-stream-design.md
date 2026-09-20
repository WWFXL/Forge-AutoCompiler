# 编译终态 Todo 并发与流式负载修复设计

日期：2026-09-20。状态：**Issue #279 本地实现与验证完成，待 PR**。

## 1. 真实事故

FMT 产品运行：

```text
thread_id  = 979abf35-6cf8-4c88-bc10-cac24a7fabbe
run_id     = 01a0bede-8901-7b20-a49e-cd5162e3a174
session_id = 2cd0b8b1c797
commit     = cfb57bfa3aa90573abfc39a160bb0248e14fd64f
```

Compile Session 已进入 `completed`，候选验证与 clean replay 均通过，24 个产物已保存，compile/replay 容器均已删除。失败发生在最终 graph step：Lead Agent 同轮调用 `write_todos` 与 `finalize_session`，两个并行工具结果都写普通 `LastValue` 状态 `todos`，LangGraph 因而抛出 `INVALID_CONCURRENT_GRAPH_UPDATE`。

同次运行的首次 SSE 响应约 10.7 MB；异常结束后 resumable stream 又重新读取约 10.7 MB。普通 Forge 聊天没有消费 `onToolEnd`，但 `useThreadStream` 仍无条件注册 `onLangChainEvent`，使 SDK 把完整 `events` 加入 stream modes，放大了前端解析与渲染负担。

## 2. 目标

1. 成功 `finalize_session` 与 `write_todos` 可以出现在同一模型轮次，不产生并发状态冲突。
2. 成功终态使用并行工具合并后的最新 Todo 快照，把当前 `in_progress` 项完成后再结束 graph。
3. 失败、取消和超时终态继续保留未完成 Todo，不能伪装为成功。
4. 原始 `finalize_session` ToolMessage、确定性中文摘要和 compile terminal 跳转语义保持不变。
5. 普通 Forge 聊天不订阅未消费的 LangChain `events`；仅需要 `onToolEnd` 的 Agent 创建页面订阅。
6. 不修改 Compile Session、验证、clean replay、产物和实验协议语义。

## 3. 后端状态时序

### 3.1 单写入者原则

`todos` 是完整快照，不适合列表拼接，也不能用并发完成顺序决定覆盖优先级。本次不为其增加 reducer。

`CompileTerminationMiddleware` 分成两个步骤：

1. `wrap_tool_call` 处理 `finalize_session` 结果时只写 `messages`、`compile_terminal` 和一个成功收尾标记，不写 `todos`；
2. 并行工具节点提交后，`before_model` 从已合并 state 读取最新 `todos`，仅在成功收尾标记存在时复制并完成 `in_progress` 项，同时清除终态标记并跳转 `end`。

这样 `write_todos` 是工具步骤中唯一的 Todo 写入者，终止钩子是下一步骤中唯一的 Todo 写入者。

### 3.2 终态区分

- `finalize_session.status == completed`：设置成功收尾标记；下一步完成当前 Todo。
- `failed/cancelled/timed_out`：不设置成功收尾标记；下一步只结束 graph，保留 Todo。
- `submit_build_result.status == passed`：继续作为 compiler 子代理终态，不操作 Todo。
- 非终态或无法解析的工具返回：保持现有行为，不提前结束。

## 4. 前端流式订阅

LangGraph SDK 只有在 `onLangChainEvent` 非空时才把 `events` 加入 callback stream modes。`useThreadStream` 应根据调用者是否提供 `onToolEnd` 创建该回调：

- Forge 主聊天和自定义 Agent 聊天没有 `onToolEnd`，传 `undefined`，不订阅 `events`；
- Agent 创建页面需要监听 `setup_agent` 工具结束，继续提供回调并订阅 `events`；
- `messages-tuple`、`values`、`updates` 和 `custom` 的既有消息、Todo、标题、子任务与 retry 行为保持不变。

本次不在任意 stream error 时清除 resumable metadata，因为网络中断时仍需要恢复能力。后端终态冲突修复后，正常运行走成功清理路径；不以牺牲断线恢复来掩盖错误。

## 5. 测试策略

### 后端

- 真实 `create_agent` 模型同轮返回 `write_todos + finalize_session`，修复前稳定复现并发错误；
- 修复后断言仅一次模型调用、Session 完成、中文摘要存在、最终 Todo 全部完成；
- middleware 单元测试断言工具阶段不写 Todo，终止步骤才使用最新 state 收口；
- 失败 finalize 保留 `in_progress` Todo；
- 同步与异步 terminal 路径继续通过。

### 前端

- 纯函数断言缺少 listener 时返回 `undefined`；
- `on_tool_end` 被映射为现有 `ToolEndEvent`；
- 其他 LangChain event 被忽略；
- ESLint、TypeScript 和 production build 验证 SDK option 类型与页面集成。

## 6. 非目标与边界

- 不升级 LangGraph/LangChain SDK。
- 不给 `todos` 增加拼接、last-wins 或按文本猜测身份的 reducer。
- 不删除 resumable stream、subgraph 消息或用户可见工具过程。
- 不调用真实模型，不创建 Compile Session，不运行 provider canary 或正式实验。
- 不改写历史 evidence、Runtime identity 或 benchmark 资产。

## 7. 验收标准

- 并行 `write_todos + finalize_session` graph 正常结束且无 `InvalidUpdateError`。
- 成功 Todo 全部完成；失败终态 Todo 不被错误完成。
- 最终中文摘要进入持久化消息。
- 普通聊天的 SDK options 中 `onLangChainEvent` 为 `undefined`，Agent 创建页仍可接收工具结束事件。
- 相关定向测试、后端 lint/test、前端 lint/typecheck/build 与 `git diff --check` 通过。
