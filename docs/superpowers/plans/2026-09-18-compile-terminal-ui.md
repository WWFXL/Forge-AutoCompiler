# Forge 编译终态展示与消息分组修复实施计划

> 本计划以 `2026-09-18-compile-terminal-ui-design.md` 为设计依据，跟踪 Issue 为 #263。

**目标：** 修复结构化 JSON直出、流式 ToolMessage 分组报错、Todo 未完成和暗色文字不可读，同时保持实验语义不变。

## Task 1：建立文档与测试基线

- [x] 从最新 `origin/main` 建立 `fix/issue-263-compile-terminal-ui` 独立 worktree。
- [x] 将 Spec 与 Plan 纳入项目。
- [x] 运行修改前的后端终态测试和前端纯逻辑测试并记录基线。

## Task 2：后端测试先行

**修改：** `backend/tests/test_compile_terminal_tools.py`

- [x] ToolMessage 原始 JSON保持不变。
- [x] 合成 AIMessage 是包含状态、验证、replay 和产物的 Markdown。
- [x] 成功终态只把 `in_progress` Todo 变为 `completed`。
- [x] 失败终态不会错误完成 Todo。
- [x] 保留“一次模型调用即结束”的断言，并先确认新增测试失败。

## Task 3：后端最小实现

**修改：** `backend/packages/harness/deerflow/agents/middlewares/compile_termination_middleware.py`

- [x] 用纯函数格式化 `finalize_session` 摘要。
- [x] 让终态转换读取当前 state，并原子更新 Todo。
- [x] 保持 `run_container_bash` / `submit_build_result` 机器终态不变。
- [x] 运行目标 pytest（16 项通过）。

## Task 4：前端测试先行

**新增：** `frontend/src/core/messages/utils.test.ts`

- [x] 覆盖普通顺序、ToolMessage 晚到、subagent 配对和未知 ID。
- [x] 使用项目现有 Node 纯逻辑测试方式执行，并确认乱序用例在实现前失败。

## Task 5：前端最小实现

**修改：**

- `frontend/src/core/messages/utils.ts`
- `frontend/src/components/workspace/messages/message-list.tsx`

- [x] 建立 `tool_call_id -> MessageGroup` 映射并精确回填。
- [x] 无 ID 才回退到开放分组；无法匹配时不在 render 路径报错。
- [x] 保留 clarification 的独立展示和工具关联。
- [x] clarification 添加标准 `text-foreground` 容器。

## Task 6：分层回归

- [x] 后端：目标 pytest、相关 replay/error middleware 测试、完整测试集与 ruff。
- [x] 前端：Node 消息测试、全量 ESLint、TypeScript 与 production build。
- [x] 仓库：`git diff --check`，确认文件范围。

## Task 7：项目状态、PR 与合并

**修改：** `.claude/memory/project.md`

- [ ] 记录 Issue、根因、实验不变量、测试和部署步骤。
- [ ] 中文提交，通过 `scripts/push-via-wsl.ps1` 推送。
- [ ] 创建中文 PR，正文包含 `Closes #263` 和测试证据。
- [ ] 读回 PR，检查 diff/CI 后合并。

## Task 8：服务器验收

- [ ] 服务器拉取合并后的 `main` 并重新构建 Forge 服务。
- [ ] 检查 runtime gate、服务状态和关键日志。
- [ ] 真实编译确认摘要、Todo、样式、验证、replay、产物和清理均正确。

## Task 9：知识库维护

- [ ] 搜索并读取 Forge 相关笔记。
- [ ] 记录根因、`tool_call_id` 配对、原子 Todo 收尾、实验约束和最终发布信息。
- [ ] 保留现有 Obsidian wikilink并读回校验。

## 完成标准

四项用户可见问题均有代码修复和自动化测试；PR 已合并并完成服务器真实验收；项目状态与个人知识库均已更新。
