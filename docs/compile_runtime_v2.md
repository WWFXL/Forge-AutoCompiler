# Compile Runtime v2 工程契约

日期：2026-09-19。状态：`engineering_validation`。

本文件描述 Issue #269 之后的当前产品运行时。它用于前端真实使用和工程验证，不授权 provider 实验或正式数据采集。历史 benchmark manifest、Schema、evidence 以及其对应代码身份保持冻结；旧协议必须在其固定 Git revision 上审计。

## 1. 解决的问题

Compile Runtime v2 收敛四类真实故障：

1. 一次 Shell 调用混合 configure、build 和日志截取，前序失败被 `tail`、`echo` 或管道末端成功状态掩盖。
2. 同一 Agent run 重复 prepare，创建多个活动 session/container，丢失已经安装的依赖和中间结果。
3. 用户取消、子代理超时或运行结束时没有可靠回收容器。
4. replay 从全部成功命令隐式推导，诊断命令、smoke 命令或宿主路径污染 `repro/build.sh`。

v2 将“完整审计历史”和“可重放配方”分开：所有命令继续写入 session；只有 Compiler 显式选择且通过校验的 command IDs 进入 replay。

## 2. 一次编译的身份

三个身份不要混用：

| 身份 | 含义 | 主要来源 |
|---|---|---|
| `thread_id` | 前端会话，可包含多个顺序执行的 run | LangGraph thread |
| `run_id` | 一次用户请求对应的 Agent 执行 | Runtime context、`configurable.run_id` 或标准 `RunnableConfig.run_id` |
| `session_id` | 一个持久化编译会话及其 workspace/artifacts/logs | `prepare_compile_session` 创建 |

同一 `run_id` 在任一时刻最多拥有一个非终态 session。幂等键为 `run_id + repo_url + branch + image`：

- 产品工具无法取得 `run_id` 时拒绝 prepare，不创建无 owner 的 session；
- 相同请求重复 prepare：返回原 session/container，继续使用原 workspace、已安装依赖和中间文件。
- 同 run 的不同 repo/branch/image：返回 `active_session_conflict`。
- 检测到多个非终态 session：返回 `multiple_active_sessions`，不再创建容器。
- 已终态 session 不会复活；之后的新 prepare 可以创建新 session。

原子性由进程内 run lock 保证，当前部署假设同一 LangGraph 服务进程管理该 run。若未来改为多进程或多副本共享同一 workspace，需要把这把锁升级为跨进程锁或事务存储。

## 3. 阶段化 Shell

`run_container_bash` 的 `command_role` 是必填六值枚举：

- `dependency`
- `configure`
- `build`
- `diagnostic`
- `smoke`
- `artifact_stage`

一次调用只能完成一个逻辑阶段。运行时会：

1. 先生成稳定 `command_id`；
2. 把完整输出写入 `logs/{command_id}.log`；
3. 拒绝可确定包含多个逻辑阶段的命令；
4. 拒绝 `set +e`、`set +u`、`set +o pipefail` 等关闭严格选项的命令；
5. 使用 `set -euo pipefail` 执行；
6. 把 exit code、timeout、role、workdir 和日志路径追加到 `session.commands`。

因此 `false | tee output.log` 和 `false; echo done` 都会失败。提示词同时禁止 `|| true`、检查 `$?` 后转为成功、以及用 `tail/head` 包裹关键命令。工具不会尝试完整解析任意 Shell AST；复杂错误容忍结构仍属于 Compiler 契约禁止项。

## 4. 显式 replay recipe

构建成功并把产物复制到 `/artifacts` 后，Compiler 必须显式调用：

```json
{
  "supporting_command_id": "command_build",
  "recipe_command_ids": [
    "command_dependency",
    "command_configure",
    "command_build",
    "command_artifact_stage"
  ]
}
```

校验规则：

- IDs 必须来自当前 session，唯一且保持原审计顺序；
- 只允许成功、未超时的 `dependency/configure/build/artifact_stage`；
- 必须至少包含一个 `build` 和一个 `artifact_stage`；
- supporting command 必须在 recipe 内、role 为 `build`，并对应当前 post-build 候选；
- workdir 必须在 `/workspace` 或 `/artifacts` 下；
- 命令不得引用宿主路径、`.compile-sessions`、`/logs`、`/repro`、thread/session ID；
- diagnostic、smoke、失败、超时、重复和乱序步骤在启动 replay 前被拒绝。

