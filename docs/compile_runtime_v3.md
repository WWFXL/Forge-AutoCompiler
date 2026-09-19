# Compile Runtime v3 工程契约

日期：2026-09-19。状态：`engineering_validation`。追踪 Issue：[#271](https://github.com/WWFXL/Forge-AutoCompiler/issues/271)。

Runtime v3 建立在 `main@9ddf428ef3cc619a8f55e4e3305c92bb64bb2bfe` 之上，修复真实 LangGraph Runtime 终态、共享服务器资源边界、完整交付 manifest、项目测试重放和前端空 reasoning 布局。它只授权交互式产品验证，不授权 provider experiment 或 formal collection。Runtime v2 的 manifest、文档和历史 evidence 保持只读。

## 1. 生命周期终态

`CompileTerminationMiddleware` 从 `Runtime.context` 读取 `thread_id/run_id`，缺失时通过 LangGraph 的 `get_config()` 读取当前 `RunnableConfig`。它不访问不存在的 `Runtime.config`。

- 身份缺失：after-agent cleanup no-op。
- 身份存在且 session 未终态：清理当前 run 拥有的 session/container。
- session 已完成：不覆盖成功终态。
- 真实 cleanup 异常：继续上抛，不能用成功消息掩盖资源泄漏。

## 2. 冻结资源策略

prepare 创建 session 时读取一次 `COMPILE_MAX_PARALLEL_JOBS`，默认 `4`，并持久化为 `session.parallel_jobs`。compile 和 clean replay 容器都使用这个冻结值，不在 replay 时重新读取进程环境：

```text
docker run --cpus <parallel_jobs>
CMAKE_BUILD_PARALLEL_LEVEL=<parallel_jobs>
CTEST_PARALLEL_LEVEL=<parallel_jobs>
MAKEFLAGS=-j<parallel_jobs>
```

Docker quota 是 CPU 硬边界；工具环境为没有显式 jobs 参数的 CMake、CTest 和 Make 提供默认值。Compiler 不应生成裸 `-j`、`-j$(nproc)` 或高于策略的并行参数。

本版本不定义内存、PID、磁盘或全局多 session 调度策略。

## 3. 完整交付 manifest

`/artifacts` 是唯一交付根。系统递归记录安全普通文件，拒绝符号链接和目录逃逸：

- `executable`
- `shared_library`
- `object`
- `static_library`
- `support_file`

`support_file` 用于公共头文件、CMake package metadata、许可证等配套文件，记录相对 POSIX 路径、字节大小和 SHA-256。空 support file 可以进入 manifest；提交仍必须至少包含一个真实 compiled artifact。

候选检查、clean replay 和 cleanup 后 finalize 使用相同的文件分类与完整路径集合。任何文件增加、删除、类型变化、大小变化或 SHA-256 变化都会阻止 session 进入 `completed`。

## 4. Build 与 verification recipe

Compiler 提交三个显式字段：

```json
{
  "supporting_command_id": "command_build",
  "recipe_command_ids": ["command_configure", "command_build", "command_stage"],
  "verification_command_ids": ["command_ctest"]
}
```

`recipe_command_ids` 只允许成功、未超时、顺序不变且可移植的 dependency/configure/build/artifact_stage 命令，并生成 `repro/build.sh`。

`verification_command_ids` 只允许 supporting build 之后成功、未超时、顺序不变且可移植的 smoke 命令，并生成可选 `repro/verify.sh`。如果审计轨迹中存在成功的 post-build smoke，提交必须至少选择一个；没有可用项目测试时显式传空列表。

Replay 在同一个干净容器中执行：

1. 从远端拉取 session 固定的完整 commit。
2. 执行 `build.sh`，记录 `build.log` 和 build exit code。
3. 若存在，执行 `verify.sh`，记录独立 `verify.log` 和 verification exit code。
4. 比较完整 artifact manifest。
5. 删除 replay 容器。

Build 失败分类为 `recipe_execution_failed`；项目验证失败分类为 `verification_execution_failed`。两者不会被后续 artifact 比较掩盖。Recipe fingerprint 覆盖 commit、不可变 image ID、并行策略、完整候选 manifest、build steps 和 verification steps。

## 5. 构建系统证据

每次产品 submit 都从 supporting build 及其之前成功的 configure 命令推导 `executed_build_system`，写入 session 和 `build.execution_checked` workflow event。`selected_build_system` 是选择，`executed_build_system` 是执行证据，两者不能互相冒充。

Active experiment 复用同一个推导结果，再执行冻结策略匹配；不维护第二套产品/实验推导逻辑。

## 6. Docker cleanup

`COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS` 默认 `20` 秒，是 stop 与 force-remove 的总预算。`COMPILE_DOCKER_STOP_GRACE_SECONDS` 默认 `3` 秒，运行：

```text
docker stop --time <grace> <container>
```

外层 CLI timeout 比 grace 多控制面缓冲，同时必须给 `docker rm -f` 留出预算。stop 失败或 timeout 不会阻止有界 force-remove。事件分别记录 grace、CLI timeout、stopped 和 removed 事实。

## 7. 会话目录

```text
.compile-sessions/<thread_id>/<session_id>/
├── session.json
├── workspace/repo/
├── artifacts/
├── logs/
│   ├── workflow.log
│   └── <command_id>.log
├── repro/
│   ├── build.sh
│   └── verify.sh                 # 可选
└── replay/<attempt_id>/
    ├── recipe/
    │   ├── build.sh
    │   └── verify.sh             # 可选
    ├── workspace/
    ├── artifacts/
    └── logs/
        ├── build.log
        └── verify.log            # 可选
```

Gateway 提供只读 session snapshot、command log、replay build log 和 replay verification log。读取 API 不创建任务、不修改 evidence。

## 8. 前端消息布局

模型消息只有在实际 reasoning 文本去除空白后非空时才创建 reasoning group。`additional_kwargs.reasoning_content=""` 不再生成 6px 空边框，也不会挤压 Compiler 子任务标题。Compile trace 可以分别展开 replay build log 与 verification log。

## 9. 非目标与授权

- 不修改 Runtime v2 identity、benchmark manifest 或历史 evidence。
- 不调用真实模型 provider。
- 不创建正式实验 evidence。
- 不承诺跨 Docker daemon、跨主机或跨架构复现 image ID。
- 不把旧 session 重新解释为 v3 实验证据；loader 默认值只用于历史页面可读性。
