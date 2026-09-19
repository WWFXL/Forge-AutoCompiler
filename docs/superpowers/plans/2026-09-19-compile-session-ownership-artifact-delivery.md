# 编译会话宿主权限、产物交付与终态展示实施计划

日期：2026-09-19。设计：`../specs/2026-09-19-compile-session-ownership-artifact-delivery-design.md`。Issue：[#273](https://github.com/WWFXL/Forge-AutoCompiler/issues/273)。状态：**本地实现与验证完成，待 PR/CI**。

## 1. 交付范围

本计划用一个追踪 Issue 和一个小而完整的 PR 交付：

- P0：Session 宿主 UID/GID 规范化与路径安全；
- P1：CMake install 优先、单次稳健诊断与 submit 边界；
- P2：终态产物汇总、结构化完整 manifest 和策略拒绝展示；
- P3：Docker `stop --timeout`；
- Runtime v4 工程身份、文档、项目快照和知识库记录。

## 2. 强制顺序

- [x] 回读 FMT Session、workflow、replay、权限和页面证据。
- [x] 完成最新版 Spec。
- [x] 完成最新版 Plan。
- [x] 对 Spec/Plan 运行格式和 diff 检查。
- [x] 创建并回读中文 GitHub Issue（#273）。
- [x] Issue 创建后先写失败测试。
- [x] 分阶段修改业务代码并运行定向测试。
- [x] 更新 Runtime v4 身份、产品文档和项目状态快照。
- [x] 跑后端、前端、构建、浏览器和 Runtime identity 门禁；本机 production build 完成页面编译后停在主干已有的主题类型错误，交由干净 Linux CI 最终判定。
- [ ] 中文提交并按仓库网络约定推送。
- [ ] 创建并回读中文 PR，等待 CI 全绿后合并。
- [ ] 回读合并提交和 Issue 终态，更新知识库。

## 3. Phase A：Issue 与基线

1. 确认实现 worktree 基于 `origin/main@fc50a3c7`，主工作区用户修改未被带入。
2. 创建中文 Issue，正文链接 Spec/Plan 并列出 P0-P3、实验边界和验收矩阵。
3. 用 `gh issue view` 回读标题、正文和 URL，确认无字面 `\n` 或字段漂移。
4. Issue 创建成功后才允许修改 `backend/`、`frontend/`、Compose、配置模板和 Runtime identity。

## 4. Phase B：失败测试先行

### 4.1 宿主权限

- 新增 UID/GID 配置解析测试：缺失 no-op、合法 pair、非法值、只配置一项。
- metadata 原子写、workflow append 和终态全树规范化测试。
- symlink 不跟随、跨 root 拒绝、session root 结构约束测试。
- executable bit 保留、other bits 清除、owner/group 设置测试。
- finalize 成功/失败/取消和规范化错误传播测试。
- Docker wrapper/Compose contract 测试确认 UID/GID 被注入且冻结脚本未修改。

### 4.2 Compiler 流程

- Prompt contract 测试固定 `cmake --install ... --prefix /artifacts` 优先路径。
- 固定无 install 规则时单次 `find` 后备和禁止 glob `ls`。
- 固定 staging 后直接 submit、候选测试与 replay 测试双阶段语义。

### 4.3 终态与 API/UI

- 终态 formatter fixture：2 个 static libraries、16 个 headers、1 个 LICENSE。
- 断言短路径、compiled 逐项、support 汇总、无 thread/session UUID 铺屏。
- Router fixture 返回 artifacts/display_path/hash 与 command termination。
- 前端 fixture 覆盖 compiled/support 和 `policy_rejected`。
- Playwright 覆盖 desktop/mobile/short viewport。

### 4.4 Docker cleanup

- 更新命令断言为 `docker stop --timeout`。
- 保留 stop timeout 后 force remove、remove timeout 和 audit 字段测试。

## 5. Phase C：P0 实现

候选文件：

- `scripts/docker-runtime.sh`
- `docker/docker-compose-dev.yaml`
- `.env.example`
- `backend/packages/harness/deerflow/compile/manager.py`
- `backend/packages/harness/deerflow/compile/operations.py`
- `backend/tests/test_compile_runtime.py`
- Compose contract tests

任务：

1. Wrapper 在 `.env` 加载后导出默认宿主 UID/GID，不修改冻结 `scripts/docker.sh`。
2. Compose 把身份传入两个可能承载 CompileSessionManager 的服务。
3. Manager 实现 pair 解析、单文件规范化、安全递归规范化和稳定事件。
4. metadata/workflow 写入后立即处理；终态在容器 cleanup 后处理全树。
5. 失败传播不覆盖已有编译/replay 证据。

完成门：权限与路径安全定向测试通过。

## 6. Phase D：P1 实现

候选文件：

- `backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py`
- prompt contract tests
- `docs/compile_runtime_v4.md`

任务：

1. 明确 CMake install 优先但非强制。
2. 明确 install 失败/空交付时的通用手工 staging。
3. 明确只有必要时执行一次 `find`，禁止 glob `ls` 探测。
4. 明确 stage 成功后直接 submit；保留原始/clean replay 双测试。

完成门：Prompt contract 和相邻 compile tool tests 通过。

## 7. Phase E：P2 实现

候选文件：

- `backend/packages/harness/deerflow/agents/middlewares/compile_termination_middleware.py`
- `backend/app/gateway/routers/compile_sessions.py`
- `frontend/src/core/compile/types.ts`
- `frontend/src/components/workspace/messages/compile-session-trace.tsx`
- 中英文 i18n 与对应测试

任务：

1. 复用稳定 helper 生成 artifact display path 和 compiled/support 分组。
2. 终态 Markdown 只展开 compiled，support 按目录汇总。
3. API 暴露完整 artifact manifest 与 command termination。
4. Evidence 卡增加完整产物区域；support 折叠。
5. Policy rejection 使用独立状态文案。

完成门：后端 formatter/router tests、前端逻辑和三视口截图通过。

## 8. Phase F：P3 与 Runtime v4

候选文件：

- `backend/packages/harness/deerflow/compile/docker_runtime.py`
- `backend/tests/test_compile_runtime.py`
- `docs/compile_runtime_v4.md`
- `benchmarks/runtime-identities/compile-runtime-v4.json`
- Runtime identity tests

任务：

1. `--time` 替换为 `--timeout`，不改变 timeout arithmetic。
2. 从最终实现计算 Runtime v4 component hashes。
3. 声明只允许交互式产品验证，不自动授权 provider/formal experiment。
4. 确认 v2/v3 和历史资产无 diff。

## 9. Phase G：文档与验证

- 更新 README/CLAUDE 中 Session 权限、CMake staging 和产物展示说明。
- 更新 `.claude/memory/project.md`，不覆盖用户条目。
- 后端定向后跑全量 pytest 与 Ruff。
- 前端跑单测、ESLint、TypeScript、Prettier、production build。
- 启动隔离前端 fixture 跑 Playwright 三视口并检查 console、overflow 和重叠。
- `git diff --check`、敏感信息扫描和冻结资产检查。

## 10. Phase H：PR、CI、合并与知识库

1. 中文提交，使用 `scripts/push-via-wsl.ps1` 推送。
2. 创建中文 PR，正文包含 `Closes #<issue>`、测试矩阵、实验边界和部署说明。
3. 等待所有 CI jobs 结束；失败则定位、修复、复测并再次等待。
4. 合并后回读 merge commit/tree 和 Issue closed 状态。
5. 更新知识库项目卡片、Linux 运行说明和编译分工/结果笔记，回读验证；不擅自提交知识库 Git 历史。

## 11. 服务器验收（合并后由用户发起）

1. 服务器 fast-forward 到合并提交并重建 Forge。
2. 用户通过 Ultra 发起一次 FMT 产品验证。
3. 检查 Session 终态、权限、install/staging 命令、双阶段 CTest、完整 manifest、终态汇总和容器清理。
4. 真实 provider 调用消耗 Token，不作为本地/CI 自动测试，也不构成正式实验授权。
