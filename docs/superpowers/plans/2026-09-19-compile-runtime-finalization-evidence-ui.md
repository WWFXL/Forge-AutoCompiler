# 编译终态、资源、重放证据与子任务布局实施计划

日期：2026-09-19。设计：`../specs/2026-09-19-compile-runtime-finalization-evidence-ui-design.md`。状态：**Issue #271 已创建，实现与本地验证完成，待 PR/CI**。

## 1. 交付范围

本计划用一个追踪 Issue 和一个小而完整的 PR 交付：

- P0：修复真实 LangGraph Runtime identity 读取和成功 run 终态；
- P1：为 compile/replay 冻结并执行共享服务器并行策略；
- P2：完整 artifact manifest、独立 replay verification recipe、Docker stop grace 和产品 executed build system；
- 前端：消除空 reasoning 产生的横线与子任务标题重叠；
- 新 Runtime v3 工程身份、文档、项目快照和知识库记录。

不调用 provider，不运行正式实验，不清理旧 gRPC 容器。

## 2. 强制顺序

- [x] 回读真实 FMT checkpoint、session 和页面 DOM 证据。
- [x] 完成最新版 Spec。
- [x] 完成最新版 Plan。
- [x] 创建并回读中文 GitHub Issue，确认正文没有字面 `\n`。
- [x] Issue 创建成功后先写失败测试。
- [x] 分阶段修改业务代码，每阶段运行定向测试。
- [x] 更新 Runtime v3 身份、开发文档和项目状态快照。
- [x] 跑后端产品测试、Runtime identity、前端逻辑/构建/浏览器及改动文件门禁；冻结历史协议继续由其 predecessor revision 和 CI 独立验证。
- [ ] 中文提交并按仓库网络约定推送。
- [ ] 创建并回读中文 PR，等待 CI 全绿后合并。
- [ ] 回读合并提交和 Issue 终态，更新 Forge 知识库笔记。

## 3. Phase A：Issue 与基线

1. 对 Spec/Plan 运行 `git diff --check`，核对非目标和实验边界。
2. 创建中文 Issue，正文包含 FMT 身份、六个后端缺口、前端 DOM 根因、设计和验收矩阵。
3. 用 `gh issue view` 回读标题、正文和 URL。
4. 确认实现工作树基于 `origin/main@9ddf428e`，主工作树用户改动未被带入。
5. Issue 创建后才允许修改 `backend/`、`frontend/`、配置模板和 Runtime identity。

## 4. Phase B：失败测试先行

### 4.1 P0 Runtime lifecycle

- 用真实 `langgraph.runtime.Runtime(context=...)` 代替带伪造 `.config` 的 `SimpleNamespace`。
- 在 `RunnableLambda`/等价 runnable context 中验证 `get_config()` 的顶层和 configurable run ID 回退。
- 覆盖 async after-agent：身份缺失 no-op、unfinished cleanup、cleanup failure propagation、completed session 不被错误覆盖。
- 至少一个最小 graph/middleware 生命周期回归证明最终 run 不抛 `AttributeError`。

### 4.2 P1 资源策略

- RuntimeConfig 默认、合法环境覆盖和非法值回退。
- session 创建和 JSON round-trip 保存 frozen `parallel_jobs`。
- compile/replay `docker run` 同时包含 `--cpus`、CMake/CTest/Make 并行环境。
- 修改进程环境后 replay 仍使用 session 值。

### 4.3 P2 artifacts/replay/cleanup/build system

- support header 被记录，空 support file 也能通过 manifest，但只有 support files 的提交失败。
- replay 对 support file 的路径、size 和 SHA 做严格比较；缺失、额外或内容变化均失败。
- finalize 再次检查完整 manifest。
- verification IDs 的成功、空列表、非法角色、失败命令、乱序、build 前命令和不可移植路径。
- 分离 `build.sh` / `verify.sh`，验证脚本失败产生稳定 classification 和独立日志。
- fingerprint 覆盖 verification steps 与 parallel policy。
- `docker stop --time` grace 小于 subprocess timeout，并在 stop timeout 后执行 bounded `rm -f`。
- 非实验产品 submit 也持久化 `executed_build_system`。

