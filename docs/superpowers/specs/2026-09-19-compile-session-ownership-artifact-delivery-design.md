# 编译会话宿主权限、产物交付与终态展示设计

日期：2026-09-19。状态：**设计完成，待 Issue 审核与实现**。

本设计承接 Compile Runtime v3，处理 2026-09-19 FMT 产品验证后发现的四类工程问题：宿主用户无法管理编译会话、Compiler 在构建后重复且脆弱地探测产物、完整交付 manifest 在终态页面逐项铺开，以及 Docker cleanup 使用弃用参数。

实施顺序固定为：Spec、Plan、GitHub Issue、失败测试、业务代码、完整验证、PR、CI、合并和知识库更新。不得修改 Runtime v2/v3、历史 benchmark、manifest 或正式 evidence。

## 1. 真实证据

本次 FMT 运行：

```text
thread_id  = 7dcc930a-37f8-489b-8254-fe6a404c7bb8
run_id     = 01a0b968-ef23-7d43-af6a-34857918162c
session_id = e3b515fa710a
commit     = fd0a9b6620c8f44fac2122adb1cc29664aa96325
```

产品主链路正确完成：session 为 `completed`，原始和 clean replay 的 22 个 CTest 全部通过，19 个交付文件的路径、类型、大小和 SHA-256 一致，compile/replay 容器均被删除，服务健康检查为 HTTP 200。

运行同时暴露：

- 宿主 `yiwei` 为 `1010:1010`，Gateway、LangGraph、compile/replay 容器均以 UID/GID `0:0` 写 bind mount；`session.json` 最终为 `600 root:root`，宿主用户无法读取；
- Compiler 用 `ls build/*.so* build/*.a*` 探测产物。未匹配的 `.so` glob 在严格 shell 下让命令退出 2，随后模型为同一目的再次执行 `ls`，又被 post-build 预算拒绝；
- FMT 的 2 个静态库和 17 个 support files 按完整 manifest 全部进入终态 Markdown，页面被长 UUID 路径和逐项头文件占满；
- compile/replay cleanup 日志出现 `Flag --time has been deprecated, use --timeout instead`；
- 策略拒绝在证据 UI 中只显示退出码 126，容易被误解为 Linux 文件执行权限错误。

## 2. 目标与非目标

### P0：宿主会话可管理

1. Docker 模式自动把启动用户 UID/GID 传给 Gateway 和 LangGraph。
2. 服务继续以 root 运行，不迁移 `/root/.codex`、uv cache 或 Docker socket 权限模型。
3. 每次原子写入 `session.json` 和 `workflow.log` 后立即规范化对应文件。
4. Session 进入终态时，对当前 Session 树执行一次不跟随符号链接的所有权与权限规范化。
5. 只允许处理 `.compile-sessions/<thread_id>/<session_id>`；任何根目录、跨 Session 或符号链接逃逸都必须拒绝。
6. 宿主用户最终能读取、修改、归档和删除自己的 workspace、artifacts、logs、repro、replay 和 metadata。

### P1：构建后流程最小且稳健

1. CMake 项目优先使用项目自己的 install 规则：`cmake --install <build-dir> --prefix /artifacts`。
2. install 规则不可用、失败或没有产生有效交付物时，保留手工 artifact staging 通用路径。
3. 必须定位产物时，优先依据构建输出和已知构建系统路径；仍不明确时最多执行一次基于 `find` 的诊断，不使用未匹配 glob 的 `ls`。
4. staging 成功后直接 submit，不再用 `ls` 重复验证 `/artifacts`；`submit_build_result` 是该目录的确定性验证者。
5. 原始容器的项目测试与 clean replay 的同一测试仍各运行一次：前者验证候选，后者验证可复现性，不视为重复。

### P2：终态简洁、证据完整

1. 终态消息显示 compiled/support 数量和短相对路径，不显示 thread/session UUID 前缀。
2. compiled artifacts 直接列出；support files 默认只按目录汇总。
3. Compile Session 证据卡提供可展开完整清单，保留类型、大小和 SHA-256。
4. API 保留原始路径，同时增加稳定的 `display_path`，展示层不自行猜测 UUID 前缀。
5. Command 证据公开 `termination`；`policy_rejected` 显示为“策略拒绝”，不伪装成 shell 权限错误。

