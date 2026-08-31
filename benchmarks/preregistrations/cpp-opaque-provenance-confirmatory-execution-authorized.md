# Forge opaque provenance 六 case confirmatory execution authorized amendment

- GitHub Issue：[Issue #237](https://github.com/WWFXL/Forge-AutoCompiler/issues/237)
- 父候选：Issue #235 / PR #236
- 授权基线：`main@0c5b7b4f4130fb1a2a17611b3f74b8cc90359fd6`

## 研究问题

在 state-matched 的 opaque build provenance failure checkpoint 上，仅向 treatment arm 暴露冻结 repair packet，是否提高 production verifier 与 P2 reference criterion 均认可的 provenance conversion？

## 冻结设计

- 六个 project block：`pupnp`、`ada-url`、`args`、`gpac`、`fio`、`sql-parser-shared`。
- 每个项目两个独立 checkpoint replicate，共 12 pairs / 24 arms。
- 项目内第二个 replicate 反转 arm order；batch 顺序逐字继承父候选。
- Provider/model：DeepSeek `deepseek-v4-flash`，endpoint `https://api.deepseek.com`。
- 每请求 300 秒、0 retry、非 streaming，禁止 fallback、replacement 和 backfill。
- 每 arm 最多 8 请求、8 model turns、24 graph steps、600 秒工作墙钟、120,000 recorded tokens。
- reachability 最多 1 次、5,000 recorded tokens；整个 batch 最多 2,940,000 recorded tokens。

## 执行边界

- 首请求前必须通过 release、父候选哈希、独立 evidence、Ubuntu 原生 Docker、0 orphan、网络介质和 credential-name-only preflight。
- Evidence 使用新的 create-once 目录；任何已开始但没有冻结 pair outcome 的目录都不自动重跑。
- checkpoint capture/restore 复用既有 `RealLifecycleCheckpointGate`；批次恢复复用 behavioral pilot v2 的单事件循环和 append-only outcome 模式。
- CMake pair 复用既有 opaque provenance CMake 执行路径；Make pair 复用 R3 Make 执行路径。新增 runner 只注入冻结 case adapter、policy、P2 evaluator 和批次状态。
- 不修改生产 Compiler、candidate verifier、clean replay、历史 runner 或历史 evidence。

## 终态与停止规则

- endpoint censoring 与模型行为结果保留为 observation，并继续下一预注册 pair。
- mechanism、identity、evidence、cleanup 或 orphan 无效时立即关闭 batch。
- 启动新 pair 前按最坏 240,000 tokens 检查剩余预算；不得启动部分 pair。
- 所有 provider opportunity 一次性消费；禁止 retry、replacement、backfill 或 schedule extension。

## 分析

- 独立分析单位是 project block，不是 arm 或 pair。
- 每个项目得分为两个 replicate 的 paired conversion difference 均值。
- 六个 project block 均可估计时，执行双侧 exact sign-flip test；否则只报告 attrition 与描述性结果。
- 历史 exploratory pair 不池化，不做模型排名。