### 4.4 前端

- `hasReasoning` 对 `""`、纯空白、非空文本和 inline reasoning 的单测。
- 离线 Playwright fixture 为 task AI message 注入空 `reasoning_content`。
- 增加稳定 test id 和 bounding-box 断言：标题前无空 MessageGroup，标题 bottom 小于卡片 top，前后区块不重叠。

## 5. Phase C：P0 实现

候选文件：

- `backend/packages/harness/deerflow/agents/middlewares/compile_termination_middleware.py`
- `backend/tests/test_compile_runtime_reliability.py`
- 必要的 agent lifecycle 相邻测试

任务：

1. 引入 `langgraph.config.get_config()`，context 优先、RunnableConfig 回退。
2. 删除对 `runtime.config` 的访问。
3. 保持身份缺失 no-op、真实 cleanup 异常上抛。
4. 删除或改写伪造 Runtime 的测试，确保未来框架接口漂移会失败。

完成门：定向 middleware/reliability 测试通过，真实 Runtime 无 `AttributeError`。

## 6. Phase D：P1 实现

候选文件：

- `backend/packages/harness/deerflow/compile/schemas.py`
- `backend/packages/harness/deerflow/compile/manager.py`
- `backend/packages/harness/deerflow/compile/operations.py`
- `backend/packages/harness/deerflow/compile/docker_runtime.py`
- `backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py`
- `.env.example`、README/CLAUDE 相关段落

任务：

1. RuntimeConfig 增加 `parallel_jobs`，默认 `COMPILE_MAX_PARALLEL_JOBS=4`。
2. prepare 将策略写入 CompileSession；旧 session 读取默认值只用于历史展示。
3. compile/replay 容器加入相同 Docker quota 和构建工具环境。
4. lifecycle 事件记录冻结值；replay fingerprint 包含该值。
5. Compiler 提示词删除无界 `-j` 建议，要求让 runtime policy 控制并行度。

完成门：schema/manager/Docker 命令测试通过，compile/replay 策略一致。

## 7. Phase E：P2 artifact manifest

候选文件：

- `backend/packages/harness/deerflow/compile/schemas.py`
- `backend/packages/harness/deerflow/compile/operations.py`
- Gateway snapshot/前端类型（若需展示新字段）
- `backend/tests/test_compile_runtime.py`

任务：

1. 抽出统一 artifact 分类：compiled 类型或 `support_file`。
2. 候选提交记录所有安全普通文件，但要求至少一个 compiled artifact。
3. replay 对完整相对路径集合、type、size、SHA 比较；support file 不执行 smoke。
4. finalize 复用相同 manifest 语义，拒绝 support file 的增删改。
5. Compiler 提示词允许显式暂存公共 include/package metadata，继续禁止倾倒任意 build tree。

完成门：FMT 风格 `lib/*.a + include/**/*.h` fixture 在候选、replay、finalize 三段一致。

## 8. Phase F：P2 verification recipe 与 build identity

候选文件：

- `backend/packages/harness/deerflow/compile/schemas.py`
- `backend/packages/harness/deerflow/compile/operations.py`
- `backend/packages/harness/deerflow/tools/bound_compile_tools.py`
- `backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py`
- 对应 tool/replay tests

任务：

1. `ReplayRecipe` 增加 `verification_steps`；tool 增加必填 `verification_command_ids` 列表。
2. 分别校验 build recipe 和 verification recipe，并保持各自稳定 classification。
3. 渲染 `build.sh` 和可选 `verify.sh`；replay 在同一容器内顺序执行并写独立日志/check。
4. fingerprint 覆盖两类步骤、资源策略和完整 manifest。
5. 每次 submit 都推导并持久化 `executed_build_system`；experiment constraint 复用结果。
6. 更新返回 payload、workflow events、只读 snapshot 中必要字段。

完成门：带 CTest 的 replay 确实执行 verify script；测试失败不被 artifact match 掩盖。