### P3：清理命令兼容当前 Docker CLI

把 `docker stop --time` 改为 `docker stop --timeout`，保持既有 grace、外层 deadline、stop 失败后 bounded `rm -f` 和审计字段不变。

### 非目标

- 不把 Gateway/LangGraph/compile 容器整体改为非 root。
- 不用 `chmod 777` 或全局放宽 `.compile-sessions`。
- 不自动修复全部历史 Session；历史数据只提供明确的人工迁移指令。
- 不把 `cmake --install` 设为唯一 staging 方法。
- 不删除候选测试或 clean replay 测试。
- 不运行 provider canary、真实模型回归或正式实验。
- 不修改 Runtime v2/v3 和历史实验资产。

## 3. 宿主身份与配置

新增可选成对配置：

```text
FORGE_HOST_UID
FORGE_HOST_GID
```

规则：

- 两者同时缺失时，非 Docker/Windows 开发路径保持 no-op；
- 只配置一个、不是非负整数或超出平台 UID/GID 范围时启动/首次使用即失败，不能静默回退 root；
- `scripts/docker-runtime.sh` 在加载 `.env` 后使用 `id -u` / `id -g` 提供默认值；用户显式值优先；
- `docker-compose-dev.yaml` 把二者传给 Gateway 和 LangGraph；
- `.env.example` 记录用途和手工启动要求；冻结的 `scripts/docker.sh` 不修改。

生产 Compose 当前不承载 Compile Session 的同一 host workspace 契约，本次不顺手扩张其拓扑。

## 4. Session 权限规范化

`CompileSessionManager` 增加内部宿主身份策略和以下窄接口：

```text
normalize_metadata(session)
normalize_event_log(session)
normalize_session_tree(session)
```

### 4.1 路径边界

规范化前必须：

1. 取得配置的 compile sessions root；
2. 对 root 与 session directory 做真实路径解析；
3. 要求 session directory 严格位于 root 下且相对部分正好是 `<thread>/<session>`；
4. 拒绝 root/session 自身为符号链接或解析到 root 外；
5. 遍历内部条目时使用 `lstat`/`os.walk(..., followlinks=False)`，符号链接只修改链接 inode 的 owner，不跟随目标，也不对链接执行 chmod。

### 4.2 权限规则

- owner/group 设置为配置 UID/GID；
- 目录确保 owner `rwx`，文件确保 owner `rw`；
- 清除 other 的 `rwx`；
- 保留现有 group bits 和文件 executable bits，不把可执行产物统一降为普通文件；
- `session.json` 与 workflow log 在每次写入后立即处理，避免终态前完全不可读；
- 全树规范化只在容器清理完成且 Session 正在进入终态时执行，避免遍历仍在并发写入的构建树。

若显式配置了宿主身份但规范化失败，必须留下稳定错误和事件，不能声称“宿主可管理”。编译正确性和交付完整性仍由 manifest/replay 决定；权限错误属于 finalization/operations failure。

## 5. Compiler staging 契约

Compiler 提示词调整为：

1. configure；
2. build；
3. 运行一个合适的项目测试或 smoke；
4. CMake 项目优先以单独 `artifact_stage` 调用执行：

   ```bash
   cmake --install /workspace/repo/build --prefix /artifacts
   ```

5. 若项目没有有效 install 规则，使用构建日志/已知目标确定交付文件；只有仍不明确时执行一次 `find` 诊断；
6. 手工 staging 只复制明确要交付的 compiled artifacts、公共头文件、package metadata 和许可证；
7. staging 成功后直接 submit。

推荐诊断形式：

```bash
find build -type f \( -name '*.a' -o -name '*.so' -o -name '*.so.*' -o -perm -111 \) -print
```

空匹配只产生空输出；build directory 不存在等真实错误仍返回非零。工具继续执行 `set -euo pipefail`，不为模型引入吞错兼容层。

