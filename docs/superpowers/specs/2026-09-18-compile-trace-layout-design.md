# 编译过程证据展示与底部布局设计

日期：2026-09-18。基线：`main@1c6d54af`。跟踪：[Issue #265](https://github.com/WWFXL/Forge-AutoCompiler/issues/265)。状态：实现与离线回归完成，待 PR 交付。

## 问题和目标

用户的真实 FMT 会话 `c21519708f79` 完成构建、22 项 CTest、两次 submit/replay 后最终成功。但页面只列 Leader 工具名，Compiler 卡片只显示最终 JSON，无法看到命令、输出和中间修复。全部 Todo 完成后，绝对定位的 Todo/输入区仍遮挡滚动正文。

本次修复用户反馈 1、3，并沉淀一篇详细 Linux 编译分工知识库笔记。产物下载入口、模型自由总结、网络代理、编译核心改造不在范围。

## 不变量

- 不修改 Harness 提示词、工具 schema/返回、调用次数、预算、编译/验收/replay/finalize 语义。
- 不增加模型请求，不伪造模型思考。最终确定性摘要和 compiler JSON 机器协议保留。
- 不改 frozen manifest、组件摘要、历史 evidence 或现有用户未提交改动。
- 展示 API 仅放在 `backend/app/gateway`，依赖方向保持 `app -> deerflow`。
- 不开放任意文件路径、容器 shell 或宿主文件浏览接口；不新增产物下载 API。

## 成熟模式与依赖评估

复用项目已有 TanStack Query 做只读快照/按需日志读取，复用 LangGraph SDK 的 Leader messages/tool_call_id 关联；使用浏览器原生 details 展开证据。Compiler 在独立 executor 图中运行，当前 custom event 只向前端保存 latestMessage，不是完整持久化工具返回历史。只累积事件无法保证页面刷新后的恢复，因此持久化 `session.json` 是命令/replay 历史的权威来源。

底部布局采用常见聊天工作台的 flex 分区：可滚动消息区与正常占位的 composer 区分离，不继续用固定 160/240px 底部空白抵消可变高度 overlay。保留未开始会话的 Welcome 和现有 followup 交互。

## 展示设计

1. 编译基础设施工具的现有返回可展开查看；有 command 参数时显示命令，有错误时保留真实错误。已有公开 reasoning 展示不删除，但不生成缺失 reasoning。
2. Compiler 卡片增加会话证据区：按记录顺序显示命令、角色、容器 workdir、退出码、耗时、超时状态；输出按需展开。显示候选验证检查、每次 replay 的结果、失败原因与清理状态。
3. 失败记录不会被最终成功覆盖；从历史 messages 恢复卡片时也读取持久化会话，而非只依赖实时 custom event。
4. 任务卡片绑定它之前最近一次成功 `prepare_compile_session` 返回中的 session ID，按 tool_call_id 识别工具名；不能用线程最新 session ID 把旧任务关联到新会话。
5. 数据缺失/不完整/读取失败显示可辨认状态，不宣告构建失败，不用空数组假装无历史。日志有截断时明确标识。
6. JSON 机器返回可作为证据保留，但不需要为了 UI 改写机器协议。

## Gateway 只读接口

- `GET /api/threads/{thread_id}/compile-sessions/{session_id}`：返回白名单字段的状态、命令记录、验证摘要和 replay 摘要。
- `GET .../commands/{command_id}/log`：仅读取该会话中该命令记录引用的日志，返回末尾最多 16 KiB 与截断标志。
- `GET .../replays/{attempt_id}/log`：仅读取该会话中该 replay 引用的日志，同样有界。
- 线程/会话/记录 ID 为安全路径组件；目录和文件 resolve 后必须留在会话内。JSON 内的 thread/session 身份必须与 URL 匹配。拒绝外部绝对路径、符号链接逃逸、跨线程引用，不回传服务端异常路径。
- 限制 metadata 文件读取大小；损坏快照返回暂不可用，404 与权限错误明确区分。记录只读，不调用 manager 保存或创建目录。
- 不回传完整 metadata、环境变量、容器凭据。可见命令与输出做常见凭据/当前 API key 值脱敏；不承诺能识别任意自定义 secret，日志仍受当前应用同等访问边界约束。
- 保持现有 API 的访问控制约定，不把本功能说成新增多租户身份隔离。

## Todo 与 composer 布局

- 已开始会话底部 Todo、followups 和输入框均正常占位；消息区 `min-h-0` 独立滚动。
- Todo 折叠/展开和长输入改变底部高度时，消息区自动缩小，不遮挡正文。
- 完成状态仍可展开检查，不因为“全部完成”丢弃清单。折叠为紧凑状态，背景不透出正文。
- 窄屏/短屏底部面板限制高度并可滚动，不能将消息区完全挤出。清理旧的平移/绝对定位和仅服务于 overlay 的 padding 补偿。

## 验收

- 离线固定 FMT 证据包含第一次 smoke_mismatch 和第二次 passed，两次均可见；命令可展开，输出可读；刷新仍可见。
- 多 session 线程的旧 Compiler 卡片不误绑定最新 session。
- 后端覆盖身份/路径/符号链接/缺失/权限/损坏/截断/脱敏和只读源哈希不变；前端覆盖 session 关联与数据展示。
- Playwright 桌面 1280px、手机 390px 和短屏，展开/折叠 Todos、显示 followups、滚动到尾部；正文与底部面板边界不相交，无横向溢出和新增 Console Error。
- 前端 Node 测试、lint/typecheck/format/production build，后端目标测试及完整 CI 通过后合并。
- 不执行真实 provider canary 或新的科研采集；真实模型页面编译留给用户独立验收。
