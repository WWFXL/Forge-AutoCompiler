# Runtime v6 的 H0/H1/H2 held-out 零 Provider 资格预注册

## 身份

- Identity：`cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1`
- Tracking Issue：#451
- 分支：`yiwei/451-h0-h1-h2-runtime-v6-qualification`
- 工作类型：实验设计与零 Provider 样本、生命周期资格

## 冻结问题

本 identity 只判断三个 held-out 项目是否能形成确定性 source archive、reference closure 和 Runtime v6 后续比较输入，
并验证 H0/H1/H2 分派与共同预算合同。它不估计 treatment effect。

## 样本与动作

样本固定为 CMake `commonmark/cmark@7e1e10c...`、Make `orangeduck/mpc@1049534...`、Autotools
`libexpat/libexpat@ac140c2...`。完整 URL、源码哈希、命令、目标和 smoke 由 const manifest 冻结。当前 identity 禁止
replacement、backfill 和结果后换样本。

Q0 必须重新 clone exact commit，并通过确定性 `git archive --format=tar HEAD | gzip -n` 得到预注册哈希。Q1 必须在
固定 `autocompiler:gcc13` image、`--network none` 下执行完整 recipe；三项均须通过 smoke、artifact stage 和真实
`ReplayClosureVerifier`。

## 后续正式设计

后续三臂固定为 H0/Runtime v3、H1/Runtime v4、H2/Runtime v6，每项目每臂重复两次，共 18 arms。三臂共享
`T=600,000`、`R=100,000` recorded-token 合同、36 requests、96 steps、72 tools、48 commands 和相同超时。
主要 estimand 为 `strict_success(H2) - strict_success(H1)`，项目族聚类，非劣界 `-0.10`。当前资格 observation 不进入
正式分母。

## 通过门槛

1. 三份 source archive 的 commit、SHA-256 和大小完全一致；
2. 三个 reference recipe、functional smoke 与隔离 clean replay 全部成功；
3. expected/actual delivery 路径、类型、大小和 SHA-256 一致；
4. replay closure 不写正式 replay attempt，Session 保持活动；
5. 每个容器 cleanup 成功，最终无受管残留；
6. dispatch 精确为 H0/v3、H1/v4、H2/v6；
7. credential、Provider、Jev、model token 和 formal effect attempt 均为 0。

任一门槛失败，决定为 `stop_before_runtime_v6_three_arm_formal_comparison`。全部通过，决定为
`proceed_to_runtime_v6_three_arm_formal_comparison_design`。

## 权限与解释边界

用户在当前会话授权本阶段使用公开网络、Docker 和新的 create-once evidence。禁止读取 credential、调用 Provider/Jev、
创建效果 arm、replacement、backfill、修改旧 evidence或实现动态预算 controller。Q0/Q1 不支持成功率、成本、token、
墙钟、自然失败或开放世界泛化结论。
