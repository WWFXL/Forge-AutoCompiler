# Submit 拒绝恢复零 Provider 工程门禁预注册

## 身份

- Identity：`cpp-progress-aware-submit-rejection-recovery-gate-v1`
- Tracking Issue：#449
- 分支：`yiwei/449-submit-rejection-recovery-gate`
- 工作类型：零 Provider 工程修复资格

## 冻结问题

Runtime v6 能否在 Runtime v5 的 replay closure 拒绝后，基于 submit 后的权威 frontier 开放一个有界 repair window，使 Agent 能新增正确 build 和 artifact-stage 证据并再次提交，同时保持普通 candidate-ready、预算、严格验证和 cleanup 约束？

## 冻结案例

Q0 为纯状态机与脚本化 Agent 案例：旧语义死锁复现、ready-before-submit、单窗口上限、accepted/terminal/malformed submit、无效合同和预算终止。

Q1 为真实 Docker Make 夹具：顶层失败命令留下正确 `test/unit_test`；随后 `make unit_test` 在脏工作区 up-to-date，但 clean replay 以 `recipe_execution_failed` 拒绝。Runtime v6 必须允许 `make -C test test` 和一次重新 stage，第二次 submit 必须通过 CandidateVerifier、functional oracle 和 ReplayClosureVerifier。

## 主要门槛

1. v5 旧语义确定性复现 submit 后 frontier 漂移，且 repair Shell 被拒绝；
2. v6 首次 closure 精确返回 `recipe_execution_failed`，Session 保持活动；
3. 被拒 frontier 只允许一个非 staging repair 和一个 artifact-stage，第二个 repair build 及额外 stage 均被拒绝；
4. 修复后的新 frontier 必须再次 submit，第二次 closure 通过并冻结候选；
5. 普通 ready candidate 在未 submit 前仍拒绝 Shell；
6. accepted、terminal、malformed submit 不开放窗口；无效合同和预算终止有界闭合；
7. CandidateVerifier、functional oracle 和 replay closure 均真实执行，正式 external evaluator 语义未被替换；
8. compile/replay 容器 cleanup 完成，最终受管容器为 0；
9. #447 inventory canonical SHA-256 仍为 `e911bb1d5d40fc270ede9921bbb4781bcd75d4851bf8fe4ef1f95d02f97e6696`；
10. credential read、Provider/Jev request、model token 和 formal effect attempt 均为 0。

任一门槛失败即决定 `stop_before_formal_comparison`。全部通过则决定 `proceed_to_unseen_three_arm_formal_comparison_design`。

## 权限与解释边界

用户已授权 Docker、公开本地工程执行和新的 create-once evidence。禁止读取 credential、调用 Provider/Jev、修改或续跑 #447 evidence、创建 18-arm formal attempt、replacement 或 backfill。本结果不得解释为 H2 treatment effect、成功率非劣、成本收益或自然失败泛化。
