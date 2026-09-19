# 编译运行时可靠性实施计划

日期：2026-09-19。设计：`../specs/2026-09-18-compile-runtime-reliability-design.md`。状态：**用户已批准实施；必须先创建并回读 Issue，再修改业务代码**。

## 1. 交付范围

本计划用一个追踪 Issue 和一个小而完整的 PR 交付：

- `run_container_bash` 显式 role、一次一个逻辑阶段、强制 `set -euo pipefail`；
- 同 run 单活动 session/container，重复 prepare 幂等复用；
- success/error/cancel/recursion exhausted 的 run 级统一清理与启动 orphan reconciliation；
- `submit_build_result` 显式 `recipe_command_ids` 和 replay 去重；
- `command_id` 唯一日志命名；
- 对应回归测试、开发文档和项目状态快照。

不实施 P2 项目 profile、artifact consumer gate、真实 provider 实验或服务器遗留容器清理。

## 2. 强制顺序

- [x] 用户批准实施范围。
- [x] 完成并检查最新版 Spec/Plan。
- [ ] 创建中文 GitHub Issue，回读标题和正文确认格式正确。
- [ ] Issue 创建成功后，从最新 `origin/main` 创建独立实现 worktree。
- [ ] 将已批准 Spec/Plan 带入实现分支。
- [ ] 先写失败测试，再修改业务代码。
- [ ] 跑定向、相邻和全量测试。
- [ ] 更新文档和 `.claude/memory/project.md`。
- [ ] 中文提交，通过 `scripts/push-via-wsl.ps1` 推送。
- [ ] 创建并回读中文 PR，使用 `Closes #<issue>`。
- [ ] 等待 CI，通过后合并并确认 Issue 自动关闭。

## 3. Phase A：Issue 与实现基线

1. `git diff --check` 检查 Spec/Plan，提交设计更新。
2. Issue 正文包含证据、设计不变量、验收标准和非目标。
3. 用 `gh issue view` 回读，确认不存在字面 `\n`、字段漂移或敏感路径。
4. 获取最新 `origin/main`；不覆盖主 worktree 中用户未提交内容。
5. 新建 `fix/compile-runtime-reliability` worktree，确认 clean tree 和基线提交。
6. 阅读根、`backend/` 范围的 AGENTS/CLAUDE 指令及现有类型和测试，再锁定实际修改文件。

## 4. Phase B：测试先行

先建立失败回归，测试不得调用真实 provider。

### 4.1 Shell 和日志

- `false | tee output.log` 返回非零。
- `false; echo done` 返回非零，日志中不出现 `done`。
- build 失败后同一脚本的 `tail` 不执行。
- 缺失或非法 role 被 schema 拒绝。
- 并发 100 条命令生成 100 个 `command_id` 和 100 个唯一日志文件。

### 4.2 Prepare 幂等与冲突

- 串行相同 prepare 返回相同 session/container。
- 并发相同 prepare 只调用一次容器创建。
- 同 run 不同 repo/branch/image 返回 `active_session_conflict`。
- 人工构造多个活动 session 返回 `multiple_active_sessions`，且不再创建容器。
- 编译命令失败后重复 prepare 仍复用原 workspace。

### 4.3 生命周期清理

- success、exception、cancel、recursion exhausted 四条 run 路径都调用相同 cleanup。
- cleanup 同时处理 compile/replay containers，重复调用不报错。
- stale worker 保存不能覆盖父级终态/termination reason。
- orphan reconciliation 忽略无 Forge labels、labels 不完整或 run 仍活动的容器。

### 4.4 显式 recipe

- 不提供 recipe IDs、跨 session、失败、超时、重复、乱序均拒绝。
- diagnostic、smoke 和不可移植路径被拒绝。
- supporting build 不在 recipe、role 非 build 或已被后续 build 取代时拒绝。
- 正确的 dependency/configure/build/artifact_stage recipe 可生成并 clean replay。
- 相同确定性失败 fingerprint 第二次不创建 replay container；输入变化后允许新 attempt。

## 5. Phase C：数据模型与 manager

候选文件：

- `backend/packages/harness/deerflow/compile/schemas.py`
- `backend/packages/harness/deerflow/compile/manager.py`
- `backend/packages/harness/deerflow/compile/paths.py`
- 对应 `backend/tests/test_compile_*.py`

任务：

1. 集中定义 command roles、terminal session statuses 和 ownership labels。
2. command record 持久化显式 role、唯一 log ID/path 和必要哈希。
3. 新增显式 replay recipe 数据，并只保存对 audit command 的稳定引用。
4. manager 在同一 lock 内提供 `get_or_create_active_session`，实现 resume/conflict/inconsistency。
5. 保存逻辑保留第一终止原因，并限制终态 cleanup 可合并字段。
6. 新增 run-owned session/container 查询和清理证据事件。

完成门：manager/schema 定向测试全部通过，且序列化 round-trip 不丢新字段。

## 6. Phase D：Shell 工具与 Compiler 契约

候选文件：

