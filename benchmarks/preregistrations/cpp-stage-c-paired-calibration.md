# Stage C 十二项目配对校准预注册

日期：2026-09-26。实现追踪：Issue #312。设计追踪：Issue #310。

## 研究问题

在 exact-commit 源码、固定 Stage C 镜像、相同模型、相同单臂预算、相同网络与资源政策，以及独立 S0-S5 evaluator 下，比较 CXXCrafter-style controlled baseline（A）与 Forge Agent Workflow Node v2（B）的严格可复现构建成功率、成本和失败结构。

本预注册授权资格检查与 Stage C 执行身份的实现。正式 Stage C 尚未开始；资格结果、授权 manifest、const Schema、干净 release preflight 和 0 managed resources 全部闭合前，不得执行 reachability 或 batch。

## 样本与冻结规则

- 12 个新项目为 `leveldb`、`libjpeg-turbo`、`libsoundio`、`oatpp`、`8cc`、`stockfish-11`、`lz4`、`rnnoise-0.1.1`、`theora`、`libsndfile`、`civetweb`、`json-c`。
- Stage B 的 `yyjson`、`cppitertools`、`openh264`、`uwebsockets`、`c-ares`、`libass` 不进入 Stage C 分母。
- source pool 冻结 repository URL、exact commit、source archive SHA-256、许可证 SHA-256、submodule commit、构建系统能力、选择的构建系统、规模与文档分层。
- 任务资格计划冻结 target、required artifacts、artifact types、S3 oracle、bitwise 条件和 reference recipe。Reference recipe 只用于零 Provider 资格构建，不写入正式公开 task contract，也不提供给 A/B 方法。
- 每项执行两次 reference build；required artifacts、结构、oracle 和清理均须通过。声明 bitwise 必需的任务还须在两次 reference build 间字节一致。

## 方法

### A：CXXCrafter-style controlled baseline

保留 Parser、Dockerfile Generator、Executor、LLM Judge 和 Modifier 循环。Parser、Generator、Judge、Modifier 共用单臂请求、token 和墙钟预算。Dockerfile 必须使用冻结完整 image ID，只复制固定 `source/`，不得联网、安装依赖、使用特权或 Docker socket，并将精确交付写入 `/artifacts`。内部 Judge 只控制方法循环，不构成实验真值。

### B：Forge Agent Workflow Node v2

直接执行 Stage B 已校准的单 Agent Workflow Node v2，不增加零模型 fast path。候选结构拒绝可以在剩余预算内修正。External evaluator 只在候选冻结后运行，其结果不反馈给方法。

两臂使用相同任务源码、完整 Stage C image ID、CPU 与 `parallel_jobs=4`、模型、预算、operation policy、required artifact contract、S3 oracle 和 S0-S5 终点。每个 arm 使用新的 workspace、artifacts、replay 和 evidence，不共享可变构建状态。

## 调度与预算

- 12 projects x 2 replicates x 2 arms，共 24 pairs / 48 physical attempts。
- 项目顺序按 `sha256(seed + NUL + repository_url + NUL + commit_sha)` 固定。
- Replicate 1 的前 6 项为 A->B，后 6 项为 B->A；每个项目的 replicate 2 使用相反顺序。
- 同一 pair 的两个 arm 相邻执行。第一 arm 的合法方法失败不阻止第二 arm。
- 单臂上限为 24 model requests、300,000 recorded tokens、1,800 秒 method work、120 秒 cleanup reserve、900 秒单命令、1,800 秒 evaluator、1,800 秒 replay。B 另限 64 agent steps、48 tool calls 和 32 commands。
- 唯一 reachability 上限为 1 request / 5,000 recorded tokens。48 arms 上限为 14,400,000 tokens，总上限为 14,405,000 tokens。
- 只在完整 pair 开始前检查剩余总预算。已开始 pair 尽量执行完双臂；禁止 retry、replacement、fallback、backfill 和按结果重排。

## 终点与分析

主要终点为 `strict_reproducible_build_success = S0 AND S1 AND S2 AND S3 AND S4 AND S5`。每个 replicate 的配对差为 `success_B - success_A`；每个项目的 score 为两个 replicate 配对差的均值，项目是独立分析单位。

部署口径保留所有已登记 arm，包括模型失败、no-submit、预算耗尽、Provider timeout、候选拒绝、oracle 失败与 replay 失败。只有完整 pair 进入 paired estimate；不完整 pair 保留原始 evidence，不得补跑或静默删失。

报告必须分别呈现 candidate generated、candidate submitted、S0-S5、strict success、bitwise、请求、tokens、墙钟、失败分类、清理和 evidence inventory。Stage C 是校准实验，不把 24 pairs 当作 24 个独立项目，也不以显著性声明为主要结论。

## 网络、身份与停止规则

源码 clone 只允许 task remote 与 exact submodule；clone 完成后，configure、build、stage、oracle 和 replay 均使用 `network=none`。镜像必须绑定 Ubuntu package snapshot 与完整 image ID。凭据只检查环境变量存在性，不写入 evidence、容器或日志。

以下情况立即关闭 batch并保留现场：manifest、release、image、task、model、evaluator 或哈希链 identity 漂移；create-once evidence 冲突；凭据泄漏；cleanup 失败；managed orphan；无法收口的预算越界；共同 adapter/oracle 缺陷。合法分类的方法失败不关闭后续 batch。

正式执行只能从干净 `main == origin/main` 且为授权基线后代的 release 开始。先运行一次 preflight，再运行唯一 reachability；reachability 失败后不得在同一 identity 重试。正式 batch 开始后只允许从完整连续 pair 前缀恢复。
