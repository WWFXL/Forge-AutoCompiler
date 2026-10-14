# Runtime v6 的 H0/H1/H2 Provider 正式比较 v2 设计

> 日期：2026-10-14
> Tracking Issue：[#455](https://github.com/WWFXL/Forge-AutoCompiler/issues/455)
> 工作类型：正式数据采集与结果分析

## 1. 研究问题

本实验检验 Runtime v6/H2 是否相对 Runtime v4/H1 保持严格成功率非劣，并通过 pre-freeze replay closure 与
submit 拒绝后的有界恢复减少不可复现候选。Runtime v3/H0 是原始受限 ReAct Agent 对照；H1 对 H0 只作为结构化
Harness 消融，H2 对 H1 才识别 Runtime v6 的增量。

H2 的正向机制结论必须同时满足严格成功非劣和机制自然激活。若没有观察到 replay rejection/recovery，或 H1 没有
post-freeze replay failure，本实验只能报告该路径在三个项目族中未自然激活，不能声称 Runtime v6 改善可靠性。

## 2. 冻结样本与三臂

样本继承通过审计的 `cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1`：

| 构建系统 | 项目 | exact commit | 目标 |
| --- | --- | --- | --- |
| CMake | `commonmark/cmark` | `7e1e10c32ca1275e387057606752123efc3e2793` | `lib/libcmark.a` |
| Make | `orangeduck/mpc` | `1049534fc56b1971345c7aaa792dea55d6f9b7bc` | `lib/libmpc.a` |
| Autotools | `libexpat/libexpat` | `ac140c2d34e0aafb1c6a126ca2917ff32d765518` | `lib/libexpat.a` |

- H0：Runtime v3；
- H1：Runtime v4；
- H2：Runtime v6，增加 pre-freeze replay closure 和一个 build 加一个 artifact-stage 的恢复窗口。

每个项目、每个 treatment 运行两次，共 18 arms。两轮采用位置平衡的冻结顺序；旧 canary 与资格 observation 不进入
正式分母。

v1 在前 8 个 arm 后因宿主磁盘耗尽失败关闭。v2 保持 v1 的样本、调度、bootstrap seed、预算、模型、终点和判据完全
不变，从 sequence 1 建立新 evidence；v1 partial observation 不进入 v2 分母。

## 3. 预算与执行合同

三臂共享 DeepSeek `deepseek-flash`、相同 frozen source、image、并行度、functional oracle、external evaluator 与预算：

- 每臂最多 36 requests、96 Agent steps、72 tool calls、48 commands；
- recorded-token 下一请求停止阈值 600,000，单响应上界 100,000，授权上界 700,000；
- node/evaluator/replay 1800 秒，command 900 秒，cleanup 120 秒；
- 全批最多 648 requests、10,800,000 stop-threshold tokens、12,600,000 authorized tokens；
- 按 input `$0.30/M`、output `$1.20/M` 且全部授权 token 视为 output，费用上界 `$15.12`。

Q0 在任何 credential read 之前校验父 evidence、source archive、Docker image、Runtime binding、clean pushed release 和
零 managed resource。Q0 通过后才允许读取 `DEEPSEEK_API_KEY`。Evidence create-once；失败、超时、预算耗尽和部分结果
都保留，不 replacement、不 backfill。

为防止 v1 基础设施失败复现，Q0 和每个 arm attempt marker 创建前必须记录仓库所在文件系统的剩余空间，并要求至少
20 GiB。低于门槛时在新 arm 开始前失败关闭。该门禁不改变 treatment，也不允许删除任何 experiment evidence。

## 4. 指标与判定

主要 estimand 是按项目族聚类的 `strict_success(H2) - strict_success(H1)`。使用固定 seed 的 10,000 次项目族
bootstrap，冻结单侧 95% 下界；非劣界为 `-0.10`。

同时报告 H0/H1/H2 的 strict success、Provider requests、input/output/recorded tokens、费用、墙钟、diagnostic
commands、budget exhaustion、no-candidate、S5 external replay failure、pre-freeze closure、submit rejection、repair
window 打开/消费和二次 submit。

结论分为三类：

1. 硬门禁或 evidence 不闭合：正式执行无效；
2. 非劣失败：不支持 Runtime v6；
3. 非劣通过但机制未自然激活：只支持系统非退化，不支持可靠性机制改善；
4. 非劣通过且出现可归因的 H1 replay failure 与 H2 closure/recovery：支持本样本上的有界机制复现。

三个项目族只支持有边界的机制复现，不支持开放世界、总体泛化、统计显著性或通用 Agent 排名。
