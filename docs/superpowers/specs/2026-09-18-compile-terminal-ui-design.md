# Forge 编译终态展示与消息分组修复设计

**日期：** 2026-09-18

**状态：** 已由 Issue #263 确认

## 背景

Forge 已能完成真实 C/C++ 项目的克隆、构建、候选校验和干净重放，但编译成功后的用户界面仍有四个相互关联的问题：

1. 最终助手消息直接显示 `finalize_session` 的结构化 JSON；
2. 流式页面出现 `Unexpected tool message outside a processing group`；
3. 编译已经结束，但 Todo 最后一项仍停留在 `in_progress`；
4. clarification 等独立 Markdown 消息在暗色主题中对比度不足。

已核查的实例 `7596ff2f-ee5a-43e7-90e9-3ccb5c5fda22` 中，Compile Session `9701a21ce329` 的构建、候选校验和 clean replay 均成功，产物 `libfmt.a` 已生成且编译容器已清理。这些现象属于终态适配和流式渲染问题，不是编译失败。

## 目标

- 最终助手消息显示确定性、可读的 Markdown 摘要。
- ToolMessage 保留完整结构化结果，继续作为状态机和实验取证依据。
- 不增加模型调用，并在成功终结时同步完成仍处于 `in_progress` 的 Todo。
- ToolMessage 即使晚于最终 AIMessage 到达，也能按 `tool_call_id` 回填到正确分组。
- clarification 在亮色和暗色主题中都使用标准前景色。
- compiler subagent 的机器终态协议、调用次数、Token 计量和 benchmark 语义保持不变。

## 非目标

- 不改变编译、验证、clean replay、产物保存或容器清理逻辑。
- 不增加终态后的模型总结调用。
- 不修改自动生成的 `frontend/src/components/ai-elements/`。
- 不重新设计整个消息时间线或 Todo 系统。

## 根因

### 后端终态

`CompileTerminationMiddleware` 在 `finalize_session` 返回终态后，把 ToolMessage 的完整 JSON复制成 AIMessage 并设置 `compile_terminal=True`。下一次进入模型前，中间件直接跳转到 graph `end`。该机制避免了额外模型调用，却也让 JSON面向用户显示，并跳过了后续 `write_todos`。

### 前端流式分组

`groupMessages()` 只把 ToolMessage 追加到最后一个开放分组。流式过程中最终 AIMessage 可能先于对应 ToolMessage 出现；最后一个分组此时已经是终态 assistant，于是正常中间态被 `console.error()` 误报。最终持久化顺序可以完全正确。

### 文字颜色

clarification 分支直接渲染裸 `MarkdownContent`，没有明确使用标准 assistant 前景色。

## 设计

### 1. 保留机器证据，独立生成人类摘要

`finalize_session` 的 ToolMessage 保持原始 JSON不变。中间件根据已解析载荷生成确定性 Markdown，内容覆盖状态、仓库/提交、构建系统、验证、clean replay、产物和错误等实际存在的字段。摘要不推测、不调用模型。

该行为只适用于 Lead Agent 的 `finalize_session`。`run_container_bash` 与 `submit_build_result` 的 compiler subagent 结构化终态保持不变。

### 2. 原子收尾 Todo

成功 `finalize_session` 时，中间件复制 state 中的 `todos`，将 `in_progress` 项改为 `completed`，并与 ToolMessage、AIMessage 和 `compile_terminal=True` 一并写入同一个 `Command.update`。失败、取消和超时不完成 Todo。

### 3. 按 `tool_call_id` 配对

`groupMessages()` 在创建 processing、subagent 等工具调用分组时登记 tool call ID。普通 ToolMessage 优先精确查找目标分组；仅在缺少 ID 时使用当前开放分组。暂时无法匹配的消息不会在 React render 路径调用 `console.error()`，也不会污染其他分组。

clarification 保留独立突出展示，同时维持工具调用关联。

### 4. 统一 clarification 样式

clarification 使用明确的 `text-foreground` 语义容器，不硬编码黑色或白色。

## 数据流

```text
finalize_session
  -> ToolMessage（完整 JSON）
  -> CompileTerminationMiddleware
       -> 确定性 Markdown AIMessage
       -> 成功时完成 in_progress Todo
       -> compile_terminal=True
  -> before_model 跳转 end（不新增模型调用）
  -> 前端按 tool_call_id 配对
```

## 验收

- 后端仍只调用模型一次，保留原始工具 JSON，并正确生成 Markdown 和收尾 Todo。
- 正常与乱序 ToolMessage 都能正确分组，未知消息不导致渲染异常。
- clarification 使用稳定前景色。
- 后端 pytest/ruff、前端测试/check/build 全部通过。
- Docker 真实编译的摘要、Todo、产物、replay 和容器清理无回归。
- benchmark/canary 调用次数和证据字段无非预期变化。

## 风险控制

- 摘要只读取工具已返回的白名单字段并容忍字段缺失。
- Todo 只在 `finalize_session` 成功终态更新。
- ToolMessage 只按全局唯一 `tool_call_id` 精确匹配。
- 不新增模型调用、不改原始 ToolMessage、不改 compiler subagent 协议。
