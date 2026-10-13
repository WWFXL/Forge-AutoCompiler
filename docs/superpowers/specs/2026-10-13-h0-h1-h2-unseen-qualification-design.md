# 未见项目族 H0/H1/H2 三臂比较资格设计

> 日期：2026-10-13  
> Tracking Issue：[#445](https://github.com/WWFXL/Forge-AutoCompiler/issues/445)  
> 工作类型：实验设计与零 Provider 基础设施资格

## 1. 研究问题

本阶段为后续 H0/H1/H2 小规模比较冻结可执行设计，不估计 treatment effect。后续比较要回答：

1. H0 的 Token 阈值从 300,000 提高后，既有 `budget_exhausted` 是否转为严格成功；
2. H2 的 pre-freeze replay closure 是否相对 H1 减少 post-freeze replay failure；
3. H2 的额外 preflight 是否造成不可接受的墙钟开销。

H0 是 Runtime v3 原始受限 ReAct Agent，H1 是 Runtime v4 进展感知 Harness，H2 是 Runtime v5，即 H1 加
pre-freeze replay closure。保留 H1 是为了隔离 replay closure 的增量贡献。

## 2. 已观察依据与预算

H0/H1 v3 的 27 个 H0 arm 中，6 个在 300,000 Token 阈值后终止，实际完整记录值位于
`308,166-337,389`；H0 最大值为 `337,389`。541 个已完成响应的单响应最大值为 `52,297`。

后续三臂使用相同预算：

- 下一请求停止阈值 `600,000` recorded tokens；
- 单响应上界 `100,000` recorded tokens；
- 单臂授权上界 `700,000` recorded tokens；
- 最多 36 次模型请求、96 Agent steps、72 次工具调用、48 条命令；
- node、evaluator 和 replay 各 1800 秒，单命令 900 秒，cleanup 120 秒。

600,000 约为已观察 H0 最大消耗的 1.78 倍，足以检验原 300k 截断解释，同时仍保持有界。该选择是在观察
v3 后作出，必须在新项目 Provider outcome 产生前冻结。

## 3. 未见项目与来源筛查

项目族相对 Forge 既有 benchmark 语料未出现，且 Provider treatment 前只允许来源和 reference closure 筛查：

| 构建系统 | 项目 | exact commit | 冻结目标 |
| --- | --- | --- | --- |
| CMake | `leethomason/tinyxml2` | `8224e427b655b83dae5e2298f1e6919523a78737` | `lib/libtinyxml2.a` |
| Make | `cesanta/mjson` | `696969cd0d35399cc66075f5ec7a96e23ba4a89b` | `bin/mjson-unit-test` |
| Autotools | `rgamble/libcsv` | `b1d5212831842ee5869d99bc208a21837e4037d5` | `lib/libcsv.a` |

首轮 Autotools 筛查固定的 `libconfuse/libconfuse@d989cbd...` 因冻结镜像缺少 `autopoint/config.rpath` 未通过，
没有进入样本。第二组只固定 `rgamble/libcsv`；其仓库自带 `fix-timestamps.sh`，该命令作为显式 dependency 动作，
避免 Git 导出同秒时间戳触发 Automake 1.14 重生成。

筛查结果只证明固定镜像中 reference recipe 可执行。它不形成 Agent、H1 或 H2 效果观察。

## 4. 零 Provider 资格

正式 identity 为 `cpp-progress-aware-h0-h1-h2-unseen-qualification-v1`。

- Q0 来源门禁：按 exact commit clone，使用 `git archive --format=tar HEAD | gzip -n` 生成确定性源码归档，并核对预冻结 SHA-256。
- Q1 lifecycle 门禁：三项目在 `autocompiler:gcc13`、禁网容器中执行完整 recipe、functional smoke 和 artifact stage；
  对提交 recipe 运行真实 `ReplayClosureVerifier`，要求三项均通过、delivery 完全一致、Session 不被错误终结、正式 replay
  attempt 为 0、cleanup 后受管容器为 0。
- 三臂绑定门禁：后续 runner 的唯一 dispatch 固定为 Runtime v3/v4/v5；H2 相对 H1 仅增加 replay closure。

Q0/Q1 通过只允许进入 Provider canary 设计。它不说明 H2 提高成功率，也不回答充足预算下 H0 的能力上限。

## 5. 后续效果比较边界

下一身份建议先做每项目每臂一次的 9-arm canary，只检查生命周期、计量、treatment separation 和方差；canary 不进入
效果估计。通过后再决定是否执行每项目每臂两次的 18-arm 配对比较。

主要观察量为 strict success、`budget_exhausted`、post-freeze replay failure、H2 pre-freeze rejection/repair、
Provider requests、recorded tokens、费用、动作数与墙钟。H2 的论文价值要求相对 H1 消除 replay failure，且相对 H0/H1
没有明显严格成功退化；仅增加 preflight 但没有改变 outcome 时，只能算工程加固。

## 6. 权限与停止规则

本 identity 允许网络获取公开源码、Docker、写入新的 create-once evidence 和报告；credential、Provider、Jev、模型 Token、
正式效果 attempt、replacement、backfill 和动态预算 controller 均为 0。任一源码哈希、镜像、recipe、closure、cleanup 或
三臂绑定门禁失败即封口当前 identity，不把部分通过解释为 treatment effect。
