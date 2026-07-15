# 安装指南（面向编程 Agent）

本文档是给 coding agent（Claude Code / Codex / Cursor / Windsurf 等）看的引导式安装手册。让 agent 帮你把 Forge-AutoCompiler 本地开发环境拉起来。

> 想自己手动装的请直接看 [README_zh.md](README_zh.md) 的「快速开始」。

## 一句话指令

把下面这段发给 coding agent：

```
如果还没 clone Forge-AutoCompiler，就先 clone，然后按照 Install.md 把它的本地开发环境初始化好
```

agent 会自动按下面的流程执行。

---

## 目标

在用户机器上以最低风险路径搭出 Forge-AutoCompiler 本地开发工作区。

## Windows + WSL2（推荐路径）

Windows 不走“原生 PowerShell + Git Bash 拼装全部依赖”的路径。推荐在 WSL2 Ubuntu 中运行仓库命令，由 Docker Desktop 提供 Linux 容器引擎。已有 WSL 原生 Docker Engine 也可以使用，但不要把它和 Docker Desktop daemon 混用：两边的镜像、网络和容器互不可见。

1. 选择一套 Docker daemon。推荐安装并启动 Docker Desktop，在 **Settings > Resources > WSL Integration** 中启用 Ubuntu；若明确使用 WSL 原生 Docker Engine，则确认 Docker 服务和 Compose v2 插件已启动，不要同时混用两套 daemon。
2. 进入 WSL：

   ```powershell
   wsl -d Ubuntu
   ```

3. 在 WSL 中安装最小宿主依赖。此命令需要用户明确执行，不会由脚本静默运行：

   ```bash
   sudo apt update && sudo apt install -y build-essential git python3
   ```

4. 在仓库根运行预检：

   ```bash
   ./scripts/wsl-check.sh
   # 或 make wsl-check
   ```

5. 首次生成配置并启动 Docker 开发环境：

   ```bash
   make config
   # 编辑 config.yaml，配置至少一个模型和对应环境变量
   make compile-image
   make docker-start
   ```

6. 访问 <http://localhost:8000>。停止服务使用 `make docker-stop`。

仓库放在 `/mnt/c/...`、`/mnt/d/...` 等 Windows 挂载目录时可以运行，但文件监听和依赖安装通常慢于 WSL 自己的 `~/src`。编译 Session 会持久化在仓库根的 `.compile-sessions/`。

常见故障：

- `docker: command not found`：没有为当前发行版启用 Docker Desktop WSL Integration，也没有安装 WSL 原生 Docker Engine。
- `Docker daemon is not reachable`：Docker Desktop 尚未启动完成，或 WSL 原生 Docker 服务没有启动。
- `make: command not found`：安装 `build-essential`。
- 构建镜像下载依赖超时：在根目录 `.env` 中按网络情况设置 `NPM_REGISTRY`、`UV_INDEX_URL` 或 `APT_MIRROR`；`UV_HTTP_TIMEOUT` 默认是 600 秒。
- 编译镜像需要代理时使用 `COMPILE_HTTP_PROXY` / `COMPILE_HTTPS_PROXY`；不要填写容器内不可达的 WSL `127.0.0.1` 代理地址。
- 不要在启用 Docker Desktop 集成后，再在 WSL 内同时启动第二套 Docker daemon。若明确使用 WSL 原生 Docker，请始终在同一个 WSL 发行版中运行 `make` 和 `docker`；保持该 WSL 会话运行，Windows 侧的 `docker.exe` 看不到这些容器。

**默认优先级**：

1. Docker 开发环境（Windows 上通过 WSL2，推荐）
2. 本机原生开发环境

**不要假设** API key / 模型凭据已经就位。能安全准备的都准备好，最后简洁汇报还缺什么。

## 操作准则

- **幂等**：重复执行不应破坏已经搭好的环境
- 优先用 repo 自带的 `make` 命令，避免临时 shell 命令
- **不允许** `sudo` 或装系统包，除非用户明确同意
- **不覆盖**用户已有的 `config.yaml` 等本地配置
- 任一步失败立刻停下，解释卡点并给出最小修复指令
- 多种安装路径可选时，**Docker 可用就用 Docker**