拒绝结果包含稳定 `classification` 和 `offending_command_id`。验证通过后，session 持久化 recipe 的 command/workdir 哈希和 fingerprint；`repro/build.sh` 只渲染这些显式步骤。

clean replay 仍从远端 clone 固定 commit，使用原 session 保存的不可变 `image_id`，在全新的 workspace/artifacts 中执行。相同 fingerprint 的已通过结果或清理成功的确定性失败不会重复创建容器；recipe 或候选产物变化后才创建新 attempt。

## 5. 容器 ownership 与清理

compile/replay 容器都有完整 labels：

```text
deerflow.compile.managed=true
deerflow.compile.role=compile|replay
deerflow.compile.thread_id=<thread>
deerflow.compile.run_id=<run>
deerflow.compile.session_id=<session>
deerflow.compile.attempt_id=<replay only>
```

清理是幂等的，且只操作 ownership 可证明的容器：

- `finalize_session` 负责正常业务收尾；
- compiler task 的失败、超时和取消会在 worker 停止前后两次对账并清理；
- Lead Agent 正常结束时，`CompileTerminationMiddleware.after_agent` 清理该 run 未完成的 session；
- Gateway 内嵌运行模式在 worker `finally` 中覆盖 success/error/cancel/timeout；
- 每次 prepare 前执行 orphan reconciliation，只删除“labels 完整、身份与持久化 session 匹配、session 已终态”的容器。

无法证明 ownership、session 仍活动、标签不完整或身份不匹配时一律保留并记录。标准 LangGraph 服务若被强制结束进程，Python 清理路径可能来不及把 session 写成终态；reconciliation 会保留这类仍标记为活动的容器，避免把另一个真实运行中的容器误删。此时需要先根据 `session.json` 和 Docker labels 确认身份，再显式结束 session；不能通过名称前缀批量删除。

## 6. 目录和证据

宿主机：

```text
$HOST_PROJECT_ROOT/.compile-sessions/{thread_id}/{session_id}/
├── session.json
├── workspace/repo/
├── artifacts/
├── logs/
│   ├── workflow.log
│   └── command_<uuid>.log
├── repro/build.sh
└── replay/{attempt_id}/
    ├── recipe/build.sh
    ├── workspace/
    ├── artifacts/
    └── logs/
```

容器挂载：

| 宿主 session 目录 | 容器路径 | 用途 |
|---|---|---|
| `workspace/` | `/workspace` | clone 与 build tree |
| `artifacts/` | `/artifacts` | 最终候选产物 |
| `logs/` | `/logs` | 完整命令日志 |
| `repro/` | `/repro` | replay 配方 |

用户可通过前端编译详情或 Gateway 只读 API 查看 session、命令和有界日志；宿主机上的文件是权威完整证据。

## 7. 身份与测试边界

当前产品身份记录在 `benchmarks/runtime-identities/compile-runtime-v2.json`，其中核心 Python 组件使用 SHA-256 固定。授权边界为：

- `interactive_product_validation=true`
- `provider_experiment_execution=false`
- `formal_collection=false`

CI 分成两条独立路径：

1. 当前产品测试在 PR 当前代码上运行，并排除历史 `test_forge_*.py` 协议测试；
2. 冻结研究测试检出 predecessor commit，再运行历史 `test_forge_*.py`。

这不是兼容层。v2 不保留旧的隐式 recipe 工具 schema；历史实验继续在冻结 revision 上复核，当前产品代码可以演进。

## 8. 非目标

- 不允许配置“可接受的非零退出码”。
- 不实现项目 profile、文档优先级、子模块策略、依赖缓存和阶段预算等复杂仓库 P2 能力。
- 不修改历史 benchmark manifest/evidence。
- 不用本次工程验证运行 provider canary 或正式实验。
- 不自动清理服务器上无法证明 ownership 的旧容器。
