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

**默认优先级**：

1. Docker 开发环境（推荐）
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

Forge-AutoCompiler 的编译能力依赖一个 GCC/Clang 工具链镜像，默认 `autocompiler:gcc13`。安装阶段**不要**自动拉这个镜像（它可能很大）；只要在汇报里提醒用户：

> 第一次跑编译前请确保 `autocompiler:gcc13`（或你在 `config.yaml` 中指定的镜像）已 `docker pull` 到本机。

## 环境变量提示

启动时如果走本机模式（`make dev`），脚本会自动注入 `HOST_PROJECT_ROOT`。如果用户手动 `cd backend && make dev` / `make gateway`，必须自己 export：

```bash
export HOST_PROJECT_ROOT="$(pwd)"
```

否则 `CompileDockerRuntime` 在创建编译容器时会报 `HOST_PROJECT_ROOT is not configured`。
