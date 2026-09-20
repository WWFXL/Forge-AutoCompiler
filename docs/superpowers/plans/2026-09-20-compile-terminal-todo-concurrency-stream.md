# 编译终态 Todo 并发与流式负载实施计划

日期：2026-09-20。设计：`../specs/2026-09-20-compile-terminal-todo-concurrency-stream-design.md`。跟踪：Issue #279。

## 1. 执行顺序

- [x] 核对真实 checkpoint、Compile Session、容器清理和 Nginx 流量证据。
- [x] 创建最新 `origin/main@d5b3073d` 的独立 worktree，保留主工作树用户改动。
- [x] 创建并回读中文 Issue #279。
- [x] 完成 Spec 与本 Plan。
- [x] 先增加后端并行工具失败回归和前端事件订阅纯逻辑测试。
- [x] 实现后端终态 Todo 的跨步骤单写入者收口。
- [x] 实现前端按需 LangChain event handler。
- [x] 执行定向、相邻和完整验证。
- [x] 更新项目状态快照和相关工程文档。
- [x] 完成本地中文提交所需的最终审查与验证。
- [ ] 推送、创建并回读 PR，等待 CI。
- [ ] 经用户确认后合并，更新知识库并提供服务器部署指令。

## 2. 后端测试先行

修改 `backend/tests/test_compile_terminal_tools.py`：

1. 增加会同轮返回 `write_todos` 和 `finalize_session` 的测试模型。
2. 使用真实 `create_agent`、`TodoMiddleware` 与 `CompileTerminationMiddleware` 运行最小 graph。
3. 修复前断言可稳定触发 `INVALID_CONCURRENT_GRAPH_UPDATE`。
4. 修复后断言模型只调用一次、清理只执行一次、最终消息为中文摘要、Todos 全部完成。
5. 调整 middleware 单元测试，明确工具结果阶段只设置终态标记，`before_model` 才更新 Todo。
6. 保留失败终态和 compiler submit 的既有断言。

## 3. 后端实现

修改 `backend/packages/harness/deerflow/agents/middlewares/compile_termination_middleware.py`：

1. 增加只用于 middleware 生命周期的成功 Todo 收尾标记。
2. `_terminal_result()` 不再直接返回 `todos`。
3. 成功 finalize 设置收尾标记；失败/取消/超时不设置。
4. `before_model()` 在处理 `compile_terminal` 时读取最新 state，完成 `in_progress` Todo，清除标记并跳转 `end`。
5. 同步和异步 hook 复用同一逻辑。

## 4. 前端测试与实现

新增纯逻辑模块和测试：

- `frontend/src/core/threads/stream-events.ts`
- `frontend/src/core/threads/stream-events.test.ts`

修改 `frontend/src/core/threads/hooks.ts`：

1. 纯函数仅在存在 `onToolEnd` listener 时返回 LangChain event handler。
2. handler 只转发 `on_tool_end`。
3. `useThreadStream` 把可选 handler 传给 SDK；普通聊天得到 `undefined`。
4. 保留 listener ref，避免异步事件使用陈旧闭包。

## 5. 验证矩阵

按顺序执行：

1. 后端目标 pytest，确认失败测试先红后绿。
2. 前端 Node 原生纯逻辑测试。
3. 后端 terminal/todo/error middleware 相邻测试。
4. 后端 `make lint` 与 `make test`。
5. 前端 `pnpm lint`、`pnpm typecheck`、`pnpm format`。
6. 设置测试用 `BETTER_AUTH_SECRET` 后运行 production build。
7. `git diff --check`、状态与敏感信息检查。

所有验证使用 mock/fake session，不调用 provider、Docker 或正式实验。

最终结果：后端正式产品测试 `1610 passed, 30 skipped`；定向 terminal 测试 `18 passed`；相邻 middleware 测试 `71 passed`；前端纯逻辑测试 `31 passed`；Ruff、ESLint、TypeScript、Prettier 和 44 页 production build 均通过。

## 6. 交付

1. 更新 `.claude/memory/project.md`，记录 Issue、根因、实现、验证与实验边界。
2. 使用中文提交信息。
3. 按仓库规定通过 `scripts/push-via-wsl.ps1` 推送。
4. 创建中文 PR，正文包含 `Closes #279`、真实事故证据、修复时序和测试结果。
5. 回读 PR 并检查 CI；未经用户确认不合并。
6. 合并后维护知识库并给出服务器 fast-forward、重建和健康检查指令。