- `backend/packages/harness/deerflow/tools/bound_compile_tools.py`
- `backend/packages/harness/deerflow/compile/docker_runtime.py`
- `backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py`
- 对应 tool、runtime、prompt 测试

任务：

1. `run_container_bash` 增加必填 role 枚举，并透传到 command record。
2. Docker exec 使用临时脚本统一注入 `set -euo pipefail`，调用者不能关闭严格选项。
3. 完整输出只进入唯一 `{command_id}.log`，工具返回有界预览和 `/logs/{command_id}.log`。
4. 更新 Compiler 提示词：阶段拆分、禁止输出截断吞错、失败后独立 diagnostic、最终显式 recipe。
5. 更新 prompt/schema 快照，删除旧的隐式 recipe 描述。

完成门：Shell、日志并发和提示词回归全部通过。

## 7. Phase E：Prepare 与 run 生命周期

候选文件：

- `backend/packages/harness/deerflow/compile/operations.py`
- `backend/packages/harness/deerflow/compile/docker_runtime.py`
- `backend/packages/harness/deerflow/tools/builtins/agent_compile_tools.py`
- `backend/packages/harness/deerflow/agents/middlewares/compile_termination_middleware.py`
- LangGraph run/启动生命周期现有入口

任务：

1. 把 prepare 改为 manager 的原子 create-or-resume，不在 operation 外先查后建。
2. compile/replay container 创建时补齐 `run_id/thread_id/session_id/role` labels。
3. 在已存在的 run 生命周期最外层接入统一 `finally` cleanup；不得把清理责任继续交给模型。
4. 取消路径对账可能仍在创建的 worker，再次按 labels 幂等清理。
5. 启动入口执行 label-scoped orphan reconciliation，并记录结果。
6. 保持 `finalize_session` 的业务验证职责，但资源回收不再依赖它是否被调用。

完成门：prepare 并发测试与四条终止路径全部通过；无法定位权威 run 生命周期边界时立即停止。

## 8. Phase F：显式 recipe 与 replay

候选文件：

- `backend/packages/harness/deerflow/compile/operations.py`
- `backend/packages/harness/deerflow/compile/replay.py` 或现有 replay 实现模块
- `backend/packages/harness/deerflow/tools/bound_compile_tools.py`
- 对应 submit/replay 测试

任务：

1. `submit_build_result` 要求 `supporting_command_id` 和有序 `recipe_command_ids`。
2. 校验 command ownership、顺序、成功状态、role、workdir 和不可移植路径。
3. supporting build 必须在 recipe 中，且是候选对应的有效 build。
4. build script 只按显式 recipe 渲染；clone 固定 commit 仍由 replay bootstrap 管理。
5. 为 recipe、commit、image 和 artifact snapshot 计算 fingerprint，阻止相同确定性失败重复 replay。
6. 结构化返回 `classification`、`offending_command_id` 和修复建议，不暴露敏感命令内容。

完成门：显式 recipe 正例、所有拒绝分支和 replay 去重测试通过。

## 9. Phase G：验证

按风险从小到大串行执行：

1. 改动模块定向 pytest。
2. compile manager/tools/runtime/replay/termination 相邻测试集。
3. 改动 Python 文件 Ruff check 与 format check。
4. backend 全量 lint/test；既有失败必须用 `origin/main` 同环境复核，不能口头归因。
5. 若本机 Linux Docker daemon 可用，运行不访问真实 provider 的 Docker 集成测试，验证唯一容器、clean replay 和取消清理。
6. `git diff --check`、敏感信息扫描、frozen manifest/evidence diff 检查。

不通过的测试必须修复或明确阻塞，不以“读代码应该正确”代替运行验证。

## 10. Phase H：文档、PR 与合并

1. 更新 `CLAUDE.md` 编译核心契约及相关运行机制文档，说明显式 role/recipe、session 复用和 run cleanup。
2. 更新 `.claude/memory/project.md`，只登记本次真实变更，不覆盖其他 worktree 的用户修改。
3. 使用中文提交信息形成一个可审阅提交序列。
4. 运行 `pwsh -NoProfile -File scripts/push-via-wsl.ps1` 推送实现分支。
5. 创建中文 PR，正文包含 `Closes #<issue>`、测试证据、非目标和迁移影响。
6. 用 `gh pr view` 回读 PR；检查 CI，失败则定位并修复。
7. CI 全绿后合并；回读 PR、Issue 和 `origin/main`，确认合并完成、Issue 已关闭。

## 11. 停止并请求用户决策的条件

遇到以下任一情况，停止扩大实现：

- 必须修改 frozen benchmark manifest、Schema 或历史 evidence。
- 现有代码中找不到能覆盖 success/error/cancel/recursion exhausted 的权威 run 生命周期边界。
- 现有持久化/锁机制无法保证 prepare 原子化，必须引入外部数据库或分布式锁。
- 显式 recipe 仍必须依赖解析任意 Shell 才能判断 membership。
- 回归只能通过调用真实模型 provider 才能建立。
- cleanup 无法严格限制在完整 Forge ownership labels 范围内。
- 最新 `main` 与设计假设发生实质冲突，需要改变用户已批准的外部行为。