## 9. Phase G：P2 Docker cleanup

候选文件：

- `backend/packages/harness/deerflow/compile/docker_runtime.py`
- `.env.example` 和运行文档
- Docker runtime tests

任务：

1. 增加 `COMPILE_DOCKER_STOP_GRACE_SECONDS=3`。
2. 使用 `docker stop --time <grace>`，外层 subprocess timeout 为 grace 加缓冲。
3. 无论 stop 成功、失败或 timeout，都按现有总 deadline 决定是否执行 `rm -f`。
4. 日志区分 grace、CLI timeout、stop/removed 事实。

完成门：正常 cleanup 不再稳定等待 10 秒；异常容器仍有界强删。

## 10. Phase H：前端修复

候选文件：

- `frontend/src/core/messages/utils.ts`
- `frontend/src/core/messages/utils.test.ts`
- `frontend/src/components/workspace/messages/message-list.tsx`
- `frontend/scripts/test-compile-trace-layout.cjs`

任务：

1. `hasReasoning` 以实际非空文本为准。
2. 给 subtask group/count 增加测试定位属性，不引入可见说明文字。
3. fixture 复现 DeepSeek 空 reasoning，并断言无空卡、无重叠。
4. 保留真实 reasoning、Compiler trace、Todos 和最终 Markdown 的现有行为。

完成门：三个 viewport Playwright、console、overflow 和截图检查全部通过。

## 11. Phase I：Runtime v3 与文档

1. 保留 `compile-runtime-v2.json` 和 `docs/compile_runtime_v2.md` 不变。
2. 新增 Runtime v3 文档与 identity manifest，predecessor 固定 `9ddf428e`，Issue URL 使用本轮实际编号。
3. 更新 identity 测试指向 v3，并计算最终核心组件 SHA-256。
4. 明确授权仍为 engineering validation，provider/formal 均为 false。
5. 更新根/后端 CLAUDE、README、`.env.example` 和 `.claude/memory/project.md`。

## 12. Phase J：验证矩阵

按风险从小到大执行：

1. `frontend` 消息工具 Node 单测。
2. backend middleware/reliability 定向 pytest。
3. backend compile runtime、Gateway snapshot 和 identity 相邻测试。
4. 改动 Python 文件 Ruff check/format check。
5. backend 当前产品全量 lint/test。
6. frontend lint、typecheck、format、production build。
7. 启动本地 production server，运行三个 viewport 的离线 Playwright；检查截图和像素非空。
8. frozen predecessor tests，确认历史 v2/benchmark 无改写。
9. `git diff --check`、敏感信息扫描、历史 manifest/evidence diff 检查。

所有测试均不调用模型 provider，不创建 Compile Session，不写正式 evidence。

## 13. Phase K：提交、PR 与合并

1. 按项目风格写中文提交，保持 PR 小而完整。
2. 使用 `scripts/push-via-wsl.ps1` 推送，避免 Windows Git 已知网络路径问题。
3. 创建中文 PR，正文包含 `Closes #<issue>`、真实根因、行为变化、测试证据、Runtime 身份和非目标。
4. `gh pr view` 回读，确认没有字面 `\n` 或字段漂移。
5. 等待 backend、frontend、frozen benchmark CI 全绿；失败则定位并追加修复。
6. 合并后回读 PR、Issue 和 `main` SHA。
7. 只更新知识库中的 Forge 项目卡片、Linux 分工/结果查看和开发记录相关段落。

## 14. 停止条件

遇到以下情况必须停止扩大实现并请求用户决策：

- 必须改写历史 Runtime v2 identity、benchmark manifest 或 evidence；
- 需要调用真实 provider 才能建立回归；
- CPU quota 在目标 Docker 版本不可用，必须改用 daemon 级全局策略；
- verification recipe 需要允许 diagnostic 或宿主/session 路径才能工作；
- 完整 artifact manifest 会把不受信任设备文件、FIFO 或符号链接纳入交付；
- 实现需要升级 LangGraph、Next.js 或引入新的运行时依赖；
- 最新主干与本设计的外部行为发生实质冲突。
