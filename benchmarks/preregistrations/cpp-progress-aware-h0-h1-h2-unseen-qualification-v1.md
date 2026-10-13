# C++ H0/H1/H2 未见项目族零 Provider 资格预注册

## 身份

- Identity：`cpp-progress-aware-h0-h1-h2-unseen-qualification-v1`
- Tracking Issue：#445
- 分支：`yiwei/445-h0-h1-h2-unseen-comparison-design`
- 工作类型：零 Provider 样本与工程生命周期资格

## 冻结问题

本实验只判断三个未见项目是否能形成确定性离线源码归档、reference closure 和 Runtime v5 replay-closure 输入，并验证
H0/H1/H2 dispatch 的唯一差异。它不估计三臂效果。

## 样本与动作

样本固定为 `tinyxml2@8224e427...`、`mjson@696969cd...`、`libcsv@b1d52128...`，分别代表 CMake、Make、
Autotools。完整 URL、源码归档 SHA-256、命令、目标和 oracle 由 const manifest 冻结。

Q0 必须重新 clone exact commit，并通过确定性 `git archive --format=tar HEAD | gzip -n` 得到预注册哈希。
Q1 必须在镜像 `sha256:d27a6a...` 中、构建网络关闭时执行 manifest recipe；三项均须通过 smoke、artifact stage 和真实
`ReplayClosureVerifier`。

## 通过门槛

以下条件必须全部成立：

1. 三份 source archive 的 commit、SHA-256 和大小完全一致；
2. 三个项目的当前工作区 recipe 与隔离 clean replay 均成功；
3. expected/actual delivery 路径、类型、大小和 SHA-256 一致；
4. replay closure 未写正式 replay attempt，Session 保持活动；
5. 每个容器 cleanup 成功，最终无受管残留；
6. dispatch 恰为 H0/v3、H1/v4、H2/v5；
7. credential read、Provider request、Jev request、model token 和 formal effect attempt 均为 0。

任一条件失败，决定为 `stop_before_unseen_three_arm_provider_canary`。全部通过，决定为
`proceed_to_unseen_three_arm_provider_canary_design`。

## 权限与解释边界

用户在当前会话授权本阶段使用公开网络、Docker 和新的 create-once evidence。禁止读取 credential、调用 Provider/Jev、
创建效果 attempt、replacement、backfill、修改旧 evidence 或实现动态预算 controller。Q0/Q1 数值不得转写为成功率、
成本或 H2 treatment claim。