## 成功判据

满足以下全部条件视为安装成功：

- 仓库已 clone 且当前工作目录是仓库根
- `config.yaml` 存在
- Docker 路径：`make docker-init` 完成（容器/镜像就绪，但**未启动服务**）
- 本机路径：`make check` 通过、`make install` 完成
- 已告知用户**下一条**启动命令
- 已告知用户 `config.yaml` 中缺失的模型配置或 `$VAR` 占位符（不读 `.env` 等含敏感信息文件）

## 步骤

1. 若当前不在 Forge-AutoCompiler 仓库根，先 clone 并 `cd` 进去。
2. 检查仓库根存在 `Makefile`、`backend/`、`frontend/`、`config.example.yaml`。
3. 判断 `config.yaml` 是否已存在。
4. 不存在则跑 `make config`（注意：**`make config` 非幂等**，已存在会主动 abort，这是正常行为）。
5. `docker info` 检查 Docker 是否可用。
6. **若 Docker 可用**：
   - 跑 `make docker-init`
   - 这一步只算「Docker 准备就绪」，不要声称服务已启动、compose 已校验、镜像已构建完
   - 除非用户明确要求或要做启动验证，**不要自动 `make docker-start`** 起后台服务
   - 告知用户下一条命令是 `make docker-start`
7. **若 Docker 不可用**：
   - 跑 `make check`
   - 若报缺 `node`/`pnpm`/`uv`/`nginx`，**停下并报告**，不要擅自 `sudo apt install`
   - 前置满足则 `make install`
   - 告知用户下一条命令是 `make dev`
8. **检查 `config.yaml` 是否需要补**：只看模型条目和 `$VAR` 占位符的**变量名**。**不读** `.env` / `frontend/.env` 或任何可能含 secret 的文件。
9. 若 `models[]` 为空，告知用户必须在 `config.yaml` 加至少一个模型条目。
10. 若 `config.yaml` 引用 `$OPENAI_API_KEY` 等变量，告知用户**变量名**仍需 export 真值，但**不去验证**这些 secret 文件的内容。
11. 若仓库看起来已配置完成，不做重复的耗时操作。

## 验证（轻量）

**Docker 路径**：
- 确认 `make docker-init` 完成
- 确认 `config.yaml` 存在
- **明确告知**「Docker 服务尚未启动，`make docker-start` 才是真正的启动步骤」
- 不要留下后台服务在跑（除非用户要求）

**本机路径**：
- 确认 `make install` 完成
- 确认 `config.yaml` 存在
- 不要留下后台服务在跑

## 最终回复格式

简短状态报告，包括：

1. **采用路径**：Docker / 本机
2. **达到的安装级别**：「Docker 前置就绪」/「本机依赖装完」
3. **创建或检测到的文件**：如 `config.yaml`
4. **用户还需做什么**：模型配置 / 环境变量 / auth 文件，或「无」
5. **下一条启动命令**：`make docker-start` / `make dev`

## 执行

按上述步骤执行。完成后停在「安装完成」边界，**不要**继续跑业务任务，把状态报告给用户即可。

---

## 关于编译镜像

Forge-AutoCompiler 的编译能力依赖 GCC 工具链镜像，默认 `autocompiler:gcc13`。镜像定义已放在 `docker/compile/Dockerfile`，首次编译前运行：

```bash
make compile-image
```

镜像可能较大，安装 Agent 未获授权时不要自动构建；但不能把“服务已启动”等同于“编译链路已就绪”。

## 环境变量提示

启动时如果走本机模式（`make dev`），脚本会自动注入 `HOST_PROJECT_ROOT`。如果用户手动 `cd backend && make dev` / `make gateway`，必须自己 export：

```bash
export HOST_PROJECT_ROOT="$(pwd)"
```

否则 `CompileDockerRuntime` 在创建编译容器时会报 `HOST_PROJECT_ROOT is not configured`。
