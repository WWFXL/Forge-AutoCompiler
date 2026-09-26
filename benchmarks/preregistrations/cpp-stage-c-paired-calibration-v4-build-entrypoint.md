# Stage C v4 构建入口与运行时合同修复预注册

日期：2026-09-26。追踪：Issue #325。来源：Stage C v3 失败审计 `benchmarks/reports/cpp-stage-c-paired-calibration-v3-failed.json`。

## 研究用途

Stage C v3 完成 `json-c` replicate 1 的完整 pair 后，在下一 pair 的正式 attempt 前错误拒绝 Stockfish 11：冻结源码的构建入口是 `src/Makefile`，v3 只检查仓库顶层。对已闭合 pair 的审计还发现，B 臂把辅助能力标签 `cmake-configure` 传入只接受规范 build-system 值的 Agent 合同；A 臂 oracle 则把 langgraph 容器路径误作宿主 Docker bind-mount 路径。v3 已产生正式结果，必须永久停止且不得续跑。

v4 从 0 个导入 outcome 重新执行完整的 12 projects × 2 replicates × 2 arms。不得导入 v1、v2 或 v3 的 outcome、pair、源码目录、reachability 或 batch marker，也不得把 v4 解释为旧 identity 的 retry、replacement 或 backfill。

## 唯一允许变化

1. build-system probe 先检查仓库顶层；仅当顶层没有任何已知 marker 时，按固定 build-system 顺序和字典序检查一层子目录。Stockfish 11 的冻结入口为 `src/Makefile`。
2. Agent 输入的 `build_system_candidates` 只包含运行时合同支持的 `cmake`、`make`、`autotools`；辅助能力标签仍保留在 source observation，不作为合同枚举值。`validate` 与 `preflight` 必须构造并校验全部 12 个任务的 Agent 输入。
3. A 臂 oracle 直接在候选镜像内运行，使用 `network=none`、只读 rootfs 和仅供 `/tmp` 的 tmpfs；不得用编排容器内路径创建宿主 bind mount。
4. exact-commit fetch 在首个 pair arm attempt 前最多执行 3 次，固定 HTTP/1.1，并仅为 Git 子进程映射既有 compile-runtime proxy。三次均失败时退出，不创建正式 attempt。
5. 全部 12 个 exact source 的 snapshot 与构建 marker 路径形成冻结的无模型结构审计。
6. evidence 目录、pair ID、attempt ID、protocol、runner 和 manifest/schema identity 更新为 v4 build-entrypoint。

任务、exact commit、project order、replicate、arm order、A/B 方法、Provider/model、不可变镜像、每臂预算、48-arm 上限、统一 evaluator、S0-S5、严格成功定义与 project-level 配对分析保持不变。

## 新 identity

- evidence：`/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v4-build-entrypoint`
- pair：`stage-c-v4-{task_id}-r{replicate}`
- attempt：`stage-c-v4-{task_id}-r{replicate}-{arm}`
- v1/v2/v3 evidence：只读，不导入结果
- v4 reachability：只允许 1 request / 5,000 recorded tokens
- v4 formal arms：48 arms / 14,400,000 recorded tokens 硬上限
- v1、v2 与 v3 实际消耗：72,769 recorded tokens
- 历史实际消耗与 v4 最坏上限合计：14,477,769 recorded tokens

## 执行顺序

1. 在合并后的干净 `main == origin/main` 上执行 `validate` 和非模型 `preflight`。
2. 核验 v3 失败审计、12-task source structure audit、manifest、runner、operations 和 Stage C image 绑定。
3. 运行真实 Docker gate，覆盖嵌套 build-system probe、候选镜像 oracle、三种构建系统和静态库验证。
4. 执行 v4 唯一 `reachability`。
5. 按冻结的 24-pair schedule 执行唯一 `batch`。
6. 只读生成 deployment、paired 和 inventory 报告，复算 usage、S0-S5、cleanup 与 0 managed resources。

## 停止与恢复规则

pair source 准备及其最多三次 fetch 均位于首个 `attempt.json` 前。该阶段失败时可以在环境修复后重新启动同一 v4 batch。只有完整连续 pair 前缀可以跳过。任一 `attempt.json` 已存在但 pair 未闭合时，整个 v4 identity 永久停止。禁止 retry、replacement、fallback、backfill、按结果重排以及导入任何旧 identity outcome。
