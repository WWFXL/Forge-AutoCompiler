# 编译过程展示与底部布局实施计划

日期：2026-09-18。设计：`../specs/2026-09-18-compile-trace-layout-design.md`。

## 任务顺序与状态

- [x] 核对真实会话、当前源码和权限，保留用户脏工作区，建立最新 main 独立 worktree。
- [x] 按 knowledge-base 流程检索/读取原笔记，新增详细 Linux 分工、流程、挂载与结果查看笔记并挂入研究索引。
- [x] 先写 Spec。
- [x] 再写本 Plan。
- [x] 用中文创建并回读 Issue #265，关联设计/计划；创建 Issue 前未改业务代码。
- [x] 增加只读 Gateway 会话/命令日志/replay 日志路由与安全回归。
- [x] 增加前端 session 关联、只读查询和 Compiler 命令/replay 证据区。
- [x] 为 Leader 编译工具增加可展开的已有返回结果，保留机器协议。
- [x] 改为消息滚动区与底部 composer 的正常 flex 占位布局，同步共享组件的自定义 Agent 调用页。
- [x] 执行目标与后端全量测试、前端 Node 测试/lint/typecheck/format/build、Playwright 桌面/手机/短屏验收；全程使用离线 fixture。
- [ ] 更新项目说明与快照，提交、推送、创建中文 PR，检查 CI 后合并。
- [ ] 更新知识库的交付状态、链接与验证证据；不代替用户启动真实模型实验。

## 1. Issue

通过已认证 Windows `gh` 创建并回读中文 Issue。记录真实 FMT 两次 replay 与 Todo overlay 的证据，限定反馈 1、3。用户本轮已授权修复、测试与合并，不扩大到产物下载/代理配置。

## 2. 后端只读 API

在 `app/gateway/routers/compile_sessions.py` 实现三个 GET 路由，注册到 app/router 导出。仅通过 Paths 的会话根读取已有 JSON，不使用会创建/保存数据的 manager 操作。白名单裁剪 verification/replay/command 字段；记录 ID 控制日志查找，bounded tail 和明确 truncation。

新 pytest 固定临时会话目录和 FastAPI TestClient，不依赖 Docker/provider。覆盖多个 replay、常见 token 脱敏、日志大小/不存在、ID/身份错误、JSON 损坏、越界路径和符号链接、完整源文件集合哈希前后不变。

## 3. 前端证据区

新增 `core/compile` 类型、fetch/query hook 和消息关联纯函数；复用 `getBackendBaseURL()` 与 TanStack Query。Compiler 卡片从 prepare 工具返回绑定 session；活动阶段有界轮询，结束时刷新，历史回放也可读取。日志只在对应 details 展开后请求。

会话状态、command 清单和 replay 检查只取证据，不让用户从页面执行命令。以 pre/code/text 渲染输出防止日志 HTML 注入；长路径、命令和输出在自身容器内换行或滚动。中间失败与最终成功都可查看。

Leader 工具结果使用可展开结果组件，不动 LangGraph messages、不改 backend tool schema。i18n 英/中文同步。

## 4. 底部布局

调整聊天页、TodoList 与 MessageList 的 ownership：消息区域 grow/min-h-0；底部正常 flex 收缩，Todo 和 InputBox 取消互相补偿的 translate/absolute。输入组件中的 followups 若仍是 overlay，改为内部正常占位。未开始会话保留 Welcome 行为。已完成 Todo 仍可查看。

Playwright 使用固定 HTTP/LangGraph fixtures 验证两次 replay和完整命令证据，不调用模型。测桌面/手机/短屏边界、滚动、Todos 开合、followups 和宽文本。截图保存在临时测试输出，不把业务凭据/真实原始日志提交。

## 5. 验证与交付

先跑目标 pytest/前端 Node 测试，再全量 lint/typecheck/format/build；后端完整集合视现有依赖准备运行，CI 必须通过。沿既定 WSL helper 推送，中文 PR 含 closing keyword、影响边界、实际测试结果和未运行事项。

合并前核对 diff 只有任务文件，代码没有改 frozen harness 组件。服务器部署不视作本轮自动授权：本轮目标是测试并合并，交付最新 main SHA 和更新命令；若用户另行要求部署再确认忙碌任务后进行。