## 6. 终态与证据展示

### 6.1 短路径

后端以 `source_path=/artifacts/...` 为首选，或从持久化路径中安全截取 `artifacts/` 后缀，生成相对 POSIX `display_path`。不能由前端正则猜测 UUID 格式。

### 6.2 终态 Markdown

示例：

```text
### 构建产物
- 编译产物：2
  - `lib/libfmt-c.a`（static_library, 5642 B）
  - `lib/libfmt.a`（static_library, 253264 B）
- 辅助文件：17
  - `include/fmt/`：16 个文件
  - `LICENSE`：1 个文件
```

辅助文件不在终态逐项铺开。完整 manifest 在结构化证据卡中展开。

### 6.3 证据 API 与 UI

Compile Session snapshot 增加：

```text
artifacts[] = {path, display_path, artifact_type, size_bytes, sha256}
commands[].termination
```

前端：

- 显示 compiled/support 汇总；
- compiled 默认展开；
- support 置于 `<details>`，按短路径逐项展示；
- 所有固定格式元素具有稳定尺寸和换行规则，移动端无横向溢出；
- `termination=policy_rejected` 使用文案“策略拒绝”，退出码只作为补充证据。

## 7. Docker cleanup

只替换 CLI 选项：

```text
docker stop --timeout <seconds> <container>
```

不改变：

- `COMPILE_DOCKER_STOP_GRACE_SECONDS`；
- stop subprocess timeout；
- cleanup 总 deadline；
- stop 失败后的 `docker rm -f`；
- stopped/removed 两个事实和事件结构。

## 8. 测试策略

### 后端

- UID/GID 缺失 no-op、成对解析、非法/单边配置失败；
- metadata 原子替换后 owner/mode 规范化；
- Session 全树不跟随 symlink，拒绝跨根和根目录本身；
- 保留 executable bit、清除 other 权限；
- finalize 成功、失败、取消均执行终态规范化；规范化失败不得伪装成功；
- Compiler 提示词固定 install 优先、单次 find 后备、stage 后直接 submit；
- 终态 summary 以短路径分组 compiled/support；
- snapshot API 返回 artifacts、display_path、sha256 和 termination；
- Docker stop 命令使用 `--timeout`，既有 bounded fallback 测试继续通过。

### 前端

- 类型与 API fixture 覆盖 artifacts 和 termination；
- 证据卡 compiled 默认展示、support 可展开；
- policy rejection 文案不显示为普通 shell failure；
- 1280x900、390x844 和短屏无横向溢出或重叠。

### 门禁

- 后端定向 compile/terminal/router tests、全量 pytest、Ruff；
- 前端单测、ESLint、TypeScript、Prettier、production build 和离线 Playwright；
- Runtime identity tests；
- 不调用 provider，不创建 Compile Session 正式 evidence。

## 9. Runtime 身份

Runtime v3 是已发布只读身份。本次修改 manager、Docker runtime、Compiler prompt、termination middleware 和 evidence API，新增 `forge-compile-runtime-v4`：

- predecessor：`main@fc50a3c7`；
- `interactive_product_validation=true`；
- `provider_experiment_execution=false`；
- `formal_collection=false`。

只有后续显式授权并完成新 canary 后，才能讨论把 Runtime v4 用于 provider experiment 或 formal collection。

## 10. 验收标准

- Docker 模式完成一次 FMT 后，`yiwei` 可直接读取 `session.json`，并能管理整个 Session 树；
- 其他普通用户没有 Session 树的 other 权限；
- 路径边界和 symlink 测试证明规范化不会逃逸当前 Session；
- FMT 风格 CMake 任务优先使用 install staging，或在无 install 规则时只做一次稳健诊断；
- staging 后不再由模型执行重复 `ls`；
- 终态只显示 2 个 compiled artifacts 和 17 个 support files 的目录汇总；完整 19 项可在证据卡展开；
- 策略拒绝与真实 shell 失败可区分；
- cleanup 无 `--time` 弃用警告且容器仍被有界删除；
- Runtime v2/v3 和历史实验资产无 diff。
