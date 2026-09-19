# Compile Runtime v4 工程契约

日期：2026-09-19。状态：`engineering_validation`。追踪 Issue：[#273](https://github.com/WWFXL/Forge-AutoCompiler/issues/273)。

Runtime v4 建立在 `main@fc50a3c7e3bd1a6755c1a8db71694582596a34c6` 之上，补齐 Docker bind mount 的宿主所有权、CMake 交付策略、完整产物展示和 Docker cleanup CLI 兼容性。它只授权交互式产品验证，不授权 provider experiment 或 formal collection。Runtime v2/v3 的 manifest、文档和历史 evidence 保持只读。

## 1. 不变的运行拓扑

Gateway 与 LangGraph 服务仍在 Compose 容器中运行，Compile Session 和 clean replay 仍通过宿主 Docker socket 创建独立容器。服务和编译容器继续使用 root；本版本不把整个运行栈切换为非 root。

每个 Session 的宿主目录仍是：

```text
$HOST_PROJECT_ROOT/.compile-sessions/<thread_id>/<session_id>/
```

编译容器继续分别挂载 `workspace/`、`artifacts/`、`logs/` 和 `repro/`。容器内仓库根固定为 `/workspace/repo`，交付根固定为 `/artifacts`。

## 2. 宿主 UID/GID 所有权

Docker 启动入口 `scripts/docker-runtime.sh` 在用户未显式配置时读取：

```text
FORGE_HOST_UID=$(id -u)
FORGE_HOST_GID=$(id -g)
```

两个变量必须同时存在并为 Linux 有效的非负整数。Compose 只把它们传给可能持有 `CompileSessionManager` 的 Gateway 和 LangGraph；只配置一个或值非法时立即失败。

Manager 执行两层规范化：

1. 每次原子替换 `session.json` 或追加 `logs/workflow.log` 后，立即设置目标 owner/group，并确保 owner 可读写。
2. 容器清理完成、Session 即将进入终态时，对该 Session 树执行一次递归规范化。

递归处理遵守以下边界：

- 目标必须严格对应 `.compile-sessions/<thread_id>/<session_id>`；
- root、thread 或 session 的符号链接边界被拒绝；
- 内部符号链接只处理链接 inode，不跟随目标；
- 目录确保 owner `rwx`，普通文件确保 owner `rw`；
- 保留 group 位和文件原有 executable 位，清除 other 的全部权限；
- 显式配置身份后若任何步骤失败，finalization 必须失败，不能声称宿主可管理。

这使启动 Forge 的用户可以读取、归档和删除自己的 Session，同时不会用 `chmod 777` 向其他普通用户开放 evidence。历史 Session 不自动迁移。

## 3. CMake 产物交付

Compiler 的默认顺序是 configure、build、候选测试、artifact staging、submit。

对于 CMake 项目，优先用项目已有安装规则一次性暂存：

```bash
cmake --install <build-dir> --prefix /artifacts
```

若安装规则缺失、失败或没有交付有效编译产物，Compiler 回到通用手工 staging，只复制明确的 executable/library/object、公共头文件、package metadata 和许可证。它应优先依据构建日志和已知 target 路径定位产物；仍不明确时最多执行一次 `find` 诊断，不使用未匹配 glob 的 `ls`。staging 成功后直接调用 `submit_build_result`。

候选容器中的项目测试与 clean replay 中的同一测试仍分别执行一次。前者验证当前候选，后者证明从固定 commit 和不可变 image ID 可以重现，不属于冗余诊断。

## 4. 终态摘要与完整证据

稳定的 `display_path` 由后端从 `/artifacts` 相对路径生成，前端不猜测 thread/session UUID。

终态 Markdown：

- 逐项列出 compiled artifacts 的短路径、类型和大小；
- support files 只显示数量并按目录汇总；
- 不把完整头文件清单铺进最终回答。

Compile Session snapshot 仍保留原始 `path`，并公开：

```text
artifacts[] = {path, display_path, artifact_type, size_bytes, sha256}
commands[].termination
```

Evidence 卡默认展开 compiled artifacts，support files 默认折叠；两类文件都可查看完整路径、大小和 SHA-256。`termination=policy_rejected` 显示为“策略拒绝”，退出码仅作为补充证据，不再伪装成普通 shell 权限失败。

## 5. Docker cleanup

当前 Docker CLI 使用：

```text
docker stop --timeout <grace_seconds> <container>
```

本版本只替换已弃用的 `--time` 拼写，不改变 cleanup 总 deadline、stop grace、失败后的有界 `docker rm -f`、container label 或审计事件。

## 6. 验证与授权边界

Runtime v4 的自动验证包括：

- UID/GID pair、原子 metadata/log 写入、POSIX mode 和 symlink 边界；
- 成功/失败终态的 ownership failure propagation；
- Compiler prompt、终态 formatter、Session API 和 Docker cleanup；
- 前端类型、lint、format、离线逻辑测试和三个视口的 Playwright fixture；
- Runtime v4 component hashes，以及 Runtime v2/v3 历史文件冻结检查。

本版本不运行真实模型 provider、不创建正式 experiment evidence，也不修改已有 Session 的实验解释。服务器完成一次人工 FMT 产品验证后，只能证明交互式产品路径可用；任何 provider canary 或正式采集都需要新的显式授权。
